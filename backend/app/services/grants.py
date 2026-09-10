"""授权校验：所有视频操作（实时/回放/下载）在服务端执行的唯一入口。"""
from datetime import datetime

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Channel, ChannelGrant, User


class GrantDenied(HTTPException):
    def __init__(self, detail: str = "无该通道的访问授权"):
        super().__init__(status_code=403, detail=detail)


async def get_channel_or_404(db: AsyncSession, channel_pk: int) -> Channel:
    r = await db.execute(select(Channel).where(Channel.id == channel_pk))
    ch = r.scalar_one_or_none()
    if ch is None:
        raise HTTPException(status_code=404, detail="通道不存在")
    return ch


def _in_window(g: ChannelGrant, now: datetime) -> bool:
    if g.valid_from and now < g.valid_from:
        return False
    if g.valid_until and now > g.valid_until:
        return False
    return True


async def get_grant(db: AsyncSession, user: User, channel_pk: int) -> ChannelGrant | None:
    r = await db.execute(
        select(ChannelGrant).where(
            ChannelGrant.user_id == user.id, ChannelGrant.channel_id == channel_pk
        )
    )
    return r.scalar_one_or_none()


async def require_grant(db: AsyncSession, user: User, channel_pk: int, action: str) -> ChannelGrant:
    """action: live / playback / download。ADMIN 视为拥有全部通道权限（不含有效期限制）。"""
    from app.core.timezone import now
    if user.role == "ADMIN":
        return ChannelGrant(user_id=user.id, channel_id=channel_pk,
                            can_live=True, can_playback=True, can_download=True)
    grant = await get_grant(db, user, channel_pk)
    field = {"live": "can_live", "playback": "can_playback", "download": "can_download"}[action]
    if grant is None or not getattr(grant, field):
        raise GrantDenied()
    if not _in_window(grant, now()):
        raise GrantDenied("授权已过期或未生效")
    return grant


async def org_play_limit_reached(db: AsyncSession, user: User) -> bool:
    """机构同时在线播放路数上限（含当前用户已有活动会话）。"""
    from sqlalchemy import func
    from app.core.timezone import now
    from app.models import Org, PlaySession
    if user.org_id is None:
        return False
    r = await db.execute(select(Org).where(Org.id == user.org_id))
    org = r.scalar_one_or_none()
    if org is None:
        return False
    r2 = await db.execute(
        select(func.count(PlaySession.id)).where(
            PlaySession.ended_at.is_(None), PlaySession.expires_at > now()
        ).join(User, User.id == PlaySession.user_id).where(User.org_id == org.id)
    )
    count = r2.scalar_one()
    return count >= org.max_concurrent_plays
