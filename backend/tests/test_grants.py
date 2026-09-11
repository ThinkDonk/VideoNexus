"""越权矩阵测试：机构用户只允许访问被授权的通道与动作，其余一律 403 且留审计。"""
import pytest
import pytest_asyncio
from httpx import AsyncClient
from tests.conftest import login

from tests.conftest import WvpStub

RANGE_START = "2026-09-01 00:00:00"
RANGE_END = "2026-09-01 12:00:00"


@pytest_asyncio.fixture(scope="module", autouse=True)
async def seeded(app_ctx):
    """建机构/用户/通道并授权：bank1 仅通道 A 的 live。"""
    from httpx import ASGITransport, AsyncClient as _AC
    app, stub = app_ctx
    async with _AC(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.post("/api/auth/login",
                              json={"username": "admin", "password": "Admin@12345"})
        assert r.status_code == 200, r.text
        # 同步通道台账
        r = await client.post("/api/admin/channels/sync")
        assert r.status_code == 200, r.text
        r = await client.get("/api/admin/channels")
        channels = {c["channelId"]: c for c in r.json()["list"]}
        assert WvpStub.CHANNEL_A in channels and WvpStub.CHANNEL_B in channels
        # 机构 + 机构用户
        r = await client.post("/api/admin/orgs", json={
            "name": "测试机构", "status": True, "maxConcurrentPlays": 4, "quotaGb": 50})
        assert r.status_code == 201, r.text
        org_id = r.json()["id"]
        r = await client.post("/api/admin/users", json={
            "username": "banker1", "password": "Banker@123", "displayName": "机构用户",
            "orgId": org_id, "role": "BANK_USER"})
        assert r.status_code == 201, r.text
        uid = r.json()["id"]
        # 仅通道 A live 授权
        r = await client.put(f"/api/admin/users/{uid}/grants", json={"grants": [{
            "channelId": channels[WvpStub.CHANNEL_A]["id"],
            "canLive": True, "canPlayback": False, "canDownload": False}]})
        assert r.status_code == 200, r.text
        return {"channels": channels, "uid": uid, "org_id": org_id}


@pytest_asyncio.fixture
async def bank_client(make_client, seeded):
    """独立实例：与 admin_client 并存时不能共享 cookie 罐。"""
    c = await make_client()
    r = await login(c, "banker1", "Banker@123")
    assert r.status_code == 200, r.text
    return c


# ---------- 通道树只显示授权通道 ----------

async def test_tree_shows_only_granted(bank_client):
    r = await bank_client.get("/api/channels/tree")
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 1
    node = body["devices"][0]["children"][0]
    assert node["channelGbId"] == WvpStub.CHANNEL_A
    assert node["grants"] == {"live": True, "playback": False, "download": False}


# ---------- 越权矩阵 ----------

async def test_play_granted_channel_ok(bank_client, seeded):
    ch_id = seeded["channels"][WvpStub.CHANNEL_A]["id"]
    r = await bank_client.post(f"/api/play/{ch_id}")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["type"] == "LIVE"
    assert body["urls"]["wsFlv"].startswith("ws://test/stream/rtp/")
    assert "?st=" in body["urls"]["wsFlv"]
    # 幂等复用：重复点播仍成功
    r2 = await bank_client.post(f"/api/play/{ch_id}")
    assert r2.status_code == 200
    # 停止
    r = await bank_client.post(f"/api/play/{ch_id}/stop")
    assert r.status_code == 200


async def test_play_ungranted_channel_403(bank_client, seeded):
    ch_b = seeded["channels"][WvpStub.CHANNEL_B]["id"]
    r = await bank_client.post(f"/api/play/{ch_b}")
    assert r.status_code == 403


async def test_playback_ungranted_403(bank_client, seeded):
    ch_a = seeded["channels"][WvpStub.CHANNEL_A]["id"]
    r = await bank_client.post(f"/api/playback/{ch_a}",
                               json={"startTime": RANGE_START, "endTime": RANGE_END})
    assert r.status_code == 403


async def test_record_query_ungranted_403(bank_client, seeded):
    ch_a = seeded["channels"][WvpStub.CHANNEL_A]["id"]
    r = await bank_client.get(f"/api/record/{ch_a}",
                              params={"startTime": RANGE_START, "endTime": RANGE_END})
    assert r.status_code == 403


async def test_download_ungranted_403(bank_client, seeded):
    ch_a = seeded["channels"][WvpStub.CHANNEL_A]["id"]
    r = await bank_client.post("/api/download-tasks",
                               json={"channelId": ch_a, "startTime": RANGE_START, "endTime": RANGE_END})
    assert r.status_code == 403


async def test_nonexistent_channel_404(bank_client):
    r = await bank_client.post("/api/play/999999")
    assert r.status_code == 404


# ---------- 授权有效期 ----------

async def test_expired_grant_403(admin_client, bank_client, seeded):
    ch_a = seeded["channels"][WvpStub.CHANNEL_A]["id"]
    uid = seeded["uid"]
    # 授权改为已过期
    r = await admin_client.put(f"/api/admin/users/{uid}/grants", json={"grants": [{
        "channelId": ch_a, "canLive": True, "canPlayback": True, "canDownload": True,
        "validFrom": "2025-01-01 00:00:00", "validUntil": "2025-12-31 23:59:59"}]})
    assert r.status_code == 200
    r = await bank_client.post(f"/api/play/{ch_a}")
    assert r.status_code == 403
    # 恢复 live 授权
    r = await admin_client.put(f"/api/admin/users/{uid}/grants", json={"grants": [{
        "channelId": ch_a, "canLive": True, "canPlayback": False, "canDownload": False}]})
    assert r.status_code == 200


# ---------- 回放链路（拿到 playback 授权后）----------

async def test_playback_flow_after_grant(admin_client, bank_client, seeded):
    ch_a = seeded["channels"][WvpStub.CHANNEL_A]["id"]
    uid = seeded["uid"]
    r = await admin_client.put(f"/api/admin/users/{uid}/grants", json={"grants": [{
        "channelId": ch_a, "canLive": True, "canPlayback": True, "canDownload": False}]})
    assert r.status_code == 200

    # 录像查询
    r = await bank_client.get(f"/api/record/{ch_a}",
                              params={"startTime": RANGE_START, "endTime": RANGE_END})
    assert r.status_code == 200, r.text
    assert len(r.json()["records"]) == 1
    assert r.json()["records"][0]["durationSeconds"] == 3600

    # 回放
    r = await bank_client.post(f"/api/playback/{ch_a}",
                               json={"startTime": RANGE_START, "endTime": RANGE_END})
    assert r.status_code == 200, r.text
    session_id = r.json()["sessionId"]
    stream = r.json()["stream"]
    assert "_20260901080000_20260901090000" in stream

    # 控制
    assert (await bank_client.post(f"/api/playback/sessions/{session_id}/pause")).status_code == 200
    assert (await bank_client.post(f"/api/playback/sessions/{session_id}/resume")).status_code == 200
    assert (await bank_client.post(f"/api/playback/sessions/{session_id}/seek",
                                   json={"seconds": 60})).status_code == 200
    assert (await bank_client.post(f"/api/playback/sessions/{session_id}/speed",
                                   json={"speed": 4})).status_code == 200
    assert (await bank_client.post(f"/api/playback/sessions/{session_id}/speed",
                                   json={"speed": 3})).status_code == 400
    assert (await bank_client.post(f"/api/playback/sessions/{session_id}/stop")).status_code == 200
    # 已结束的会话再操作 → 404
    assert (await bank_client.post(f"/api/playback/sessions/{session_id}/pause")).status_code == 404

    # 恢复 live-only 授权
    await admin_client.put(f"/api/admin/users/{uid}/grants", json={"grants": [{
        "channelId": ch_a, "canLive": True, "canPlayback": False, "canDownload": False}]})


# ---------- 播放流鉴权（auth_request 后端逻辑）----------

async def _start_live(bank_client, seeded) -> dict:
    ch_a = seeded["channels"][WvpStub.CHANNEL_A]["id"]
    r = await bank_client.post(f"/api/play/{ch_a}")
    assert r.status_code == 200
    return r.json()


async def test_stream_auth_ok(bank_client, seeded):
    body = await _start_live(bank_client, seeded)
    ws_url = body["urls"]["wsFlv"]
    uri = ws_url.split("test", 1)[1]  # /stream/rtp/xxx.live.flv?st=...
    r = await bank_client.request("GET", "/internal/stream/auth",
                                  headers={"X-Original-URI": uri})
    assert r.status_code == 200, r.text
    # HLS 分片（无 st）也应放行
    hls_uri = f"/stream/rtp/{body['stream']}/hls/abc123.ts"
    r = await bank_client.request("GET", "/internal/stream/auth",
                                  headers={"X-Original-URI": hls_uri})
    assert r.status_code == 200, r.text
    # 停止后不放行
    await bank_client.post(f"/api/play/{seeded['channels'][WvpStub.CHANNEL_A]['id']}/stop")
    r = await bank_client.request("GET", "/internal/stream/auth",
                                  headers={"X-Original-URI": uri})
    assert r.status_code == 403


async def test_stream_auth_bad_token(bank_client, seeded):
    await _start_live(bank_client, seeded)
    r = await bank_client.request("GET", "/internal/stream/auth",
                                  headers={"X-Original-URI": "/stream/rtp/xxx.live.flv?st=fake-token"})
    assert r.status_code == 403


async def test_stream_auth_no_session(bank_client, seeded):
    r = await bank_client.request("GET", "/internal/stream/auth",
                                  headers={"X-Original-URI": "/stream/rtp/notexist.live.flv"})
    assert r.status_code == 403


async def test_stream_auth_no_cookie(client):
    r = await client.request("GET", "/internal/stream/auth",
                              headers={"X-Original-URI": "/stream/rtp/x.live.flv?st=1"})
    assert r.status_code == 403


# ---------- 审计落库验证 ----------

async def test_audit_trail_exists(admin_client, seeded):
    r = await admin_client.get("/api/admin/audit", params={"action": "GRANT_ADDED"})
    assert r.status_code == 200
    assert r.json()["total"] >= 1
    entry = r.json()["list"][0]
    assert entry["username"] == "admin"
    assert "to" in entry["params"] or "to" in (entry["params"] or "")

    r = await admin_client.get("/api/admin/audit", params={"action": "STREAM_AUTH_FAIL"})
    assert r.status_code == 200
    assert r.json()["total"] >= 3  # bad_token / no_session / stopped 三个场景


async def test_bank_user_cannot_access_admin(bank_client):
    r = await bank_client.get("/api/admin/users")
    assert r.status_code == 403
    r = await bank_client.get("/api/admin/audit")
    assert r.status_code == 403
