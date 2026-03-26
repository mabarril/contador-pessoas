"""Rotas REST — status das câmeras e stream MJPEG."""
from __future__ import annotations

import asyncio

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from app.services.manager import CameraManager

router = APIRouter(prefix="/cameras", tags=["cameras"])

_manager: CameraManager | None = None


def init_router(manager: CameraManager) -> None:
    global _manager
    _manager = manager


def _get_manager() -> CameraManager:
    if _manager is None:
        raise HTTPException(status_code=503, detail="Manager não inicializado.")
    return _manager


@router.get("/")
async def list_cameras():
    """Lista todas as câmeras configuradas e seu estado atual."""
    manager = _get_manager()
    result = []
    for cam_id, session in manager.sessions().items():
        result.append(
            {
                "id": cam_id,
                "name": session.config.name,
                "type": session.config.type,
                "running": session.running,
                "error": session.error,
                **session.counter.state.to_dict(),
            }
        )
    return result


@router.get("/{camera_id}/state")
async def camera_state(camera_id: str):
    """Retorna estado atual de contagem de uma câmera."""
    manager = _get_manager()
    session = manager.get_session(camera_id)
    if not session:
        raise HTTPException(status_code=404, detail=f"Câmera '{camera_id}' não encontrada.")
    return {
        "id": camera_id,
        "name": session.config.name,
        "running": session.running,
        "error": session.error,
        **session.counter.state.to_dict(),
    }


@router.get("/{camera_id}/stream")
async def mjpeg_stream(camera_id: str):
    """Stream MJPEG da câmera. Compatível com <img src='...'> no browser."""
    manager = _get_manager()
    session = manager.get_session(camera_id)
    if not session:
        raise HTTPException(status_code=404, detail=f"Câmera '{camera_id}' não encontrada.")

    async def generator():
        while True:
            frame_bytes = session.latest_frame_jpeg
            if frame_bytes:
                yield (
                    b"--frame\r\n"
                    b"Content-Type: image/jpeg\r\n\r\n"
                    + frame_bytes
                    + b"\r\n"
                )
            await asyncio.sleep(0.04)  # ~25 fps

    return StreamingResponse(
        generator(),
        media_type="multipart/x-mixed-replace;boundary=frame",
    )
