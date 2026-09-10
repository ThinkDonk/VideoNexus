"""VideoNexus 门户后端入口。

启动流程：初始化引擎/表结构 → 引导管理员 → 启动 WVP 客户端与定时任务 → 恢复中断的下载任务。
"""
import asyncio
import logging
import secrets

from fastapi import FastAPI
from sqlalchemy import select

from app.api import admin, auth, channels, download_tasks, internal, play, playback
from app.config import get_settings
from app.core.db import close_engine, create_all, get_engine, init_engine
from app.core.security import hash_password
from app.core.timezone import now
from app.models import User
from app.services import download_worker
from app.services.wvp import get_wvp

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)


async def bootstrap_admin() -> None:
    """首次启动创建管理员；未配置密码则随机生成并打印一次。"""
    from app.core.db import _session_factory
    assert _session_factory is not None
    async with _session_factory() as db:
        r = await db.execute(select(User).where(User.role == "ADMIN").limit(1))
        if r.scalar_one_or_none() is not None:
            return
        s = get_settings()
        password = s.initial_admin_password or secrets.token_urlsafe(12)
        db.add(User(username=s.initial_admin_username, password_hash=hash_password(password),
                    display_name="系统管理员", role="ADMIN", must_change_password=True,
                    created_at=now(), updated_at=now()))
        await db.commit()
        if s.initial_admin_password:
            logger.warning("已创建初始管理员 %s（密码来自 INITIAL_ADMIN_PASSWORD，首次登录需修改）",
                           s.initial_admin_username)
        else:
            logger.warning("已创建初始管理员 %s，初始密码: %s （仅显示一次，请立即登录修改）",
                           s.initial_admin_username, password)


def create_app() -> FastAPI:
    app = FastAPI(title="VideoNexus 门户", docs_url=None, redoc_url=None, openapi_url=None)

    @app.on_event("startup")
    async def _startup() -> None:
        s = get_settings()
        engine = init_engine(s.effective_database_url)
        await create_all(engine)
        await bootstrap_admin()
        wvp = get_wvp()
        await wvp.start()
        from app.core.scheduler import setup_jobs
        setup_jobs().start()
        await download_worker.recover_on_startup()
        logger.info("VideoNexus 后端启动完成 (data_dir=%s)", s.data_dir)

    @app.on_event("shutdown")
    async def _shutdown() -> None:
        from app.core.scheduler import scheduler
        if scheduler.running:
            scheduler.shutdown(wait=False)
        await get_wvp().close()
        await close_engine()

    app.include_router(auth.router)
    app.include_router(channels.router)
    app.include_router(play.router)
    app.include_router(playback.router)
    app.include_router(download_tasks.router)
    app.include_router(admin.router)
    app.include_router(admin.write_router)
    app.include_router(internal.router)
    return app


app = create_app()
