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

    async def mock_callback(cid: str, direction: str, tid: int):
        callback_calls.append((cid, direction, tid))

    counter = LineCounter(cam_config_vertical_right, on_crossing=mock_callback)

    # Frame de 640x480. A linha está no x=320 (0.5 * 640)
    w, h = 640, 480

    # Frame 1: pessoa #1 está à esquerda da linha (x=300)
    await counter.update([build_person(1, 300, 240)], w, h)
    assert counter.state.count_in == 0
    assert len(callback_calls) == 0

    # Frame 2: pessoa #1 cruzou para a direita da linha (x=330)
    await counter.update([build_person(1, 330, 240)], w, h)
    
    # Deve registrar 'in' (direction_in=right)
    assert counter.state.count_in == 1
    assert counter.state.inside == 1
    assert len(callback_calls) == 1
    assert callback_calls[0] == ("cam-vert", "in", 1)


@pytest.mark.asyncio
async def test_vertical_crossing_out(cam_config_vertical_right: CameraConfig):
    """Testa cruzamento de linha vertical para a ESQUERDA (saída)."""
    counter = LineCounter(cam_config_vertical_right)
    w, h = 640, 480

    # Frame 1: pessoa na direita (x=340)
    await counter.update([build_person(2, 340, 240)], w, h)
    
    # Frame 2: cruzou para esquerda (x=300)
    await counter.update([build_person(2, 300, 240)], w, h)

    assert counter.state.count_in == 0
    assert counter.state.count_out == 1
    assert counter.state.inside == -1


@pytest.mark.asyncio
async def test_horizontal_crossing_in(cam_config_horizontal_down: CameraConfig):
    """Testa cruzamento de linha horizontal para BAIXO (entrada)."""
    counter = LineCounter(cam_config_horizontal_down)
    
    # Frame de 640x480. Linha no y=240 (0.5 * 480)
    w, h = 640, 480

    # Frame 1: pessoa em cima (y=200)
    await counter.update([build_person(10, 320, 200)], w, h)
    
    # Frame 2: pessoa cruzou para baixo (y=260)
    await counter.update([build_person(10, 320, 260)], w, h)

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
