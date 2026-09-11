"""播放流访问校验（共享逻辑）。

两个调用方：
1. 生产：Nginx auth_request 子请求 -> app/api/internal.py 的 /internal/stream/auth
2. 开发：DEV_STREAM_PROXY=true 时，app/api/dev_proxy.py 在转发前直接调用

校验规则：
  1) 登录 cookie 必须有效
  2) ?st=stream_token 存在时：必须命中该用户处于播放中的会话且 app/stream 匹配
  3) st 缺失（HLS 分片场景）：该用户存在匹配 app/stream 的播放中会话即可
"""
import jwt as pyjwt
from fastapi import Request
from sqlalchemy import select

from app.core import db as core_db
from app.core.security import COOKIE_NAME, decode_session_token
from app.core.timezone import now
from app.models import PlaySession, User


def parse_stream(original_uri: str) -> tuple[str, str] | None:
    """从 /stream/{app}/{stream}... 提取 (app, stream)。"""
    path = original_uri.split("?")[0]
    parts = [p for p in path.split("/") if p]
    if len(parts) < 3 or parts[0] != "stream":
        return None
    app = parts[1]
    stream = parts[2]
    # rtp/xxx.live.flv -> xxx；rtp/xxx/hls.m3u8 -> xxx
    if ".live." in stream:
        stream = stream.split(".live.")[0]
    elif stream.endswith(".m3u8"):
        stream = stream[:-5]
    if not app or not stream:
        return None
    return app, stream


def get_st(original_uri: str) -> str | None:
    if "?" not in original_uri:
        return None
    query = original_uri.split("?", 1)[1]
    for kv in query.split("&"):
        if kv.startswith("st="):
            return kv[3:]
    return None


async def check_stream_access(request: Request, original_uri: str) -> tuple[bool, str, "User | None"]:
    """校验播放流访问。返回 (allowed, reason, user)。

    放行时会刷新对应 play_session 的 last_seen_at；拒绝时由调用方记审计
    （保持内部端点与开发代理的审计参数差异）。
    """
    if core_db._session_factory is None:
        return False, "db_unavailable", None

    token = request.cookies.get(COOKIE_NAME)
    if not token:
        return False, "no_cookie", None
    try:
        payload = decode_session_token(token)
    except pyjwt.InvalidTokenError:
        return False, "bad_cookie", None

    parsed = parse_stream(original_uri)
    if parsed is None:
        return False, "bad_uri", None
    app, stream = parsed
    st = get_st(original_uri)

    async with core_db._session_factory() as db:
        r = await db.execute(select(User).where(User.id == int(payload["sub"])))
        user = r.scalar_one_or_none()
        if user is None or not user.status:
            return False, "bad_user", user
        if payload.get("ver", 0) != user.session_version:
            return False, "stale_session", user

        now_ = now()
        if st:
            r = await db.execute(
                select(PlaySession).where(
                    PlaySession.stream_token == st,
                    PlaySession.ended_at.is_(None),
                    PlaySession.expires_at > now_,
                )
            )
            session = r.scalar_one_or_none()
            if (session is None or session.user_id != user.id
                    or session.app != app or session.stream != stream):
                return False, "token_mismatch", user
        else:
            r = await db.execute(
                select(PlaySession).where(
                    PlaySession.user_id == user.id,
                    PlaySession.app == app,
                    PlaySession.stream == stream,
                    PlaySession.ended_at.is_(None),
                    PlaySession.expires_at > now_,
                ).limit(1)
            )
            if r.scalar_one_or_none() is None:
                return False, "no_active_session", user

        # 刷新 last_seen（尽力而为，失败不影响放行）
        r = await db.execute(
            select(PlaySession).where(
                PlaySession.user_id == user.id,
                PlaySession.app == app,
                PlaySession.stream == stream,
                PlaySession.ended_at.is_(None),
            ).limit(1)
        )
        s = r.scalar_one_or_none()
        if s is not None:
            s.last_seen_at = now_
        await db.commit()
        return True, "ok", user
