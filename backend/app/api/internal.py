"""内部端点：Nginx auth_request 的播放流校验 + 健康检查。

Nginx 配置（见 deploy/nginx/nginx.conf.template）：
  location = /_stream_auth {
      internal;
      proxy_pass http://backend/internal/stream/auth;
      proxy_pass_request_body off;
      proxy_set_header Content-Length "";
      proxy_set_header X-Original-URI $request_uri;   # 原始请求（含 ?st= 查询串）
  }
auth_request 会自动携带原始请求头（含 Cookie）。校验规则见 services/stream_auth.py。
"""
from fastapi import APIRouter, Request, Response

from app.core import db as core_db
from app.services import audit
from app.services import stream_auth as stream_auth_service
from app.services.audit import AuditAction

router = APIRouter(prefix="/internal", tags=["internal"])


@router.api_route("/stream/auth", methods=["GET", "POST", "HEAD"])
async def stream_auth(request: Request):
    ip = request.headers.get("x-real-ip") or (request.client.host if request.client else "unknown")
    ua = request.headers.get("user-agent")
    original_uri = request.headers.get("x-original-uri", "")

    allowed, reason, user = await stream_auth_service.check_stream_access(request, original_uri)
    if not allowed:
        if core_db._session_factory is not None:
            async with core_db._session_factory() as db:
                await audit.write(db, action=AuditAction.STREAM_AUTH_FAIL, user=user,
                                  object_type="stream", object_id=original_uri[:64],
                                  params={"reason": reason}, result="denied", ip=ip, ua=ua)
                await db.commit()
        return Response(status_code=403)
    return Response(status_code=200)


@router.get("/health")
async def health():
    ok = core_db._session_factory is not None
    return {"status": "ok" if ok else "degraded", "db": ok}
