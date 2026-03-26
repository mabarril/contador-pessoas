"""Detector YOLOv8 + ByteTrack via ultralytics."""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np
from loguru import logger

try:
    from ultralytics import YOLO
except ImportError:
    YOLO = None  # type: ignore[assignment,misc]


@dataclass
class TrackedPerson:
    track_id: int
    bbox: tuple[int, int, int, int]  # x1, y1, x2, y2
    confidence: float

    @property
    def centroid(self) -> tuple[int, int]:
        x1, y1, x2, y2 = self.bbox
        return ((x1 + x2) // 2, (y1 + y2) // 2)


class Detector:
    """
    Wrapper em torno do YOLOv8 com ByteTrack integrado.

    Roda a inferência em um thread-pool executor para não bloquear o event loop.
    """

    CLASS_PERSON = 0  # índice da classe "person" no COCO

    def __init__(
        self,
        model_path: Path,
        confidence: float = 0.5,
        input_resolution: tuple[int, int] = (640, 480),
        skip_frames: int = 2,
    ) -> None:
        self._model_path = model_path
        self._confidence = confidence
        self._input_w, self._input_h = input_resolution
        self._skip_frames = skip_frames
        self._model: "YOLO | None" = None
        self._frame_counter = 0

    def load(self) -> None:
        """Carrega modelo (síncrono — chamar no startup)."""
        if YOLO is None:
            raise ImportError("ultralytics não está instalado.")
        if not self._model_path.exists():
            raise FileNotFoundError(
                f"Modelo não encontrado: {self._model_path}\n"
                "Execute: python scripts/download_model.py"
            )
        self._model = YOLO(str(self._model_path))
        logger.info("Modelo carregado: {}", self._model_path)

    async def detect(
        self, frame: np.ndarray
    ) -> tuple[list[TrackedPerson] | None, np.ndarray]:
        """
        Roda detecção + tracking.

        Retorna (lista de pessoas rastreadas, frame anotado).
        """
        self._frame_counter += 1
        if self._frame_counter % self._skip_frames != 0:
            return None, frame

        loop = asyncio.get_event_loop()
        persons, annotated = await loop.run_in_executor(
            None, self._run_sync, frame
        )
        return persons, annotated

    def _run_sync(
        self, frame: np.ndarray
    ) -> tuple[list[TrackedPerson], np.ndarray]:
        if self._model is None:
            raise RuntimeError("Detector não carregado. Chame load() primeiro.")

        # Redimensiona para resolução de inferência
        resized = cv2.resize(frame, (self._input_w, self._input_h))

        results = self._model.track(
            resized,
            persist=True,
            classes=[self.CLASS_PERSON],
            conf=self._confidence,
            verbose=False,
            tracker="bytetrack.yaml",
        )

        persons: list[TrackedPerson] = []
        result = results[0]

        if result.boxes is not None and result.boxes.id is not None:
            boxes = result.boxes.xyxy.cpu().numpy().astype(int)
            ids = result.boxes.id.cpu().numpy().astype(int)
            confs = result.boxes.conf.cpu().numpy()

            # Escala de volta para dimensões originais
            h_orig, w_orig = frame.shape[:2]
            sx = w_orig / self._input_w
            sy = h_orig / self._input_h

            for bbox, tid, conf in zip(boxes, ids, confs):
                x1, y1, x2, y2 = bbox
                persons.append(
                    TrackedPerson(
                        track_id=int(tid),
                        bbox=(
                            int(x1 * sx),
                            int(y1 * sy),
                            int(x2 * sx),
                            int(y2 * sy),
                        ),
                        confidence=float(conf),
                    )
                )

        # Frame anotado (redimensionado de volta ao original)
        annotated = cv2.resize(result.plot(), (frame.shape[1], frame.shape[0]))
        return persons, annotated
