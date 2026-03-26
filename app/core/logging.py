"""Configuração de logging com Loguru."""
from __future__ import annotations

import sys
from pathlib import Path

from loguru import logger


def setup_logging(level: str = "INFO", retention_days: int = 30) -> None:
    """Configura handlers de console e arquivo com rotação."""
    logger.remove()

    # Console — colorido e legível
    logger.add(
        sys.stderr,
        level=level,
        format=(
            "<green>{time:HH:mm:ss}</green> | "
            "<level>{level: <8}</level> | "
            "<cyan>{name}</cyan>:<cyan>{line}</cyan> — <level>{message}</level>"
        ),
        colorize=True,
    )

    # Arquivo — com rotação diária e retenção configurável
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)

    logger.add(
        log_dir / "contador.log",
        level=level,
        rotation="00:00",
        retention=f"{retention_days} days",
        compression="gz",
        encoding="utf-8",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{line} — {message}",
    )

    logger.info("Logging configurado: level={}, retenção={}d", level, retention_days)
