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
    """等待下载完成并返回 ZLM 文件直链。

    完成判定（按优先级）：
      A. progress 响应携带 downLoadFilePath（WVP 主动给出直链）
      B. progress 报"资源未找到"（WVP 已按请求倍速的估算时长拆除会话——设备实际可能
         仍按 1 倍速在传）后，轮询云端录像表：on_record_mp4 完成入库，该流出现
         task 开始之后的新文件即为最终 MP4
    注意：WVP 的 progress 是按"请求倍速"估算的（设备忽略倍速时会虚高），仅用于展示。
    """
    s = get_settings()
    deadline = time.monotonic() + _max_wait_seconds(task)
    task_started_ms = time.time() * 1000 - 60_000  # 云端录像 startTime 对齐窗口（毫秒）
    session_gone = False
    last_pct = -1

    while time.monotonic() < deadline:
        await asyncio.sleep(s.download_poll_seconds)

        if not session_gone:
            try:
                data = await wvp.download_progress(channel.device_id, channel.channel_id, stream_name)
            except WvpError as e:
                if "资源未找到" in str(e) or e.code == 404:
                    session_gone = True
                    continue
                try:  # 偶发失败重试一次
                    data = await wvp.download_progress(channel.device_id, channel.channel_id, stream_name)
                except WvpError as e2:
                    if "资源未找到" in str(e2) or e2.code == 404:
                        session_gone = True
                        continue
                    raise RuntimeError(f"查询下载进度失败: {e2}")
            progress = data.get("progress")
            if isinstance(progress, (int, float)):
                pct = max(0, min(99, round(float(progress) * 100)))
                if pct != last_pct:
                    last_pct = pct
                    task.progress = pct
                    await db.commit()
            dl = data.get("downLoadFilePath")
            if isinstance(dl, dict):
                url = dl.get("httpsPath") or dl.get("httpPath")
                if url:
                    return url
            continue

        # 会话已结束：等待云端录像表出现本任务开始后的新文件（文件写完即入库）
        rec = await _find_cloud_record(wvp, stream_name, task_started_ms)
        if rec:
            return rec

    raise RuntimeError("下载超时未完成（未等到录像文件入库）")


async def _find_cloud_record(wvp, stream_name: str, started_after_ms: float) -> str | None:
    """在云端录像中找 stream_name 本次任务开始后完成的新文件，返回 downloadFile 直链。"""
    from app.config import get_settings
    try:
        data = await wvp.cloud_record_list("rtp", stream_name)
    except WvpError:
        return None
    candidates = []
    for item in (data.get("list") or []):
        try:
            st = int(item.get("startTime") or 0)
        except (TypeError, ValueError):
            continue
        if st >= started_after_ms and item.get("filePath"):
            candidates.append((st, item["filePath"]))
    if not candidates:
        return None
    file_path = max(candidates)[1]
    s = get_settings()
    base = (s.zlm_download_base_url or "").rstrip("/")
    if not base:
        return None
    from urllib.parse import urlencode
    params = {"file_path": file_path}
    if s.zlm_secret:
        params["secret"] = s.zlm_secret
    return f"{base}/index/api/downloadFile?{urlencode(params)}"


def _max_wait_seconds(task: DownloadTask) -> float:
    """等待上限 = 录像时长（设备可能忽略倍速按 1 倍速传输）+ 30 分钟缓冲。"""
    span = (task.end_time - task.start_time).total_seconds()
    return max(1800, span + 1800)


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
