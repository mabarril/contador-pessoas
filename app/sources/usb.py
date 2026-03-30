"""Fonte de vídeo via câmera USB (webcam)."""
from __future__ import annotations

import asyncio
from typing import AsyncGenerator

import cv2
import numpy as np
from loguru import logger

from app.sources.base import VideoSource


class UsbSource(VideoSource):
    def __init__(self, camera_id: str, name: str, device_index: int = 0) -> None:
        self.camera_id = camera_id
        self.name = name
        self._device_index = device_index
        self._cap: cv2.VideoCapture | None = None

    async def open(self) -> None:
        loop = asyncio.get_event_loop()
        self._cap = await loop.run_in_executor(
            None, lambda: cv2.VideoCapture(self._device_index)
        )
        if not self._cap.isOpened():
            raise OSError(
                f"[{self.name}] Não foi possível abrir USB device={self._device_index}"
            )
        logger.info("[{}] USB device={} aberto", self.name, self._device_index)

    async def close(self) -> None:
        if self._cap and self._cap.isOpened():
            self._cap.release()
            logger.info("[{}] USB device fechado", self.name)
        self._cap = None

    def is_open(self) -> bool:
        return self._cap is not None and self._cap.isOpened()

    async def frames(self) -> AsyncGenerator[np.ndarray, None]:
        if not self._cap:
            raise RuntimeError("Fonte não aberta. Chame open() primeiro.")

        loop = asyncio.get_event_loop()
        consecutive_failures = 0

        while self.is_open():
            ret, frame = await loop.run_in_executor(None, self._cap.read)
            if not ret or frame is None:
                consecutive_failures += 1
                logger.warning(
                    "[{}] Frame USB inválido (falha #{}) — tentando reconectar...",
                    self.name,
                    consecutive_failures,
                )
                if consecutive_failures >= 5:
                    await self.close()
                    await asyncio.sleep(2.0)
                    try:
                        await self.open()
                        consecutive_failures = 0
                    except OSError:
                        await asyncio.sleep(5.0)
                else:
                    await asyncio.sleep(0.1)
                continue

            consecutive_failures = 0
            yield frame
