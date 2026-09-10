"""数据库引擎与会话。SQLite 需开启 WAL 与 busy_timeout 以支持并发读。"""
from collections.abc import AsyncIterator

from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def init_engine(database_url: str) -> AsyncEngine:
    global _engine, _session_factory
    _engine = create_async_engine(database_url, poolclass=NullPool, echo=False)
    if database_url.startswith("sqlite"):

        @event.listens_for(_engine.sync_engine, "connect")
        def _set_sqlite_pragma(dbapi_connection, _):
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA busy_timeout=10000")
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()
    _session_factory = async_sessionmaker(_engine, expire_on_commit=False)
    return _engine


def get_engine() -> AsyncEngine:
    if _engine is None:
        raise RuntimeError("数据库引擎未初始化（init_engine 未调用）")
    return _engine


async def close_engine() -> None:
    global _engine, _session_factory
    if _engine is not None:
        await _engine.dispose()
    _engine = None
    _session_factory = None


async def get_db() -> AsyncIterator[AsyncSession]:
    """FastAPI 依赖：每请求一个会话，提交或回滚后关闭。"""
    if _session_factory is None:
        raise RuntimeError("数据库会话工厂未初始化")
    async with _session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def create_all(engine: AsyncEngine) -> None:
    from app.models import Base  # noqa: 延迟导入避免循环
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # 审计表是 append-only 语义的最后一道兜底：SQLite 无法做库内权限，MySQL 阶段由 DB 账号权限保证
        await conn.execute(text("SELECT 1"))
