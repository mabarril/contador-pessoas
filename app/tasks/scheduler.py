"""APScheduler — tarefas periódicas (relatórios diários etc.)."""
from __future__ import annotations

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from loguru import logger

from app.core.config import AppConfig
from app.db.models import DailySummary
from app.db.repository import CountEventRepository, DailySummaryRepository
from app.db.session import get_session_factory
from app.services.manager import CameraManager


def build_scheduler(config: AppConfig, manager: CameraManager) -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler(timezone="America/Sao_Paulo")

    # Gera resumos diários às 00:05 (para pegar todo o dia anterior)
    scheduler.add_job(
        _generate_daily_summaries,
        trigger="cron",
        hour=0,
        minute=5,
        args=[config, manager],
        id="daily_summaries",
        replace_existing=True,
    )

    # Reseta contadores em memória exatamente na virada do dia (00:00)
    scheduler.add_job(
        _reset_daily_counters,
        trigger="cron",
        hour=0,
        minute=0,
        args=[manager],
        id="daily_reset",
        replace_existing=True,
    )

    return scheduler


async def _reset_daily_counters(manager: CameraManager) -> None:
    """Zera contadores em memória na virada do dia."""
    logger.info("Executando resete diário dos contadores...")
    manager.reset_all_counts()


async def _generate_daily_summaries(config: AppConfig, manager: CameraManager) -> None:
    """Calcula e persiste resumos do dia anterior por câmera e período."""
    yesterday = (datetime.now(tz=ZoneInfo("America/Sao_Paulo")) - timedelta(days=1)).date()
    logger.info("Gerando resumos para {}", yesterday)

    factory = get_session_factory()

    for cam_cfg in config.cameras:
        for period in config.reports.periods:
            try:
                period_start = datetime.combine(
                    yesterday,
                    datetime.strptime(period.start, "%H:%M").time(),
                    tzinfo=ZoneInfo("America/Sao_Paulo"),
                )
                period_end = datetime.combine(
                    yesterday,
                    datetime.strptime(period.end, "%H:%M").time(),
                    tzinfo=ZoneInfo("America/Sao_Paulo"),
                )

                async with factory() as session:
                    event_repo = CountEventRepository(session)
                    events = await event_repo.events_in_range(
                        cam_cfg.id, period_start, period_end
                    )

                    count_in = sum(1 for e in events if e.direction == "in")
                    count_out = sum(1 for e in events if e.direction == "out")

                    # Metodologia FIFO: média das durações registradas nos eventos "out"
                    out_durations = [
                        e.dwell_duration_seconds 
                        for e in events 
                        if e.direction == "out" and e.dwell_duration_seconds is not None
                    ]
                    avg_dwell_min = 0.0
                    if out_durations:
                        avg_dwell_min = (sum(out_durations) / len(out_durations)) / 60.0

                    # Estimativa de pico de ocupação
                    occupancy = 0
                    peak = 0
                    for e in events:
                        occupancy += 1 if e.direction == "in" else -1
                        peak = max(peak, occupancy)

                    summary = DailySummary(
                        camera_id=cam_cfg.id,
                        date=yesterday.strftime("%Y-%m-%d"),
                        period_name=period.name,
                        count_in=count_in,
                        count_out=count_out,
                        peak_occupancy=peak,
                        avg_dwell_minutes=avg_dwell_min,
                    )

                    summary_repo = DailySummaryRepository(session)
                    await summary_repo.upsert(summary)

                logger.info(
                    "[{}] Resumo {}/{}: in={}, out={}, pico={}",
                    cam_cfg.id,
                    yesterday,
                    period.name,
                    count_in,
                    count_out,
                    peak,
                )
            except Exception:
                logger.exception(
                    "Erro ao gerar resumo [{}/{}]", cam_cfg.id, period.name
                )
