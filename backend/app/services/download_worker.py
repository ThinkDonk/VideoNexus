"""下载任务 worker：调 WVP 倍速下载 → 轮询进度 → 从 ZLM 拉取 MP4 落盘 → 限时提供。

生命周期：PENDING → RUNNING → COMPLETE / FAILED；文件过期后 → EXPIRED。
所有状态迁移写审计。
"""
import asyncio
import logging
import time
from datetime import timedelta
from pathlib import Path

from sqlalchemy import select

from app.config import get_settings
from app.core.timezone import fmt_dt, now
from app.models import Channel, DownloadTask, User
from app.services import audit, wvp as wvp_service
from app.services.wvp import WvpError, with_zlm_secret, zlm_download_url

logger = logging.getLogger(__name__)

_running_tasks: dict[int, asyncio.Task] = {}


async def fetch_file_to_path(url: str, dest: Path) -> int:
    """流式下载文件到本地，返回字节数。（测试中会被替换）"""
    import httpx
    async with httpx.AsyncClient(timeout=httpx.Timeout(30, read=300)) as client:
        dest.parent.mkdir(parents=True, exist_ok=True)
        size = 0
        tmp = dest.with_suffix(".part")
        with open(tmp, "wb") as f:
            async with client.stream("GET", url) as resp:
                resp.raise_for_status()
                async for chunk in resp.aiter_bytes(512 * 1024):
                    f.write(chunk)
                    size += len(chunk)
        tmp.rename(dest)
        return size


async def _load_task_context(db, task: DownloadTask) -> tuple[Channel, User]:
    ch = (await db.execute(select(Channel).where(Channel.id == task.channel_id))).scalar_one()
    user = (await db.execute(select(User).where(User.id == task.user_id))).scalar_one()
    return ch, user


async def _update(db, task: DownloadTask, **fields) -> None:
    for k, v in fields.items():
        setattr(task, k, v)
    await db.flush()


async def run_download_task(task_id: int) -> None:
    """单个下载任务的执行协程（PENDING/RUNNING 均从此入口启动）。"""
    from app.core.db import _session_factory
    assert _session_factory is not None
    wvp = wvp_service.get_wvp()
    s = get_settings()

    async with _session_factory() as db:
        r = await db.execute(select(DownloadTask).where(DownloadTask.id == task_id))
        task = r.scalar_one_or_none()
        if task is None or task.status not in ("PENDING", "RUNNING"):
            return
        channel, user = await _load_task_context(db, task)
        start_str = fmt_dt(task.start_time)
        end_str = fmt_dt(task.end_time)
        task.status = "RUNNING"
        await db.commit()

        try:
            # 1. 发起 WVP 下载
            try:
                stream = await wvp.download_start(channel.device_id, channel.channel_id,
                                                  start_str, end_str, s.download_speed)
            except WvpError as e:
                raise RuntimeError(f"WVP 下载启动失败: {e}")
            stream_name = stream.get("stream") or ""
            if not stream_name:
                raise RuntimeError("WVP 未返回下载流标识")
            task.wvp_stream = stream_name
            await db.commit()
            await _audit(task, user, channel, audit.AuditAction.DOWNLOAD_START)

            # 2. 轮询进度
            file_url = await _poll_progress(wvp, db, task, channel, stream_name)

            # 3. 从 ZLM 拉取文件落盘
            dest = s.downloads_dir / f"{task.id}.mp4"
            real_url = with_zlm_secret(zlm_download_url(file_url))
            size = await fetch_file_to_path(real_url, dest)
            if size <= 0:
                raise RuntimeError("下载的文件为空")

            # 4. 完成
            task.status = "COMPLETE"
            task.progress = 100
            task.file_name = dest.name
            task.file_size = size
            task.completed_at = now()
            task.expires_at = now() + timedelta(days=s.file_retention_days)
            await db.commit()
            await _audit(task, user, channel, audit.AuditAction.DOWNLOAD_COMPLETE,
                         {"fileSize": size, "expiresAt": fmt_dt(task.expires_at)})
            logger.info("下载任务 %s 完成: %s 字节", task_id, size)

        except Exception as e:
            logger.exception("下载任务 %s 失败", task_id)
            task.status = "FAILED"
            task.error = str(e)[:500]
            await db.commit()
            await _audit(task, user, channel, audit.AuditAction.DOWNLOAD_FAIL,
                         {"error": str(e)[:200]}, result="fail")
        finally:
            _running_tasks.pop(task_id, None)


