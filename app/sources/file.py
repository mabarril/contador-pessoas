"""Fonte de vídeo via arquivo (MP4, AVI etc.) — útil para testes."""
from __future__ import annotations

import asyncio
from pathlib import Path
from typing import AsyncGenerator

import cv2
import numpy as np
from loguru import logger

from app.sources.base import VideoSource


class FileSource(VideoSource):
    def __init__(
        self,
        camera_id: str,
        name: str,
        file_path: str | Path,
        loop: bool = True,
    ) -> None:
        self.camera_id = camera_id
        self.name = name
        self._path = Path(file_path)
        self._loop = loop
        self._cap: cv2.VideoCapture | None = None
        self._fps: float = 25.0

    async def open(self) -> None:
        if not self._path.exists():
            raise FileNotFoundError(f"[{self.name}] Arquivo não encontrado: {self._path}")

        loop = asyncio.get_event_loop()
        self._cap = await loop.run_in_executor(
            None, lambda: cv2.VideoCapture(str(self._path))
        )
        if not self._cap.isOpened():
            raise OSError(f"[{self.name}] Não foi possível abrir: {self._path}")

        self._fps = self._cap.get(cv2.CAP_PROP_FPS) or 25.0
        logger.info(
            "[{}] Arquivo aberto: {} ({:.1f} fps)", self.name, self._path, self._fps
        )

    async def close(self) -> None:
        if self._cap and self._cap.isOpened():
            self._cap.release()
            logger.info("[{}] Arquivo fechado", self.name)
        self._cap = None

    def is_open(self) -> bool:
        return self._cap is not None and self._cap.isOpened()

    async def frames(self) -> AsyncGenerator[np.ndarray, None]:
        if not self._cap:
            raise RuntimeError("Fonte não aberta.")

        ev_loop = asyncio.get_event_loop()
        frame_delay = 1.0 / self._fps

        while True:
            ret, frame = await ev_loop.run_in_executor(None, self._cap.read)
            if not ret or frame is None:
                if self._loop:
                    # Reinicia o arquivo
                    await ev_loop.run_in_executor(
                        None,
                        lambda: self._cap.set(cv2.CAP_PROP_POS_FRAMES, 0),  # type: ignore[union-attr]
                    )
                    logger.debug("[{}] Arquivo reiniciado (loop)", self.name)
                    continue
                else:
                    logger.info("[{}] Arquivo finalizado", self.name)
                    break

            yield frame
            # Simula FPS real do arquivo
            await asyncio.sleep(frame_delay)
