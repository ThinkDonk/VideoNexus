"""播放会话编排：实时点播与录像回放共用。

关键约束：
- 播放地址永远是门户域名 + /stream/{app}/{stream} 路径 + st=stream_token，ZLM 原始地址不下发。
- 同一用户同一通道重复点播幂等复用（F5 刷新不产生孤儿会话），每次复用换新 token（旧 token 作废）。
"""
from datetime import timedelta

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.core.timezone import fmt_dt, now
from app.models import Channel, PlaySession, User
from app.services import audit, wvp as wvp_service


def build_stream_urls(host: str, app: str, stream: str, token: str) -> dict:
    """生成门户域名下的多协议播放地址（host 来自请求头，不含协议与端口）。"""
    s = get_settings()
    ws = "wss" if s.public_https else "ws"
    http = "https" if s.public_https else "http"
    st = f"?st={token}"
    return {
        "wsFlv": f"{ws}://{host}/stream/{app}/{stream}.live.flv{st}",
        "flv": f"{http}://{host}/stream/{app}/{stream}.live.flv{st}",
        "hls": f"{http}://{host}/stream/{app}/{stream}/hls.m3u8{st}",
    }


async def _close_session(db: AsyncSession, session: PlaySession, wvp: wvp_service.WvpClient,
                         stop_action: str) -> None:
    """关闭会话并停止 WVP 侧拉流（失败不阻断关闭流程，WVP 无人观看兜底断流）。"""
    end = now()
    if session.ended_at is None:
        session.ended_at = end
        session.duration_seconds = int((end - session.started_at).total_seconds())
    r = await db.execute(select(Channel).where(Channel.id == session.channel_id))
    channel = r.scalar_one_or_none()
    if channel is not None:
        try:
            if session.session_type == "LIVE":
                await wvp.play_stop(channel.device_id, channel.channel_id)
            else:
                await wvp.playback_stop(channel.device_id, channel.channel_id, session.stream)
        except Exception:
            pass  # BYE 失败由 ZLM 无人观看机制兜底


async def start_live(db: AsyncSession, user: User, channel: Channel, host: str,
                     ip: str | None, ua: str | None) -> PlaySession:
    """实时点播：校验在 API 层完成（require_grant），这里负责编排与审计。"""
    from app.services.grants import org_play_limit_reached
    if await org_play_limit_reached(db, user):
        raise HTTPException(status_code=429, detail="机构同时在线播放路数已达上限")

    wvp = wvp_service.get_wvp()
    try:
        stream = await wvp.play_start(channel.device_id, channel.channel_id)
    except wvp_service.WvpError as e:
        raise HTTPException(status_code=502, detail=f"WVP 点播失败: {e}")

    app = stream.get("app") or "rtp"
    stream_name = stream.get("stream") or f"{channel.device_id}_{channel.channel_id}"

    # 幂等复用：关闭旧会话记录（换新 token），复用 WVP 已存在的流
    r = await db.execute(
        select(PlaySession).where(
            PlaySession.user_id == user.id,
            PlaySession.channel_id == channel.id,
            PlaySession.session_type == "LIVE",
            PlaySession.ended_at.is_(None),
        )
    )
    for old in r.scalars().all():
        old.ended_at = now()
        old.duration_seconds = int((old.ended_at - old.started_at).total_seconds())

    session = PlaySession(
        user_id=user.id, channel_id=channel.id, session_type="LIVE",
        app=app, stream=stream_name,
        stream_token=_new_token(),
        started_at=now(),
        expires_at=now() + timedelta(hours=get_settings().play_session_max_hours),
    )
    db.add(session)
    await db.flush()
    await audit.write(db, action=audit.AuditAction.PLAY_START, user=user,
                      object_type="channel", object_id=channel.id,
                      params={"channel": channel.channel_id, "name": channel.display_name or channel.name,
                              "sessionId": session.id, "stream": stream_name},
                      ip=ip, ua=ua)
    return session


def _new_token() -> str:
    from app.core.security import new_stream_token
    return new_stream_token()


async def start_playback(db: AsyncSession, user: User, channel: Channel,
                         start_time: str, end_time: str, host: str,
                         ip: str | None, ua: str | None) -> PlaySession:
    wvp = wvp_service.get_wvp()
    try:
        stream = await wvp.playback_start(channel.device_id, channel.channel_id, start_time, end_time)
    except wvp_service.WvpError as e:
        raise HTTPException(status_code=502, detail=f"WVP 回放失败: {e}")

    app = stream.get("app") or "rtp"
    stream_name = stream.get("stream") or ""
    if not stream_name:
        raise HTTPException(status_code=502, detail="WVP 未返回回放流标识")

    session = PlaySession(
        user_id=user.id, channel_id=channel.id, session_type="PLAYBACK",
        app=app, stream=stream_name,
        stream_token=_new_token(),
        started_at=now(),
        expires_at=now() + timedelta(hours=get_settings().play_session_max_hours),
    )
    db.add(session)
    await db.flush()
    await audit.write(db, action=audit.AuditAction.PLAYBACK_START, user=user,
                      object_type="channel", object_id=channel.id,
                      params={"channel": channel.channel_id, "name": channel.display_name or channel.name,
                              "sessionId": session.id, "stream": stream_name,
                              "startTime": start_time, "endTime": end_time},
                      ip=ip, ua=ua)
    return session


async def get_own_session(db: AsyncSession, user: User, session_id: int) -> PlaySession:
    r = await db.execute(
        select(PlaySession).where(PlaySession.id == session_id, PlaySession.user_id == user.id)
    )
    session = r.scalar_one_or_none()
    if session is None or session.ended_at is not None:
        raise HTTPException(status_code=404, detail="播放会话不存在或已结束")
    return session


async def stop_session(db: AsyncSession, user: User, session: PlaySession,
                       ip: str | None = None, ua: str | None = None) -> None:
    wvp = wvp_service.get_wvp()
    await _close_session(db, session, wvp, "stop")
    action = (audit.AuditAction.PLAY_END if session.session_type == "LIVE"
              else audit.AuditAction.PLAYBACK_END)
    await audit.write(db, action=action, user=user, object_type="channel",
                      object_id=session.channel_id,
                      params={"sessionId": session.id, "stream": session.stream,
                              "durationSeconds": session.duration_seconds},
                      ip=ip, ua=ua)


async def cleanup_expired_sessions(db: AsyncSession) -> int:
    """定时任务：关闭超时播放会话并停止 WVP 拉流。"""
    wvp = wvp_service.get_wvp()
    r = await db.execute(
        select(PlaySession).where(PlaySession.ended_at.is_(None), PlaySession.expires_at <= now())
    )
    sessions = r.scalars().all()
    for s in sessions:
        await _close_session(db, s, wvp, "expire")
        await audit.write(db, action=(audit.AuditAction.PLAY_END if s.session_type == "LIVE"
                                       else audit.AuditAction.PLAYBACK_END),
                          object_type="channel", object_id=s.channel_id,
                          params={"sessionId": s.id, "stream": s.stream,
                                  "durationSeconds": s.duration_seconds, "reason": "expired"},
                          result="expired")
    return len(sessions)


def session_payload(session: PlaySession, channel: Channel, host: str) -> dict:
    return {
        "sessionId": session.id,
        "channelId": channel.id,
        "channelName": channel.display_name or channel.name,
        "channelGbId": channel.channel_id,
        "type": session.session_type,
        "stream": session.stream,
        "urls": build_stream_urls(host, session.app, session.stream, session.stream_token),
        "expiresAt": fmt_dt(session.expires_at),
    }
