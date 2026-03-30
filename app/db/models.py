"""ORM models (SQLAlchemy 2.x declarativo)."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Float, Integer, String, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class CountEvent(Base):
    """Registro de um cruzamento de linha (entrada ou saída)."""

    __tablename__ = "count_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    camera_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    direction: Mapped[str] = mapped_column(String(8), nullable=False)  # "in" | "out"
    track_id: Mapped[int] = mapped_column(Integer, nullable=False)
    dwell_duration_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class DailySummary(Base):
    """Resumo diário por câmera e período (calculado pelo scheduler)."""

    __tablename__ = "daily_summaries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    camera_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    date: Mapped[str] = mapped_column(String(10), nullable=False)  # YYYY-MM-DD
    period_name: Mapped[str] = mapped_column(String(64), nullable=False)
    count_in: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    count_out: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    peak_occupancy: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    avg_dwell_minutes: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
