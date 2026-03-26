"""WebSocket — broadcast de contagens em tempo real."""
from __future__ import annotations

import asyncio
import json
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from loguru import logger

router = APIRouter(tags=["websocket"])

_connections: set[WebSocket] = set()


async def broadcast(data: dict[str, Any]) -> None:
    """Envia update de contagem para todos os clientes conectados."""
    if not _connections:
        return

    message = json.dumps(data)
    dead: set[WebSocket] = set()

    for ws in list(_connections):
        try:
            await ws.send_text(message)
        except Exception:
            dead.add(ws)

    _connections.difference_update(dead)


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    _connections.add(websocket)
    logger.info("WebSocket conectado. Total: {}", len(_connections))
    try:
        while True:
            # Mantém a conexão viva aguardando ping do cliente
            await asyncio.sleep(30)
    except WebSocketDisconnect:
        pass
    except Exception as exc:
        logger.warning("WebSocket desconectado inesperadamente: {}", exc)
    finally:
        _connections.discard(websocket)
        logger.info("WebSocket desconectado. Total: {}", len(_connections))
