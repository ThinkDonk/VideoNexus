"""下载任务链路测试：创建校验、异步完成、文件下载。"""
import asyncio
from pathlib import Path

import pytest_asyncio
from tests.conftest import login, WvpStub

RANGE_START = "2026-09-01 00:00:00"
RANGE_END = "2026-09-01 01:00:00"


@pytest_asyncio.fixture(scope="module", autouse=True)
async def seeded(app_ctx):
    from httpx import ASGITransport, AsyncClient as _AC
    app, stub = app_ctx
    async with _AC(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.post("/api/auth/login",
                              json={"username": "admin", "password": "Admin@12345"})
        assert r.status_code == 200, r.text
        r = await client.post("/api/admin/channels/sync")
        assert r.status_code == 200
        r = await client.get("/api/admin/channels")
        channels = {c["channelId"]: c for c in r.json()["list"]}
        r = await client.post("/api/admin/users", json={
            "username": "downloader1", "password": "Downer@123", "displayName": "下载用户",
            "orgId": None, "role": "ADMIN"})
        assert r.status_code == 201
        return {"channels": channels}


@pytest_asyncio.fixture
async def bank_client(make_client, seeded):
    """独立实例：与其他登录身份并存时不共享 cookie 罐。"""
    c = await make_client()
    r = await login(c, "downloader1", "Downer@123")
    assert r.status_code == 200
    return c


async def test_download_full_flow(bank_client, seeded, app_ctx, monkeypatch):
    app, stub = app_ctx
    ch_a = seeded["channels"][WvpStub.CHANNEL_A]["id"]

    # 1. monkeypatch 文件拉取（写一个假 MP4）——必须在创建任务之前，
    #    否则任务创建时 submit 的后台协程可能先于 patch 生效、
    #    用真实 fetch 去请求 http://zlm-fake/... 导致任务 FAILED
    from app.services import download_worker

    async def fake_fetch(url, dest: Path) -> int:
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(b"FAKE_MP4_CONTENT" * 1000)
        return dest.stat().st_size
    monkeypatch.setattr(download_worker, "fetch_file_to_path", fake_fetch)

    # 2. 创建任务
    r = await bank_client.post("/api/download-tasks",
                               json={"channelId": ch_a, "startTime": RANGE_START, "endTime": RANGE_END})
    assert r.status_code == 201, r.text
    task_id = r.json()["id"]
    assert r.json()["status"] == "PENDING"

    # 3. 等待 worker 完成
    for _ in range(20):
        r = await bank_client.get(f"/api/download-tasks/{task_id}")
        assert r.status_code == 200
        if r.json()["status"] in ("COMPLETE", "FAILED"):
            break
        await asyncio.sleep(0.5)
    body = r.json()
    assert body["status"] == "COMPLETE", body
    assert body["fileSize"] > 0
    assert body["expiresAt"]

    # 4. 文件下载（X-Accel-Redirect 头）
    r = await bank_client.get(f"/api/download-tasks/{task_id}/file")
    assert r.status_code == 200
    assert r.headers.get("x-accel-redirect", "").startswith("/protected-download/")

    # 5. 审计链完整
    r = await bank_client.get("/api/admin/audit", params={"action": "DOWNLOAD_CREATE"})
    assert r.json()["total"] >= 1
    r = await bank_client.get("/api/admin/audit", params={"action": "DOWNLOAD_COMPLETE"})
    assert r.json()["total"] >= 1


async def test_download_over_duration_rejected(bank_client, seeded):
    ch_a = seeded["channels"][WvpStub.CHANNEL_B]["id"]
    r = await bank_client.post("/api/download-tasks", json={
        "channelId": ch_a, "startTime": RANGE_START, "endTime": "2026-09-05 00:00:00"})
    assert r.status_code == 400
    assert "超过" in r.json()["detail"]


async def test_download_bad_time_range(bank_client, seeded):
    ch_a = seeded["channels"][WvpStub.CHANNEL_A]["id"]
    r = await bank_client.post("/api/download-tasks", json={
        "channelId": ch_a, "startTime": RANGE_END, "endTime": RANGE_START})
    assert r.status_code == 400


async def test_download_running_limit(bank_client, seeded, app_ctx):
    app, stub = app_ctx
    # 把桩改成永不完成
    stub._download_done_after = 10 ** 9
    ch_a = seeded["channels"][WvpStub.CHANNEL_A]["id"]
    r = await bank_client.post("/api/download-tasks", json={
        "channelId": ch_a, "startTime": RANGE_START, "endTime": RANGE_END})
    assert r.status_code == 201
    r = await bank_client.post("/api/download-tasks", json={
        "channelId": seeded["channels"][WvpStub.CHANNEL_B]["id"],
        "startTime": RANGE_START, "endTime": RANGE_END})
    assert r.status_code == 201
    # 第 3 个并发任务被拒（DOWNLOAD_MAX_RUNNING_PER_USER=2）
    r = await bank_client.post("/api/download-tasks", json={
        "channelId": ch_a, "startTime": RANGE_START, "endTime": RANGE_END})
    assert r.status_code == 429
    # 恢复桩并等待两个任务结束，避免影响后续测试
    stub._download_done_after = 2
    for _ in range(30):
        r = await bank_client.get("/api/download-tasks")
        statuses = [t["status"] for t in r.json()]
        if all(s in ("COMPLETE", "FAILED") for s in statuses):
            break
        await asyncio.sleep(0.5)
