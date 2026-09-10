"""实时点播：/api/play/{channelId} 与 stop。"""
from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.deps import client_ip, get_current_user
from app.models import PlaySession, User
from app.schemas import PlayStartResponse
from app.services import play_service
from app.services.grants import get_channel_or_404, require_grant

router = APIRouter(prefix="/api/play", tags=["play"])


def _host(request: Request) -> str:
    # 部署形态下 Nginx 会透传 Host；本地直连时取请求 host
    return request.headers.get("host") or request.url.netloc


@router.post("/{channel_id}", response_model=PlayStartResponse)
async def start_play(channel_id: int, request: Request,
                     user: User = Depends(get_current_user),
                     db: AsyncSession = Depends(get_db)):
    channel = await get_channel_or_404(db, channel_id)
    await require_grant(db, user, channel_id, "live")
    session = await play_service.start_live(
        db, user, channel, _host(request), client_ip(request),
        request.headers.get("user-agent"))
    return play_service.session_payload(session, channel, _host(request))


@router.post("/{channel_id}/stop")
async def stop_play(channel_id: int, request: Request,
                    user: User = Depends(get_current_user),
                    db: AsyncSession = Depends(get_db)):
    channel = await get_channel_or_404(db, channel_id)
    r = await db.execute(
        select(PlaySession).where(
            PlaySession.user_id == user.id,
            PlaySession.channel_id == channel_id,
            PlaySession.session_type == "LIVE",
            PlaySession.ended_at.is_(None),
        )
    )
    for session in r.scalars().all():
        await play_service.stop_session(db, user, session, client_ip(request),
                                         request.headers.get("user-agent"))
    return {"ok": True}