async def _poll_progress(wvp, db, task: DownloadTask, channel: Channel, stream_name: str) -> str:
    """轮询 WVP 下载进度，返回 ZLM 文件直链；期间持续更新 task.progress。"""
    s = get_settings()
    deadline = time.monotonic() + _max_wait_seconds(task)
    last_progress = -1
    while time.monotonic() < deadline:
        await asyncio.sleep(s.download_poll_seconds)
        try:
            data = await wvp.download_progress(channel.device_id, channel.channel_id, stream_name)
        except WvpError as e:
            # 偶发失败重试一次
            try:
                data = await wvp.download_progress(channel.device_id, channel.channel_id, stream_name)
            except WvpError:
                raise RuntimeError(f"查询下载进度失败: {e}")
        progress = data.get("progress")
        if isinstance(progress, (int, float)) and int(progress) != last_progress:
            last_progress = int(progress)
            task.progress = max(0, min(100, last_progress))
            await db.commit()
        dl = data.get("downLoadFilePath")
        if isinstance(dl, dict):
            url = dl.get("httpsPath") or dl.get("httpPath")
            if url:
                return url
        if progress == 100:
            # 部分版本完成后稍等一轮才出现 downLoadFilePath
            await asyncio.sleep(3)
            data = await wvp.download_progress(channel.device_id, channel.channel_id, stream_name)
            dl = data.get("downLoadFilePath")
            if isinstance(dl, dict):
                url = dl.get("httpsPath") or dl.get("httpPath")
                if url:
                    return url
            raise RuntimeError("进度 100% 但未取得文件地址")
    raise RuntimeError("下载超时未完成")


def _max_wait_seconds(task: DownloadTask) -> float:
    """等待上限 = 申请时长 / 倍速 + 30 分钟缓冲。"""
    s = get_settings()
    span = (task.end_time - task.start_time).total_seconds()
    return max(1800, span / max(1, s.download_speed) + 1800)


async def _audit(task: DownloadTask, user: User, channel: Channel, action: str,
                 extra: dict | None = None, result: str = "ok") -> None:
    """独立会话写审计：worker 主会话频繁 commit 进度，审计即时落库互不干扰。"""
    from app.core.db import _session_factory
    if _session_factory is None:
        return
    async with _session_factory() as db2:
        await audit.write(db2, action=action, user=user, object_type="download_task",
                          object_id=task.id,
                          params={"channel": channel.channel_id,
                                  "name": channel.display_name or channel.name,
                                  "startTime": fmt_dt(task.start_time),
                                  "endTime": fmt_dt(task.end_time),
                                  "progress": task.progress,
                                  "status": task.status, **(extra or {})})
        await db2.commit()


async def submit(task_id: int) -> None:
    """提交执行（幂等：同任务只起一个协程）。"""
    if task_id in _running_tasks and not _running_tasks[task_id].done():
        return
    _running_tasks[task_id] = asyncio.create_task(run_download_task(task_id))


async def recover_on_startup() -> None:
    """应用重启后：RUNNING/PENDING 的旧任务统一标记失败（WVP 侧会话已不可恢复）。"""
    from app.core.db import _session_factory
    if _session_factory is None:
        return
    async with _session_factory() as db:
        r = await db.execute(select(DownloadTask).where(DownloadTask.status.in_(["PENDING", "RUNNING"])))
        for task in r.scalars().all():
            task.status = "FAILED"
            task.error = "门户服务重启导致任务中断，请重新发起"
            await db.commit()
            user = (await db.execute(select(User).where(User.id == task.user_id))).scalar_one_or_none()
            channel = (await db.execute(select(Channel).where(Channel.id == task.channel_id))).scalar_one_or_none()
            if user and channel:
                await _audit(task, user, channel, audit.AuditAction.DOWNLOAD_FAIL,
                            {"error": task.error}, result="fail")
        logger.info("启动恢复：中断的下载任务已标记失败")


async def cleanup_expired_files() -> int:
    """定时任务：删除过期文件并置 EXPIRED。"""
    from app.core.db import _session_factory
    if _session_factory is None:
        return 0
    s = get_settings()
    n = 0
    async with _session_factory() as db:
        r = await db.execute(
            select(DownloadTask).where(DownloadTask.status == "COMPLETE",
                                       DownloadTask.expires_at.is_not(None),
                                       DownloadTask.expires_at <= now())
        )
        for task in r.scalars().all():
            if task.file_name:
                p = s.downloads_dir / task.file_name
                if p.exists():
                    p.unlink(missing_ok=True)
            task.status = "EXPIRED"
            await db.commit()
            user = (await db.execute(select(User).where(User.id == task.user_id))).scalar_one_or_none()
            channel = (await db.execute(select(Channel).where(Channel.id == task.channel_id))).scalar_one_or_none()
            if user and channel:
                await _audit(task, user, channel, audit.AuditAction.DOWNLOAD_EXPIRED)
            n += 1
    if n:
        logger.info("已清理过期下载文件 %s 个", n)
    return n


async def org_quota_used_gb(db) -> float:
    """全站下载文件占用（GB）——按机构配额校验用。"""
    from sqlalchemy import func
    from app.models import DownloadTask
    r = await db.execute(
        select(func.coalesce(func.sum(DownloadTask.file_size), 0)).where(
            DownloadTask.status == "COMPLETE")
    )
    return (r.scalar_one() or 0) / (1024 ** 3)
