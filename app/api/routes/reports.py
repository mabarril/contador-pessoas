"""Rotas REST — relatórios históricos."""
from __future__ import annotations

from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.repository import CountEventRepository, DailySummaryRepository
from app.db.session import get_session

router = APIRouter(prefix="/reports", tags=["reports"])


@router.get("/{camera_id}/today")
async def today_counts(camera_id: str, db: AsyncSession = Depends(get_session)):
    """Totais de entrada/saída de hoje para uma câmera."""
    repo = CountEventRepository(db)
    counts = await repo.count_by_camera_today(camera_id)
    count_in = counts.get("in", 0)
    count_out = counts.get("out", 0)
    return {
        "camera_id": camera_id,
        "date": date.today().isoformat(),
        "count_in": count_in,
        "count_out": count_out,
        "inside": max(0, count_in - count_out),
    }


@router.get("/{camera_id}/hourly")
async def hourly_report(camera_id: str, db: AsyncSession = Depends(get_session)):
    """Contagens agrupadas por hora para hoje."""
    repo = CountEventRepository(db)
    data = await repo.hourly_counts(camera_id, date.today())
    return {"camera_id": camera_id, "data": data}


@router.get("/{camera_id}/summaries")
async def daily_summaries(
    camera_id: str,
    days: int = 7,
    db: AsyncSession = Depends(get_session),
):
    """Resumos diários dos últimos N dias."""
    if days < 1 or days > 365:
        raise HTTPException(status_code=400, detail="days deve estar entre 1 e 365.")
    repo = DailySummaryRepository(db)
    summaries = await repo.get_by_camera(camera_id, days)
    return {
        "camera_id": camera_id,
        "data": [
            {
                "date": s.date,
                "period": s.period_name,
                "count_in": s.count_in,
                "count_out": s.count_out,
                "peak_occupancy": s.peak_occupancy,
            }
            for s in summaries
        ],
    }
