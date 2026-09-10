"""后台定时任务：通道同步、播放会话清理、下载文件清理。"""
import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.config import get_settings

logger = logging.getLogger(__name__)
scheduler = AsyncIOScheduler(timezone=get_settings().tz)


def setup_jobs() -> AsyncIOScheduler:
    from app.services.channel_sync import sync_job
    from app.services.download_worker import cleanup_expired_files
    from app.services.play_service import cleanup_expired_sessions

    async def _cleanup_sessions_job() -> None:
        from app.core.db import _session_factory
        if _session_factory is None:
            return
        try:
            async with _session_factory() as db:
                await cleanup_expired_sessions(db)
                await db.commit()
        except Exception:
            logger.exception("播放会话清理失败")

    async def _cleanup_files_job() -> None:
        try:
            await cleanup_expired_files()
        except Exception:
            logger.exception("下载文件清理失败")

    s = get_settings()
    scheduler.add_job(sync_job, "interval", minutes=s.channel_sync_minutes,
                       id="channel_sync", max_instances=1, coalesce=True)
    scheduler.add_job(_cleanup_sessions_job, "interval", minutes=10,
                       id="cleanup_sessions", max_instances=1, coalesce=True)
    scheduler.add_job(_cleanup_files_job, "interval", hours=1,
                       id="cleanup_files", max_instances=1, coalesce=True)
    return scheduler
