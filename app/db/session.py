"""Async engine e session factory."""
from __future__ import annotations

from pathlib import Path
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.db.models import Base

_engine = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def _build_url(db_path: Path) -> str:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    return f"sqlite+aiosqlite:///{db_path}"


async def init_db(db_path: Path) -> None:
    """Cria engine, cria tabelas e inicializa session factory."""
    global _engine, _session_factory

    url = _build_url(db_path)
    _engine = create_async_engine(url, echo=False, future=True)
    _session_factory = async_sessionmaker(_engine, expire_on_commit=False)

    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def close_db() -> None:
    global _engine
    if _engine:
        await _engine.dispose()
        _engine = None


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency — sessão assíncrona por request."""
    if _session_factory is None:
        raise RuntimeError("DB não inicializado. Chame init_db() no startup.")
    async with _session_factory() as session:
        yield session


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    if _session_factory is None:
        raise RuntimeError("DB não inicializado.")
    return _session_factory
