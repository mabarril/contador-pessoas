"""FastAPI app factory — monta a aplicação e registra lifecycle hooks."""
from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from loguru import logger

from app.api.routes import cameras as cameras_router
from app.api.routes import reports as reports_router
from app.api.routes import ws as ws_router
from app.core.config import AppConfig, load_config
from app.core.detector import Detector
from app.core.logging import setup_logging
from app.db.session import close_db, init_db
from app.services.manager import CameraManager
from app.tasks.scheduler import build_scheduler


def create_app(config: AppConfig | None = None) -> FastAPI:
    cfg = config or load_config()
    setup_logging(cfg.logging.level, cfg.logging.retention_days)

    detector = Detector(
        model_path=cfg.model.path,
        confidence=cfg.model.confidence_threshold,
        input_resolution=tuple(cfg.model.input_resolution),  # type: ignore[arg-type]
        skip_frames=cfg.model.skip_frames,
    )

    manager = CameraManager(cfg, detector)
    scheduler = build_scheduler(cfg, manager)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        logger.info("🚀 Iniciando Contador de Pessoas...")

        # DB
        await init_db(cfg.database.path)

        # Modelo
        try:
            detector.load()
        except FileNotFoundError as exc:
            logger.error("{}", exc)
            logger.warning("Sistema iniciará sem detecção de IA.")

        # Injeta broadcast do WS no manager
        manager.set_broadcast(ws_router.broadcast)

        # Câmeras
        await manager.start_all()

        # Scheduler de relatórios
        scheduler.start()

        logger.info("✅ Sistema pronto em http://{}:{}", cfg.server.host, cfg.server.port)
        yield

        # Shutdown
        logger.info("🛑 Encerrando...")
        scheduler.shutdown(wait=False)
        await manager.stop_all()
        await close_db()
        logger.info("Sistema encerrado.")

    app = FastAPI(
        title="Contador de Pessoas",
        version="0.1.0",
        description="Sistema standalone de contagem de pessoas via câmera e IA",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Injeta manager nos routers
    cameras_router.init_router(manager)

    # Registra routers
    app.include_router(cameras_router.router, prefix="/api")
    app.include_router(reports_router.router, prefix="/api")
    app.include_router(ws_router.router)

    # Serve frontend estático
    frontend_dir = Path(__file__).parents[2] / "frontend"
    if frontend_dir.exists():
        app.mount("/", StaticFiles(directory=str(frontend_dir), html=True), name="frontend")

    return app
