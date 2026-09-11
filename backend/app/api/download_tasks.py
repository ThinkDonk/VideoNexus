"""下载任务：创建/列表/详情/文件下载。"""
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.core.db import get_db
from app.core.deps import client_ip, get_current_user
from app.core.timezone import fmt_dt, now, parse_dt
from app.models import Channel, DownloadTask, Org, User
from app.schemas import DownloadCreateRequest, DownloadTaskInfo
from app.services import audit, download_worker
from app.services.audit import AuditAction
from app.services.grants import get_channel_or_404, require_grant

router = APIRouter(prefix="/api/download-tasks", tags=["download"])


def _task_info(task: DownloadTask, channel: Channel | None = None, user: User | None = None,
               org: Org | None = None) -> DownloadTaskInfo:
    return DownloadTaskInfo(
        id=task.id,
        channelId=task.channel_id,
        channelName=(channel.display_name or channel.name) if channel else None,
        channelGbId=channel.channel_id if channel else None,
        username=user.username if user else None,
        orgName=org.name if org else None,
        startTime=fmt_dt(task.start_time) or "",
        endTime=fmt_dt(task.end_time) or "",
        status=task.status,
        progress=task.progress,
        fileSize=task.file_size,
        expiresAt=fmt_dt(task.expires_at),
        error=task.error,
        createdAt=fmt_dt(task.created_at),
        completedAt=fmt_dt(task.completed_at),
    )


async def _load_related(db: AsyncSession, tasks: list[DownloadTask]) -> list[DownloadTaskInfo]:
    infos = []
    for t in tasks:
        channel = (await db.execute(select(Channel).where(Channel.id == t.channel_id))).scalar_one_or_none()
        user = (await db.execute(select(User).where(User.id == t.user_id))).scalar_one_or_none()
        org = None
        if user and user.org_id:
            org = (await db.execute(select(Org).where(Org.id == user.org_id))).scalar_one_or_none()
        infos.append(_task_info(t, channel, user, org))
    return infos


@router.post("", status_code=201)
async def create_task(body: DownloadCreateRequest, request: Request,
                      user: User = Depends(get_current_user),
                      db: AsyncSession = Depends(get_db)):
    s = get_settings()
    channel = await get_channel_or_404(db, body.channelId)
    await require_grant(db, user, body.channelId, "download")
    try:
        start, end = parse_dt(body.startTime), parse_dt(body.endTime)
    except ValueError:
        raise HTTPException(status_code=400, detail="时间格式应为 yyyy-MM-dd HH:mm:ss")
    if start >= end:
        raise HTTPException(status_code=400, detail="开始时间必须早于结束时间")
    if (end - start).total_seconds() > s.download_max_duration_hours * 3600:
        raise HTTPException(status_code=400,
                            detail=f"单次下载时间段不能超过 {s.download_max_duration_hours} 小时")

    r = await db.execute(select(func.count(DownloadTask.id)).where(
        DownloadTask.user_id == user.id, DownloadTask.status.in_(["PENDING", "RUNNING"])))
    if r.scalar_one() >= s.download_max_running_per_user:
        raise HTTPException(status_code=429, detail="进行中的下载任务数已达上限")

    task = DownloadTask(user_id=user.id, channel_id=channel.id,
                        start_time=start, end_time=end, status="PENDING")
    db.add(task)
    await db.flush()

    await audit.write(db, action=AuditAction.DOWNLOAD_CREATE, user=user,
                      object_type="download_task", object_id=task.id,
                      params={"channel": channel.channel_id,
                              "name": channel.display_name or channel.name,
                              "startTime": body.startTime, "endTime": body.endTime},
                      ip=client_ip(request), ua=request.headers.get("user-agent"))
    await db.commit()  # 先落库拿到 task.id，再提交协程
    await download_worker.submit(task.id)
    return _task_info(task, channel, user)


@router.get("")
async def list_my_tasks(user: User = Depends(get_current_user),
                        db: AsyncSession = Depends(get_db)):
    r = await db.execute(
        select(DownloadTask).where(DownloadTask.user_id == user.id)
        .order_by(DownloadTask.id.desc()).limit(100))
    return await _load_related(db, list(r.scalars().all()))


@router.get("/{task_id}")
async def get_task(task_id: int, user: User = Depends(get_current_user),
                  db: AsyncSession = Depends(get_db)):
    r = await db.execute(select(DownloadTask).where(
        DownloadTask.id == task_id, DownloadTask.user_id == user.id))
    task = r.scalar_one_or_none()
    if task is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    infos = await _load_related(db, [task])
    return infos[0]


@router.get("/{task_id}/file")
async def download_file(task_id: int, request: Request, response: Response,
                        user: User = Depends(get_current_user),
                        db: AsyncSession = Depends(get_db)):
    r = await db.execute(select(DownloadTask).where(
        DownloadTask.id == task_id, DownloadTask.user_id == user.id))
    task = r.scalar_one_or_none()
    if task is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    if task.status != "COMPLETE" or not task.file_name:
        raise HTTPException(status_code=400, detail="任务未完成")
    if task.expires_at and now() > task.expires_at:
        raise HTTPException(status_code=410, detail="文件已过期")

    await audit.write(db, action=AuditAction.DOWNLOAD_FILE_FETCH, user=user,
                      object_type="download_task", object_id=task.id,
                      params={"fileSize": task.file_size},
                      ip=client_ip(request), ua=request.headers.get("user-agent"))

    channel = (await db.execute(select(Channel).where(Channel.id == task.channel_id))).scalar_one_or_none()
    filename = f"{channel.display_name or channel.name or 'record'}_{task.id}.mp4" if channel else f"{task.id}.mp4"
    # Content-Disposition 需符合 RFC 6266：HTTP 头只能 latin-1 编码，
    # 中文文件名用 filename*=UTF-8'' 传输，filename 字段退化为 ASCII 兜底名。
    fallback = filename if filename.isascii() else f"download_{task.id}.mp4"
    disposition = (f'attachment; filename="{fallback}"; '
                   f"filename*=UTF-8''{quote(filename, safe='')}")

    # 本地开发模式（无 Nginx）：后端直接流式发送文件（无限速）
    if get_settings().dev_stream_proxy:
        from fastapi.responses import FileResponse
        file_path = get_settings().downloads_dir / task.file_name
        if not file_path.exists():
            raise HTTPException(status_code=410, detail="文件已丢失或被清理")
        return FileResponse(file_path, media_type="video/mp4",
                            headers={"Content-Disposition": disposition})

    # 生产：空响应体 + X-Accel-Redirect，由 Nginx internal location 限速发送真实文件。
    return Response(status_code=200, headers={
        "X-Accel-Redirect": f"/protected-download/{task.file_name}",
        "Content-Disposition": disposition,
        "Content-Type": "video/mp4",
    })
