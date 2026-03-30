"""Lógica de cruzamento de linha e contagem entrada/saída."""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable, Coroutine
from zoneinfo import ZoneInfo

from loguru import logger

from app.core.config import CameraConfig, CountingLineConfig
from app.core.detector import TrackedPerson


@dataclass
class CountState:
    camera_id: str
    count_in: int = 0
    count_out: int = 0
    inside: int = 0  # estimativa de pessoas no local
    dwell_total_seconds: float = 0.0
    dwell_count: int = 0
    last_updated: datetime = field(
        default_factory=lambda: datetime.now(tz=ZoneInfo("America/Sao_Paulo"))
    )

    def to_dict(self) -> dict:
        avg_dwell = 0.0
        if self.dwell_count > 0:
            avg_dwell = self.dwell_total_seconds / self.dwell_count

        return {
            "camera_id": self.camera_id,
            "count_in": self.count_in,
            "count_out": self.count_out,
            "inside": max(0, self.inside),
            "avg_dwell_seconds": avg_dwell,
            "dwell_total_seconds": self.dwell_total_seconds,
            "dwell_count": self.dwell_count,
            "last_updated": self.last_updated.isoformat(),
        }


# Callback chamado quando há cruzamento: (camera_id, direction, track_id, dwell_duration)
CrossingCallback = Callable[[str, str, int, float | None], Coroutine]


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
        dead_zone_px: int = 8,
        cooldown_frames: int = 10,
    ) -> None:
        self._camera_id = camera_cfg.id
        self._line: CountingLineConfig = camera_cfg.counting_line
        self._on_crossing = on_crossing
        self._state = CountState(camera_id=camera_cfg.id)
        self._last_positions: dict[int, tuple[int, int]] = {}
        # Dead-zone: pixels de margem em cada lado da linha para evitar oscilação
        self._dead_zone_px = dead_zone_px
        # Cooldown: número de frames após um cruzamento em que o mesmo track não conta de novo
        self._cooldown_frames = cooldown_frames
        # Mapeia track_id -> frame_counter do seu último cruzamento
        self._crossed_tracks: dict[int, int] = {}
        self._frame_count = 0
        # Fila FIFO para tempo de permanência (armazena datetime de cada "in")
        self._entry_timestamps: deque[datetime] = deque()
        # Rastreia o último lado conhecido fora da dead-zone: -1 (esq/cima), 1 (dir/baixo)
        self._last_sides: dict[int, int] = {}

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
        self._frame_count += 1

        # Posição da linha em pixels
        if self._line.orientation == "vertical":
            line_px = int(self._line.position * frame_width)
        else:
            line_px = int(self._line.position * frame_height)

        for person in persons:
            tid = person.track_id
            cx, cy = person.centroid

            # Registra posição última conhecida para compatibilidade (embora o novo sistema use last_sides)
            self._last_positions[tid] = (cx, cy)

            # Verifica cooldown: ignora cruzamento se o track cruzou recentemente
            last_cross = self._crossed_tracks.get(tid, -self._cooldown_frames - 1)
            if (self._frame_count - last_cross) <= self._cooldown_frames:
                continue

            direction = self._detect_crossing(tid, cx, cy, line_px)
            if direction is None:
                continue

            crossings.append((tid, direction))
            self._crossed_tracks[tid] = self._frame_count
            dwell_duration = self._apply(direction)

            if self._on_crossing:
                await self._on_crossing(self._camera_id, direction, tid, dwell_duration)

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
        
        # Limpa estados de lado para tracks inativos
        stale_sides = [k for k in self._last_sides if k not in active_ids]
        for k in stale_sides:
            del self._last_sides[k]

        # Limpa cooldown de tracks inativos também
        stale_crossed = [k for k in self._crossed_tracks if k not in active_ids]
        for k in stale_crossed:
            del self._crossed_tracks[k]

        return crossings

    def _detect_crossing(
        self,
        tid: int,
        cx: int,
        cy: int,
        line_px: int,
    ) -> str | None:
        if self._line.orientation == "vertical":
            val = cx
            pos_dir, neg_dir = "right", "left"
        else:
            val = cy
            pos_dir, neg_dir = "down", "up"

        dz = self._dead_zone_px
        
        # Determina o lado atual de forma definitiva
        if val < (line_px - dz):
            current_side = -1
        elif val > (line_px + dz):
            current_side = 1
        else:
            current_side = 0  # Na dead-zone

        last_side = self._last_sides.get(tid)
        
        # Se for o primeiro frame e estiver fora da dead-zone, inicializa e encerra
        if last_side is None:
            if current_side != 0:
                self._last_sides[tid] = current_side
            return None

        # Se mudou de lado (e não é apenas entrada/saída da dead-zone)
        movement = None
        if last_side == -1 and current_side == 1:
            movement = pos_dir
        elif last_side == 1 and current_side == -1:
            movement = neg_dir

        # Atualiza o último lado definitivo se estiver fora da dead-zone
        if current_side != 0:
            self._last_sides[tid] = current_side

        if movement is None:
            return None

        return "in" if movement == self._line.direction_in else "out"

    def _apply(self, direction: str) -> float | None:
        now = datetime.now(tz=ZoneInfo("America/Sao_Paulo"))
        self._state.last_updated = now
        
        dwell_duration: float | None = None

        if direction == "in":
            self._state.count_in += 1
            self._state.inside += 1
            # Adiciona timestamp da entrada à fila FIFO
            self._entry_timestamps.append(now)
        else:
            self._state.count_out += 1
            self._state.inside -= 1
            # Calcula tempo de permanência se houver alguém na fila
            if self._entry_timestamps:
                entry_time = self._entry_timestamps.popleft()
                dwell_duration = (now - entry_time).total_seconds()
                # Acumula estatísticas no estado (para tempo real no dashboard)
                if dwell_duration is not None:
                    self._state.dwell_total_seconds += dwell_duration
                    self._state.dwell_count += 1

        return dwell_duration

    def reset(self) -> None:
        """Zera os contadores (usado na virada do dia)."""
        self._state.count_in = 0
        self._state.count_out = 0
        self._state.inside = 0
        self._state.dwell_total_seconds = 0.0
        self._state.dwell_count = 0
        self._state.last_updated = datetime.now(tz=ZoneInfo("America/Sao_Paulo"))
        self._last_positions.clear()
        self._crossed_tracks.clear()
        self._entry_timestamps.clear()
        logger.info("[{}] Contadores resetados", self._camera_id)
