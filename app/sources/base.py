"""Classe base abstrata para fontes de vídeo."""
from __future__ import annotations

import abc
from typing import AsyncGenerator

import numpy as np


class VideoSource(abc.ABC):
    """Interface comum para USB, RTSP e File."""

    camera_id: str
    name: str

    @abc.abstractmethod
    async def open(self) -> None:
        """Abre a fonte de vídeo."""

    @abc.abstractmethod
    async def close(self) -> None:
        """Libera recursos."""

    @abc.abstractmethod
    async def frames(self) -> AsyncGenerator[np.ndarray, None]:
        """Yield de frames capturados (BGR, shape HxWx3)."""
        # O `yield` aqui é apenas para satisfazer o type checker.
        # Subclasses devem sobrescrever completamente.
        raise NotImplementedError
        yield  # type: ignore[misc]

    @abc.abstractmethod
    def is_open(self) -> bool:
        """Retorna True se a fonte está capturando."""
