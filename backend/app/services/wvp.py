"""WVP REST 客户端（门户是 WVP 的唯一调用方）。

认证：优先 api-key header（长效 JWT）；未配置时用账号登录 access-token，401 自动重登。
WVP 返回体统一为 WVPResult{code,msg,data}，code!=0 抛 WvpError。
"""
import hashlib
import logging
from typing import Any

import httpx

from app.config import get_settings

logger = logging.getLogger(__name__)


class WvpError(Exception):
    def __init__(self, msg: str, code: int = -1):
        super().__init__(msg)
        self.code = code


_client: "WvpClient | None" = None


def get_wvp() -> "WvpClient":
    """全局单例；main 启动时初始化，测试时可替换为桩。"""
    global _client
    if _client is None:
        _client = WvpClient()
    return _client


def set_wvp(client: "WvpClient | None") -> None:
    global _client
    _client = client


class WvpClient:
    def __init__(self) -> None:
        self._http: httpx.AsyncClient | None = None
        self._token: str | None = None

    async def start(self) -> None:
        self._http = httpx.AsyncClient(timeout=httpx.Timeout(get_settings().wvp_request_timeout))

    async def close(self) -> None:
        if self._http:
            await self._http.aclose()
        self._http = None
        self._token = None

    # ---------- 内部 ----------

    def _headers(self) -> dict[str, str]:
        s = get_settings()
        if s.wvp_api_key:
            return {"api-key": s.wvp_api_key}
        if self._token:
            return {"access-token": self._token}
        return {}

    async def _login(self) -> None:
        s = get_settings()
        pwd_md5 = hashlib.md5(s.wvp_password.encode()).hexdigest()
        r = await self._http.get(
            f"{s.wvp_base_url}/api/user/login",
            params={"username": s.wvp_username, "password": pwd_md5},
        )
        r.raise_for_status()
        body = r.json()
        if body.get("code") != 0:
            raise WvpError(f"WVP 登录失败: {body.get('msg')}", body.get("code", -1))
        self._token = body["data"]["accessToken"]

    async def _request(self, method: str, path: str, params: dict | None = None) -> dict:
        s = get_settings()
        url = f"{s.wvp_base_url}{path}"
        assert self._http is not None
        r = await self._http.request(method, url, params=params, headers=self._headers())
        if r.status_code == 401 and not s.wvp_api_key:
            await self._login()
            r = await self._http.request(method, url, params=params, headers=self._headers())
        r.raise_for_status()
        body = r.json()
        if body.get("code") != 0:
            raise WvpError(body.get("msg") or "WVP 返回失败", body.get("code", -1))
        return body.get("data") or {}

    async def _get(self, path: str, params: dict | None = None) -> dict:
        return await self._request("GET", path, params)

    # ---------- 设备/通道 ----------

    async def devices(self, page: int = 1, count: int = 100) -> dict:
        return await self._get("/api/device/query/devices", {"page": page, "count": count})

    async def channels(self, device_id: str, page: int = 1, count: int = 100) -> dict:
        return await self._get(f"/api/device/query/devices/{device_id}/channels",
                               {"page": page, "count": count})

    # ---------- 实时点播 ----------

    async def play_start(self, device_id: str, channel_id: str) -> dict:
        return await self._get(f"/api/play/start/{device_id}/{channel_id}")

    async def play_stop(self, device_id: str, channel_id: str) -> dict:
        return await self._get(f"/api/play/stop/{device_id}/{channel_id}")

    # ---------- 录像/回放 ----------

    async def record_query(self, device_id: str, channel_id: str, start: str, end: str) -> dict:
        return await self._get(f"/api/gb_record/query/{device_id}/{channel_id}",
                               {"startTime": start, "endTime": end})

    async def playback_start(self, device_id: str, channel_id: str, start: str, end: str) -> dict:
        return await self._get(f"/api/playback/start/{device_id}/{channel_id}",
                               {"startTime": start, "endTime": end})

    async def playback_control(self, op: str, stream: str, arg: str | None = None) -> dict:
        path = f"/api/playback/{op}/{stream}"
        if arg is not None:
            path += f"/{arg}"
        return await self._get(path)

    async def playback_stop(self, device_id: str, channel_id: str, stream: str) -> dict:
        return await self._get(f"/api/playback/stop/{device_id}/{channel_id}/{stream}")

    # ---------- 录像下载 ----------

    async def download_start(self, device_id: str, channel_id: str, start: str, end: str,
                             speed: int) -> dict:
        return await self._get(f"/api/gb_record/download/start/{device_id}/{channel_id}",
                               {"startTime": start, "endTime": end, "downloadSpeed": speed})

    async def download_progress(self, device_id: str, channel_id: str, stream: str) -> dict:
        return await self._get(f"/api/gb_record/download/progress/{device_id}/{channel_id}/{stream}")

    async def download_stop(self, device_id: str, channel_id: str, stream: str) -> dict:
        return await self._get(f"/api/gb_record/download/stop/{device_id}/{channel_id}/{stream}")

    async def cloud_record_list(self, app: str, stream: str, page: int = 1, count: int = 100) -> dict:
        """查询云端录像（ZLM on_record_mp4 完成即入库，条目出现代表文件已写完）。"""
        return await self._get("/api/cloud/record/list",
                               {"app": app, "stream": stream, "page": page, "count": count})

    # ---------- 其他 ----------

    async def health(self) -> bool:
        try:
            await self.devices(page=1, count=1)
            return True
        except Exception:
            return False


def zlm_download_url(raw_url: str) -> str:
    """按配置改写 ZLM 下载直链的 host（WVP 返回的 stream-ip 可能本机不可达）。"""
    s = get_settings()
    if not s.zlm_download_base_url or not raw_url:
        return raw_url
    base = s.zlm_download_base_url.rstrip("/")
    idx = raw_url.find("://")
    if idx < 0:
        return raw_url
    rest = raw_url[idx + 3:]
    slash = rest.find("/")
    if slash < 0:
        return f"{base}{rest}"
    return f"{base}{rest[slash:]}"


def with_zlm_secret(url: str) -> str:
    s = get_settings()
    if not s.zlm_secret:
        return url
    sep = "&" if "?" in url else "?"
    return f"{url}{sep}secret={s.zlm_secret}"
