"""Testes unitários para a lógica de cruzamento de linha (LineCounter)."""
from __future__ import annotations

import pytest

from app.core.config import CameraConfig, CountingLineConfig
from app.core.detector import TrackedPerson
from app.services.counter import LineCounter


@pytest.fixture
def cam_config_vertical_right() -> CameraConfig:
    return CameraConfig(
        id="cam-vert",
        name="Teste Vertical",
        type="usb",
        source=0,
        counting_line=CountingLineConfig(
            orientation="vertical",
            position=0.5,
            direction_in="right",
        ),
    )


@pytest.fixture
def cam_config_horizontal_down() -> CameraConfig:
    return CameraConfig(
        id="cam-horiz",
        name="Teste Horizontal",
        type="usb",
        source=0,
        counting_line=CountingLineConfig(
            orientation="horizontal",
            position=0.5,
            direction_in="down",
        ),
    )


def build_person(tid: int, x: int, y: int) -> TrackedPerson:
    """Helper para criar uma pessoa com bbox falso mas centróide controlado."""
    # Centroid da bbox será (x, y)
    return TrackedPerson(
        track_id=tid,
        bbox=(x - 10, y - 10, x + 10, y + 10),
        confidence=0.9,
    )


@pytest.mark.asyncio
async def test_vertical_crossing_in(cam_config_vertical_right: CameraConfig):
    """Testa cruzamento de linha vertical para a DIREITA (entrada)."""
    callback_calls = []

    async def mock_callback(cid: str, direction: str, tid: int, dwell_duration: float | None):
        callback_calls.append((cid, direction, tid, dwell_duration))

    counter = LineCounter(cam_config_vertical_right, on_crossing=mock_callback)

    # Frame de 640x480. A linha está no x=320 (0.5 * 640)
    # Dead-zone padrão = 8px => deve cruzar de <312 para >328
    w, h = 640, 480

    # Frame 1: pessoa #1 está claramente à esquerda da dead-zone (x=290)
    await counter.update([build_person(1, 290, 240)], w, h)
    assert counter.state.count_in == 0
    assert len(callback_calls) == 0

    # Frame 2: pessoa #1 cruzou claramente para a direita da dead-zone (x=350)
    await counter.update([build_person(1, 350, 240)], w, h)

    # Deve registrar 'in' (direction_in=right)
    assert counter.state.count_in == 1
    assert counter.state.inside == 1
    assert len(callback_calls) == 1
    assert callback_calls[0] == ("cam-vert", "in", 1, None)


@pytest.mark.asyncio
async def test_vertical_crossing_out(cam_config_vertical_right: CameraConfig):
    """Testa cruzamento de linha vertical para a ESQUERDA (saída)."""
    counter = LineCounter(cam_config_vertical_right)
    w, h = 640, 480

    # Frame 1: pessoa na direita, claramente além da dead-zone (x=360)
    await counter.update([build_person(2, 360, 240)], w, h)

    # Frame 2: cruzou para esquerda, claramente antes da dead-zone (x=280)
    await counter.update([build_person(2, 280, 240)], w, h)

    assert counter.state.count_in == 0
    assert counter.state.count_out == 1
    assert counter.state.inside == -1


@pytest.mark.asyncio
async def test_horizontal_crossing_in(cam_config_horizontal_down: CameraConfig):
    """Testa cruzamento de linha horizontal para BAIXO (entrada)."""
    counter = LineCounter(cam_config_horizontal_down)

    # Frame de 640x480. Linha no y=240 (0.5 * 480)
    # Dead-zone = 8px => deve cruzar de <232 para >248
    w, h = 640, 480

    # Frame 1: pessoa claramente em cima da dead-zone (y=200)
    await counter.update([build_person(10, 320, 200)], w, h)

    # Frame 2: pessoa cruzou claramente para baixo da dead-zone (y=270)
    await counter.update([build_person(10, 320, 270)], w, h)

    # 'down' é input, então:
    assert counter.state.count_in == 1
    assert counter.state.inside == 1


@pytest.mark.asyncio
async def test_stale_track_cleanup(cam_config_vertical_right: CameraConfig):
    """Testa se as posições cacheadas são limpas para IDs que não aparecem mais."""
    counter = LineCounter(cam_config_vertical_right)
    w, h = 640, 480

    # Frame 1: aparecem tid 1 e 2
    await counter.update([
        build_person(1, 100, 100),
        build_person(2, 500, 100)
    ], w, h)

    assert 1 in counter._last_positions
    assert 2 in counter._last_positions

    # Frame 2: apenas tid 2 aparece
    await counter.update([
        build_person(2, 510, 100)
    ], w, h)

    # tid 1 deve ter sido apagado para não estourar memória
    assert 1 not in counter._last_positions
    assert 2 in counter._last_positions


@pytest.mark.asyncio
async def test_two_people_crossing_simultaneously(cam_config_vertical_right: CameraConfig):
    """Duas pessoas cruzando a linha ao mesmo tempo devem ser contadas separadamente."""
    counter = LineCounter(cam_config_vertical_right)
    w, h = 640, 480
    # Linha em x=320, dead-zone=8 => cruzar de <312 para >328

    # Frame 1: pessoa 1 e 2 estão claramente à esquerda (x=280)
    await counter.update([
        build_person(1, 280, 200),
        build_person(2, 280, 280),
    ], w, h)
    assert counter.state.count_in == 0

    # Frame 2: ambas cruzaram claramente para a direita (x=360)
    await counter.update([
        build_person(1, 360, 200),
        build_person(2, 360, 280),
    ], w, h)

    # AMBAS devem ser contadas
    assert counter.state.count_in == 2
    assert counter.state.inside == 2


@pytest.mark.asyncio
async def test_cooldown_prevents_double_count(cam_config_vertical_right: CameraConfig):
    """O cooldown deve impedir que o mesmo track_id conte duas vezes rapidamente."""
    counter = LineCounter(cam_config_vertical_right, cooldown_frames=5)
    w, h = 640, 480

    # Frame 1: esquerda
    await counter.update([build_person(1, 280, 240)], w, h)
    # Frame 2: cruzou para direita — conta 1
    await counter.update([build_person(1, 360, 240)], w, h)
    assert counter.state.count_in == 1

    # Frame 3: volta para esquerda (simula oscilação/ID switch) — cooldown ativo, não conta
    await counter.update([build_person(1, 280, 240)], w, h)
    assert counter.state.count_out == 0  # cooldown ainda ativo
