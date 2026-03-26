"""Gerenciador de sessões de câmera — orquestra sources, detector e counter."""
from __future__ import annotations

import asyncio
import io
from dataclasses import dataclass, field
from typing import Any

import cv2
import numpy as np
from loguru import logger

from app.core.config import AppConfig, CameraConfig
from app.core.detector import Detector, TrackedPerson
from app.db.repository import CountEventRepository
from app.db.session import get_session_factory
from app.services.counter import CountState, LineCounter
from app.sources.base import VideoSource
from app.sources.file import FileSource
from app.sources.rtsp import RtspSource
from app.sources.usb import UsbSource


@dataclass
class CameraSession:
    config: CameraConfig
    source: VideoSource
    counter: LineCounter
    task: asyncio.Task | None = None
    latest_frame_jpeg: bytes = field(default=b"", repr=False)
    error: str | None = None
    running: bool = False


class CameraManager:
    """
    Singleton que gerencia todas as câmeras configuradas.

    Responsabilidades:
    - Criar e iniciar sessions por câmera.
    - Rodar o loop de captura + detecção + contagem.
    - Fornecer frames JPEG para MJPEG streaming.
    - Notificar WebSocket subscribers via broadcast callback.
    """

    def __init__(self, config: AppConfig, detector: Detector) -> None:
        self._config = config
        self._detector = detector
        self._sessions: dict[str, CameraSession] = {}
        self._broadcast_callback: Any | None = None  # injected by ws router

    def set_broadcast(self, callback: Any) -> None:
        """Injeta callback assíncrono para broadcast de updates."""
        self._broadcast_callback = callback

    def sessions(self) -> dict[str, CameraSession]:
        return self._sessions

    def get_session(self, camera_id: str) -> CameraSession | None:
        return self._sessions.get(camera_id)

    def all_states(self) -> list[CountState]:
        return [s.counter.state for s in self._sessions.values()]

    async def start_all(self) -> None:
        for cam_cfg in self._config.cameras:
            await self.start_camera(cam_cfg)

    async def stop_all(self) -> None:
        for session in self._sessions.values():
            await self._stop_session(session)
        self._sessions.clear()

    async def start_camera(self, cam_cfg: CameraConfig) -> None:
        source = self._build_source(cam_cfg)
        counter = LineCounter(
            cam_cfg,
            on_crossing=self._on_crossing,
        )
        
        # Carrega totais de hoje do banco para não reiniciar zerado
        try:
            factory = get_session_factory()
            async with factory() as db_session:
                repo = CountEventRepository(db_session)
                counts = await repo.count_by_camera_today(cam_cfg.id)
                counter.state.count_in = counts.get("in", 0)
                counter.state.count_out = counts.get("out", 0)
                counter.state.inside = max(0, counter.state.count_in - counter.state.count_out)
        except Exception as exc:
            logger.error("Aviso: falha ao carregar estado inicial do banco: {}", exc)

        session = CameraSession(
            config=cam_cfg,
            source=source,
            counter=counter,
        )
        self._sessions[cam_cfg.id] = session
        session.task = asyncio.create_task(
            self._capture_loop(session),
            name=f"camera-{cam_cfg.id}",
        )
        logger.info("[{}] Câmera iniciada", cam_cfg.name)

    async def _stop_session(self, session: CameraSession) -> None:
        session.running = False
        if session.task and not session.task.done():
            session.task.cancel()
            try:
                await session.task
            except asyncio.CancelledError:
                pass
        await session.source.close()

    async def _capture_loop(self, session: CameraSession) -> None:
        session.running = True
        try:
            await session.source.open()
        except (OSError, FileNotFoundError) as exc:
            session.error = str(exc)
            session.running = False
            logger.error("[{}] Falha ao abrir fonte: {}", session.config.name, exc)
            return

        try:
            async for frame in session.source.frames():
                if not session.running:
                    break

                persons, annotated = await self._detector.detect(frame)

                # Desenha linha de contagem sobre o frame anotado
                annotated = self._draw_line(annotated, session.config)

                # Atualiza contagem apenas em frames processados pela IA
                if persons is not None:
                    h, w = frame.shape[:2]
                    await session.counter.update(persons, w, h)

                # Codifica frame como JPEG para MJPEG
                session.latest_frame_jpeg = self._encode_jpeg(annotated)

                # Broadcast do estado atualizado
                if self._broadcast_callback:
                    await self._broadcast_callback(session.counter.state.to_dict())

        except asyncio.CancelledError:
            pass
        except Exception as exc:
            session.error = str(exc)
            logger.exception("[{}] Erro no loop de captura", session.config.name)
        finally:
            session.running = False
            await session.source.close()

    async def _on_crossing(
        self, camera_id: str, direction: str, track_id: int
    ) -> None:
        """Persiste evento de cruzamento no banco de dados."""
        try:
            factory = get_session_factory()
            async with factory() as db_session:
                repo = CountEventRepository(db_session)
                await repo.add(camera_id, direction, track_id)
        except Exception as exc:
            logger.error("Erro ao persistir cruzamento: {}", exc)

    @staticmethod
    def _build_source(cam_cfg: CameraConfig) -> VideoSource:
        if cam_cfg.type == "usb":
            return UsbSource(cam_cfg.id, cam_cfg.name, device_index=int(cam_cfg.source))
        if cam_cfg.type == "rtsp":
            return RtspSource(cam_cfg.id, cam_cfg.name, url=str(cam_cfg.source))
        if cam_cfg.type == "file":
            return FileSource(cam_cfg.id, cam_cfg.name, file_path=str(cam_cfg.source))
        raise ValueError(f"Tipo de câmera desconhecido: {cam_cfg.type}")

    @staticmethod
    def _draw_line(frame: np.ndarray, cam_cfg: CameraConfig) -> np.ndarray:
        h, w = frame.shape[:2]
        line_cfg = cam_cfg.counting_line
        color = (0, 255, 128)  # verde-neon
        thickness = 2

        if line_cfg.orientation == "vertical":
            x = int(line_cfg.position * w)
            cv2.line(frame, (x, 0), (x, h), color, thickness)
            cv2.putText(
                frame, "LINHA", (x + 5, 20),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2,
            )
        else:
            y = int(line_cfg.position * h)
            cv2.line(frame, (0, y), (w, y), color, thickness)
            cv2.putText(
                frame, "LINHA", (5, y - 5),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2,
            )
        return frame

    @staticmethod
    def _encode_jpeg(frame: np.ndarray, quality: int = 75) -> bytes:
        _, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, quality])
        return buf.tobytes()
