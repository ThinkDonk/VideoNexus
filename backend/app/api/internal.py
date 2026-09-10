"""内部端点：Nginx auth_request 的播放流校验 + 健康检查。

Nginx 配置（见 deploy/nginx/nginx.conf.template）：
  location = /_stream_auth {
      internal;
      proxy_pass http://backend/internal/stream/auth;
      proxy_pass_request_body off;
      proxy_set_header Content-Length "";
      proxy_set_header X-Original-URI $request_uri;   # 原始请求（含 ?st= 查询串）
  }
auth_request 会自动携带原始请求头（含 Cookie）。

校验规则：
  1) 登录 cookie 必须有效
  2) ?st=stream_token 存在时：必须命中该用户处于播放中的会话且 app/stream 匹配
  3) st 缺失（HLS 分片场景）：该用户存在匹配 app/stream 的播放中会话即可
  4) 校验失败记审计（STREAM_AUTH_FAIL，疑似地址外泄/越权拉流）
"""
import jwt as pyjwt
from fastapi import APIRouter, Request, Response
from sqlalchemy import select

from app.core import db as core_db
from app.core.security import COOKIE_NAME, decode_session_token
from app.core.timezone import now
from app.models import PlaySession, User
from app.services import audit
from app.services.audit import AuditAction

router = APIRouter(prefix="/internal", tags=["internal"])


def _parse_stream(original_uri: str) -> tuple[str, str] | None:
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


def _get_st(original_uri: str) -> str | None:
    if "?" not in original_uri:
        return None
    query = original_uri.split("?", 1)[1]
    for kv in query.split("&"):
        if kv.startswith("st="):
            return kv[3:]
    return None


@router.api_route("/stream/auth", methods=["GET", "POST", "HEAD"])
async def stream_auth(request: Request, response: Response):
    ip = request.headers.get("x-real-ip") or (request.client.host if request.client else "unknown")
    ua = request.headers.get("user-agent")
    original_uri = request.headers.get("x-original-uri", "")

    async def deny(reason: str, user: User | None = None):
        if core_db._session_factory is None:
            return
        async with core_db._session_factory() as db:
            await audit.write(db, action=AuditAction.STREAM_AUTH_FAIL, user=user,
                              object_type="stream", object_id=original_uri[:64],
                              params={"reason": reason}, result="denied", ip=ip, ua=ua)
            await db.commit()
        return Response(status_code=403)

    token = request.cookies.get(COOKIE_NAME)
    if not token:
        return await deny("no_cookie")
    try:
        payload = decode_session_token(token)
    except pyjwt.InvalidTokenError:
        return await deny("bad_cookie")

    if core_db._session_factory is None:
        return Response(status_code=503)

    parsed = _parse_stream(original_uri)
    if parsed is None:
        return await deny("bad_uri")
    app, stream = parsed
    st = _get_st(original_uri)

    async with core_db._session_factory() as db:
        r = await db.execute(select(User).where(User.id == int(payload["sub"])))
        user = r.scalar_one_or_none()
        if user is None or not user.status:
            return await deny("bad_user")
        if payload.get("ver", 0) != user.session_version:
            return await deny("stale_session", user)

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
                return await deny("token_mismatch", user)
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
                return await deny("no_active_session", user)

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
        return Response(status_code=200)


@router.get("/health")
async def health():
    from app.services import wvp as wvp_service
    ok = core_db._session_factory is not None
    return {"status": "ok" if ok else "degraded", "db": ok}
