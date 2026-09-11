"""测试夹具：独立临时数据目录 + WVP 桩 + httpx ASGI 客户端。"""
import asyncio
import os
import sys
from pathlib import Path

# 环境必须先于 app 模块导入设置（Settings 单例）
_TMP = Path(__file__).parent / "_tmp_data"
if _TMP.exists():
    import shutil
    shutil.rmtree(_TMP)
os.environ.update({
    "DATA_DIR": str(_TMP),
    "JWT_SECRET": "test-jwt-secret",
    "PUBLIC_HTTPS": "false",
    "INITIAL_ADMIN_USERNAME": "admin",
    "INITIAL_ADMIN_PASSWORD": "Admin@12345",
    "WVP_BASE_URL": "http://127.0.0.1:9",  # 不会被真正请求（用桩替换）
    "LOGIN_MAX_FAILURES": "3",
    "LOGIN_LOCK_MINUTES": "30",
    "DOWNLOAD_POLL_SECONDS": "1",
    "FILE_RETENTION_DAYS": "7",
    "TZ": "Asia/Shanghai",
    "DEV_STREAM_PROXY": "false",  # 测试与本地 .env 隔离（环境变量优先于 dotenv）
})
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient


class WvpStub:
    """WVP 桩：可编程返回值。"""
    DEVICE = "34020000001110000001"
    CHANNEL_A = "34020000001310000001"
    CHANNEL_B = "34020000001310000002"

    def __init__(self):
        self.play_calls = []
        self.download_progress_calls = 0
        self.pause_fails = False  # 模拟不支持暂停/恢复的设备（WVP 固定报错）
        self._download_done_after = 2  # 第 2 次轮询后完成
        self.download_file_url = "http://zlm-fake/index/api/downloadFile?file_path=/opt/x.mp4"

    async def devices(self, page=1, count=100):
        return {"total": 1, "list": [{"deviceId": self.DEVICE, "name": "测试设备", "onLine": True,
                                       "channelCount": 2}]}

    async def channels(self, device_id, page=1, count=100):
        assert device_id == self.DEVICE
        return {"total": 2, "list": [
            {"deviceId": self.CHANNEL_A, "name": "1号仓-北门", "status": "ON"},
            {"deviceId": self.CHANNEL_B, "name": "1号仓-南门", "status": "ON"},
        ]}

    async def play_start(self, device_id, channel_id):
        self.play_calls.append(("play", device_id, channel_id))
        return {"app": "rtp", "stream": f"{device_id}_{channel_id}",
                "ws_flv": f"ws://zlm/rtp/{device_id}_{channel_id}.live.flv"}

    async def play_stop(self, device_id, channel_id):
        return {}

    async def record_query(self, device_id, channel_id, start, end):
        return {"recordList": [
            {"startTime": f"{start[:10]} 08:00:00", "endTime": f"{start[:10]} 09:00:00", "type": "time"},
        ]}

    async def playback_start(self, device_id, channel_id, start, end):
        return {"app": "rtp", "stream": f"{device_id}_{channel_id}_20260901080000_20260901090000"}

    async def playback_control(self, op, stream, arg=None):
        if self.pause_fails and op in ("pause", "resume"):
            from app.services.wvp import WvpError
            raise WvpError("暂停RTP接收失败" if op == "pause" else "继续RTP接收失败", 400)
        return {}

    async def playback_stop(self, device_id, channel_id, stream):
        return {}

    async def download_start(self, device_id, channel_id, start, end, speed):
        return {"app": "rtp", "stream": f"{device_id}_{channel_id}_dl"}

    async def download_progress(self, device_id, channel_id, stream):
        self.download_progress_calls += 1
        if self.download_progress_calls >= self._download_done_after:
            return {"progress": 100,
                    "downLoadFilePath": {"httpPath": self.download_file_url}}
        return {"progress": 50}

    async def download_stop(self, device_id, channel_id, stream):
        return {}

    async def start(self):
        pass

    async def close(self):
        pass


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(scope="session")
async def app_ctx():
    from app.main import app
    from app.services import wvp as wvp_service
    stub = WvpStub()
    wvp_service.set_wvp(stub)
    for handler in app.router.on_startup:
        await handler()
    yield app, stub
    for handler in app.router.on_shutdown:
        await handler()
    wvp_service.set_wvp(None)


@pytest_asyncio.fixture
async def client(app_ctx):
    app, stub = app_ctx
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


@pytest_asyncio.fixture
async def make_client(app_ctx):
    """工厂 fixture：每个调用方获得独立的 AsyncClient 实例（独立 cookie 罐）。

    同一测试内需要两种登录身份（如 admin + 银行用户）时，必须各自用
    make_client() 创建实例，否则后登录的一方会覆盖共享 cookie 导致 403。
    """
    app, _ = app_ctx
    created = []

    async def _make():
        c = AsyncClient(transport=ASGITransport(app=app), base_url="http://test")
        created.append(c)
        return c

    yield _make
    for c in created:
        await c.aclose()


async def login(client: AsyncClient, username: str, password: str):
    return await client.post("/api/auth/login",
                             json={"username": username, "password": password})


@pytest_asyncio.fixture
async def admin_client(make_client):
    c = await make_client()
    r = await login(c, "admin", "Admin@12345")
    assert r.status_code == 200, r.text
    yield c
