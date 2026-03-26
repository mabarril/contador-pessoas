"""Lógica de cruzamento de linha e contagem entrada/saída."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from zoneinfo import ZoneInfo
from typing import Callable, Coroutine

from loguru import logger

from app.core.config import CameraConfig, CountingLineConfig
from app.core.detector import TrackedPerson


@dataclass
class CountState:
    camera_id: str
    count_in: int = 0
    count_out: int = 0
    inside: int = 0  # estimativa de pessoas no local
    last_updated: datetime = field(
        default_factory=lambda: datetime.now(tz=ZoneInfo("America/Sao_Paulo"))
    )

    def to_dict(self) -> dict:
        return {
            "camera_id": self.camera_id,
            "count_in": self.count_in,
            "count_out": self.count_out,
            "inside": max(0, self.inside),
            "last_updated": self.last_updated.isoformat(),
        }


# Callback chamado quando há cruzamento: (camera_id, direction, track_id)
CrossingCallback = Callable[[str, str, int], Coroutine]


class LineCounter:
    """
    Detecta cruzamentos de linha de contagem.

    Mantém a posição anterior de cada track_id e dispara callback
    quando a linha é cruzada.
    """

    def __init__(
        self,
        camera_cfg: CameraConfig,
        on_crossing: CrossingCallback | None = None,
    ) -> None:
        self._camera_id = camera_cfg.id
        self._line: CountingLineConfig = camera_cfg.counting_line
        self._on_crossing = on_crossing
        self._state = CountState(camera_id=camera_cfg.id)
        self._last_positions: dict[int, tuple[int, int]] = {}

    @property
    def state(self) -> CountState:
        return self._state

    async def update(
        self,
        persons: list[TrackedPerson],
        frame_width: int,
        frame_height: int,
    ) -> list[tuple[int, str]]:
        """
        Processa lista de pessoas rastreadas.

        Retorna lista de (track_id, direction) para os cruzamentos detectados.
        """
        crossings: list[tuple[int, str]] = []

        # Posição da linha em pixels
        if self._line.orientation == "vertical":
            line_px = int(self._line.position * frame_width)
        else:
            line_px = int(self._line.position * frame_height)

        for person in persons:
            tid = person.track_id
            cx, cy = person.centroid

            if tid not in self._last_positions:
                self._last_positions[tid] = (cx, cy)
                continue

            prev_x, prev_y = self._last_positions[tid]
            self._last_positions[tid] = (cx, cy)

            direction = self._detect_crossing(
                prev=(prev_x, prev_y),
                curr=(cx, cy),
                line_px=line_px,
            )
            if direction is None:
                continue

            crossings.append((tid, direction))
            self._apply(direction)

            if self._on_crossing:
                await self._on_crossing(self._camera_id, direction, tid)

            logger.info(
                "[{}] Cruzamento: track_id={} → {}  (in={}, out={}, inside={})",
                self._camera_id,
                tid,
                direction,
                self._state.count_in,
                self._state.count_out,
                self._state.inside,
            )

        # Limpa tracks que sumiram (evita vazamento de memória)
        active_ids = {p.track_id for p in persons}
        stale = [k for k in self._last_positions if k not in active_ids]
        for k in stale:
            del self._last_positions[k]

        return crossings

    def _detect_crossing(
        self,
        prev: tuple[int, int],
        curr: tuple[int, int],
        line_px: int,
    ) -> str | None:
        if self._line.orientation == "vertical":
            prev_val, curr_val = prev[0], curr[0]
            pos_dir, neg_dir = "right", "left"
        else:
            prev_val, curr_val = prev[1], curr[1]
            pos_dir, neg_dir = "down", "up"

        crossed_positive = prev_val < line_px <= curr_val
        crossed_negative = prev_val >= line_px > curr_val

        if crossed_positive:
            movement = pos_dir
        elif crossed_negative:
            movement = neg_dir
        else:
            return None

        return "in" if movement == self._line.direction_in else "out"

    def _apply(self, direction: str) -> None:
        self._state.last_updated = datetime.now(tz=ZoneInfo("America/Sao_Paulo"))
        if direction == "in":
            self._state.count_in += 1
            self._state.inside += 1
        else:
            self._state.count_out += 1
            self._state.inside -= 1
