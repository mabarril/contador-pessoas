"""Data access layer — operações assíncronas no banco."""
from __future__ import annotations

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import CountEvent, DailySummary


class CountEventRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(
        self,
        camera_id: str,
        direction: str,
        track_id: int,
        timestamp: datetime | None = None,
        dwell_duration: float | None = None,
    ) -> CountEvent:
        event = CountEvent(
            camera_id=camera_id,
            direction=direction,
            track_id=track_id,
            dwell_duration_seconds=dwell_duration,
            timestamp=timestamp or datetime.now(tz=ZoneInfo("America/Sao_Paulo")),
        )
        self._session.add(event)
        await self._session.commit()
        return event

    async def count_by_camera_today(self, camera_id: str) -> dict[str, int]:
        """Retorna totais de in/out de hoje para uma câmera."""
        today_start = datetime.now(tz=ZoneInfo("America/Sao_Paulo")).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        stmt = (
            select(CountEvent.direction, func.count().label("total"))
            .where(
                CountEvent.camera_id == camera_id,
                CountEvent.timestamp >= today_start,
            )
            .group_by(CountEvent.direction)
        )
        rows = (await self._session.execute(stmt)).all()
        return {row.direction: row.total for row in rows}

    async def events_in_range(
        self,
        camera_id: str,
        start: datetime,
        end: datetime,
    ) -> list[CountEvent]:
        stmt = (
            select(CountEvent)
            .where(
                CountEvent.camera_id == camera_id,
                CountEvent.timestamp >= start,
                CountEvent.timestamp < end,
            )
            .order_by(CountEvent.timestamp)
        )
        return list((await self._session.execute(stmt)).scalars().all())

    async def hourly_counts(
        self,
        camera_id: str,
        target_date: date,
    ) -> list[dict]:
        """Retorna contagens agrupadas por hora (para gráficos)."""
        start = datetime(
            target_date.year, target_date.month, target_date.day,
            tzinfo=ZoneInfo("America/Sao_Paulo")
        )
        end = start + timedelta(days=1)

        events = await self.events_in_range(camera_id, start, end)
        hourly: dict[int, dict[str, int]] = {h: {"in": 0, "out": 0} for h in range(24)}
        for e in events:
            h = e.timestamp.hour
            hourly[h][e.direction] = hourly[h].get(e.direction, 0) + 1

        return [{"hour": h, **counts} for h, counts in sorted(hourly.items())]


class DailySummaryRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def upsert(self, summary: DailySummary) -> None:
        existing = await self._session.scalar(
            select(DailySummary).where(
                DailySummary.camera_id == summary.camera_id,
                DailySummary.date == summary.date,
                DailySummary.period_name == summary.period_name,
            )
        )
        if existing:
            existing.count_in = summary.count_in
            existing.count_out = summary.count_out
            existing.peak_occupancy = summary.peak_occupancy
            existing.avg_dwell_minutes = summary.avg_dwell_minutes
        else:
            self._session.add(summary)
        await self._session.commit()

    async def get_by_camera(
        self,
        camera_id: str,
        days: int = 7,
    ) -> list[DailySummary]:
        cutoff = (datetime.now(tz=ZoneInfo("America/Sao_Paulo")) - timedelta(days=days)).strftime(
            "%Y-%m-%d"
        )
        stmt = (
            select(DailySummary)
            .where(
                DailySummary.camera_id == camera_id,
                DailySummary.date >= cutoff,
            )
            .order_by(DailySummary.date, DailySummary.period_name)
        )
        return list((await self._session.execute(stmt)).scalars().all())
