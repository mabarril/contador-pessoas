"""Entry point — inicia servidor uvicorn."""
from __future__ import annotations

import uvicorn

from app.api.app import create_app
from app.core.config import load_config


def run() -> None:
    cfg = load_config()
    app = create_app(cfg)
    uvicorn.run(
        app,
        host=cfg.server.host,
        port=cfg.server.port,
        log_level="warning",  # Loguru cuida do logging da aplicação
    )


if __name__ == "__main__":
    run()
