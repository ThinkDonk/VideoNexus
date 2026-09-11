"""开发模式播放流代理（仅 DEV_STREAM_PROXY=true 时注册）。

生产环境播放流由 Nginx 完成 auth_request + 反代（见 deploy/nginx/nginx.conf.template）；
本地无 Nginx 开发时，由本模块承担同样的职责：
  GET /stream/{app}/{stream}.live.flv | /stream/{app}/{stream}/hls.m3u8 | HLS 分片
鉴权逻辑与生产完全一致（services/stream_auth.py），鉴权通过后转发到 ZLM。

上游地址取 ZLM_DOWNLOAD_BASE_URL（部署形态下 WVP nginx 的 /rtp/、/index/api/ 均
代理到 ZLM，见 deploy/README.md）。
"""
import logging

import httpx
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from starlette.background import BackgroundTask

from app.config import get_settings
from app.core import db as core_db
from app.services import audit, stream_auth
from app.services.audit import AuditAction

logger = logging.getLogger(__name__)
router = APIRouter(tags=["dev-proxy"])

_client: httpx.AsyncClient | None = None


def _get_client() -> httpx.AsyncClient:
    global _client
    if _client is None:
        _client = httpx.AsyncClient(timeout=httpx.Timeout(10, read=None))
    return _client


async def close_proxy_client() -> None:
    global _client
    if _client is not None:
        await _client.aclose()
    _client = None


@router.api_route("/stream/{path:path}", methods=["GET", "HEAD"])
async def dev_stream_proxy(path: str, request: Request):
    s = get_settings()
    if not s.zlm_download_base_url:
        raise HTTPException(status_code=503, detail="未配置 ZLM_DOWNLOAD_BASE_URL，无法代理播放流")

    original_uri = request.url.path + (f"?{request.url.query}" if request.url.query else "")
    allowed, reason, user = await stream_auth.check_stream_access(request, original_uri)
    if not allowed:
        if core_db._session_factory is not None:
            async with core_db._session_factory() as db:
                await audit.write(db, action=AuditAction.STREAM_AUTH_FAIL, user=user,
                                  object_type="stream", object_id=original_uri[:64],
                                  params={"reason": reason, "via": "dev_proxy"},
                                  result="denied",
                                  ip=request.client.host if request.client else None,
                                  ua=request.headers.get("user-agent"))
                await db.commit()
        raise HTTPException(status_code=403, detail="无权访问该流")

    target = f"{s.zlm_download_base_url.rstrip('/')}/{path}"
    if request.url.query:
        target += f"?{request.url.query}"
    upstream_req = _get_client().build_request(request.method, target)
    resp = await _get_client().send(upstream_req, stream=True)

    async def _close_upstream() -> None:
        await resp.aclose()

    headers = {}
    if ct := resp.headers.get("content-type"):
        headers["content-type"] = ct
    return StreamingResponse(resp.aiter_bytes(64 * 1024), status_code=resp.status_code,
                             headers=headers, background=BackgroundTask(_close_upstream))
