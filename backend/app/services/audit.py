"""审计服务：全站唯一的审计写入入口，只 INSERT，永不 UPDATE/DELETE。

动作常量集中在这里，便于与银行的合规字段清单对照。
"""
import json
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AuditLog, Org, User


class AuditAction:
    # 登录类
    LOGIN_SUCCESS = "LOGIN_SUCCESS"
    LOGIN_FAIL = "LOGIN_FAIL"
    LOGIN_LOCKED = "LOGIN_LOCKED"
    LOGOUT = "LOGOUT"
    PASSWORD_CHANGE = "PASSWORD_CHANGE"
    # 视频类
    PLAY_START = "PLAY_START"
    PLAY_END = "PLAY_END"
    PLAYBACK_START = "PLAYBACK_START"
    PLAYBACK_END = "PLAYBACK_END"
    RECORD_QUERY = "RECORD_QUERY"
    DOWNLOAD_CREATE = "DOWNLOAD_CREATE"
    DOWNLOAD_START = "DOWNLOAD_START"
    DOWNLOAD_COMPLETE = "DOWNLOAD_COMPLETE"
    DOWNLOAD_FAIL = "DOWNLOAD_FAIL"
    DOWNLOAD_EXPIRED = "DOWNLOAD_EXPIRED"
    DOWNLOAD_FILE_FETCH = "DOWNLOAD_FILE_FETCH"
    # 授权类（追责关键）
    GRANT_ADDED = "GRANT_ADDED"
    GRANT_UPDATED = "GRANT_UPDATED"
    GRANT_REMOVED = "GRANT_REMOVED"
    # 管理类
    ORG_CREATED = "ORG_CREATED"
    ORG_UPDATED = "ORG_UPDATED"
    ORG_DELETED = "ORG_DELETED"
    USER_CREATED = "USER_CREATED"
    USER_UPDATED = "USER_UPDATED"
    PASSWORD_RESET = "PASSWORD_RESET"
    CHANNEL_SYNC = "CHANNEL_SYNC"
    CHANNEL_UPDATED = "CHANNEL_UPDATED"
    STREAM_AUTH_FAIL = "STREAM_AUTH_FAIL"  # 疑似播放地址外泄/越权拉流


async def write(
    db: AsyncSession,
    *,
    action: str,
    user: User | None = None,
    username: str | None = None,
    object_type: str | None = None,
    object_id: str | int | None = None,
    params: dict[str, Any] | None = None,
    result: str = "ok",
    ip: str | None = None,
    ua: str | None = None,
) -> None:
    """写一条审计。调用方负责最终 commit（get_db 依赖在请求成功时提交）。"""
    org_name = None
    if user is not None and user.org_id is not None:
        r = await db.execute(select(Org).where(Org.id == user.org_id))
        org = r.scalar_one_or_none()
        org_name = org.name if org else None

    entry = AuditLog(
        user_id=user.id if user else None,
        username=username or (user.username if user else None),
        org_id=user.org_id if user else None,
        org_name=org_name,
        action=action,
        object_type=object_type,
        object_id=str(object_id) if object_id is not None else None,
        params=json.dumps(params, ensure_ascii=False, default=str) if params else None,
        result=result,
        ip=ip,
        ua=(ua[:255] if ua else None),
    )
    db.add(entry)
