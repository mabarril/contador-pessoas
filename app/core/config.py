"""Carregamento e validação da configuração via Pydantic + YAML."""
from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field, field_validator


# ---------------------------------------------------------------------------
# Sub-models
# ---------------------------------------------------------------------------


class ServerConfig(BaseModel):
    host: str = "0.0.0.0"
    port: int = 8000


class ModelConfig(BaseModel):
    path: Path = Path("models/yolov8n.pt")
    confidence_threshold: float = Field(0.5, ge=0.0, le=1.0)
    input_resolution: tuple[int, int] = (640, 480)
    skip_frames: int = Field(2, ge=1)


class CountingLineConfig(BaseModel):
    orientation: Literal["vertical", "horizontal"] = "vertical"
    position: float = Field(0.5, ge=0.0, le=1.0)
    direction_in: Literal["right", "left", "down", "up"] = "right"


class CameraConfig(BaseModel):
    id: str
    name: str
    type: Literal["usb", "rtsp", "file"] = "usb"
    source: str | int = 0
    counting_line: CountingLineConfig = CountingLineConfig()

    @field_validator("source", mode="before")
    @classmethod
    def coerce_source(cls, v: object) -> str | int:
        if isinstance(v, str) and v.isdigit():
            return int(v)
        return v  # type: ignore[return-value]


class DatabaseConfig(BaseModel):
    path: Path = Path("data/contador.db")


class PeriodConfig(BaseModel):
    name: str
    start: str  # "HH:MM"
    end: str  # "HH:MM"


class ReportsConfig(BaseModel):
    periods: list[PeriodConfig] = []


class LoggingConfig(BaseModel):
    level: str = "INFO"
    retention_days: int = 30


class AppConfig(BaseModel):
    server: ServerConfig = ServerConfig()
    model: ModelConfig = ModelConfig()
    cameras: list[CameraConfig] = []
    database: DatabaseConfig = DatabaseConfig()
    reports: ReportsConfig = ReportsConfig()
    logging: LoggingConfig = LoggingConfig()


# ---------------------------------------------------------------------------
# Loader
# ---------------------------------------------------------------------------

_CONFIG_PATH = Path(__file__).parents[2] / "config.yaml"
_config: AppConfig | None = None


def load_config(path: Path | None = None) -> AppConfig:
    """Carrega (ou retorna cached) a configuração da aplicação."""
    global _config
    if _config is not None:
        return _config

    cfg_path = path or _CONFIG_PATH
    if cfg_path.exists():
        raw = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
    else:
        raw = {}

    _config = AppConfig.model_validate(raw)
    return _config


def get_config() -> AppConfig:
    """FastAPI dependency — retorna a config carregada."""
    return load_config()
