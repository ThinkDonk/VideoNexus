"""通道失效（从设备目录中消失）后的可见性与操作约束。

背景：设备换编码、平台侧测试配置等会留下"幽灵通道"（如某些 NVR 的音频输出虚拟通道）。
这类通道会被下一次目录同步标记为 active=False，但历史授权可能仍在。
需求：失效通道不得再出现在用户摄像树上，也不允许再被授权或操作。
"""
import pytest_asyncio
from httpx import ASGITransport, AsyncClient as _AC

from tests.conftest import WvpStub, login

RANGE_START = "2026-09-01 00:00:00"
RANGE_END = "2026-09-01 01:00:00"


async def _as_admin(app):
    c = _AC(transport=ASGITransport(app=app), base_url="http://test")
    r = await c.post("/api/auth/login", json={"username": "admin", "password": "Admin@12345"})
    assert r.status_code == 200, r.text
    return c


@pytest_asyncio.fixture(scope="module")
async def seeded(app_ctx):
    """建机构/用户，并给两个通道都授权；结束后恢复桩的通道列表并重新同步。"""
    app, stub = app_ctx
    admin = await _as_admin(app)
    try:
        stub.channel_ids = [WvpStub.CHANNEL_A, WvpStub.CHANNEL_B]
        r = await admin.post("/api/admin/channels/sync")
        assert r.status_code == 200, r.text
        r = await admin.get("/api/admin/channels", params={"count": 50})
        channels = {c["channelId"]: c for c in r.json()["list"]}

        r = await admin.post("/api/admin/orgs", json={
            "name": "可见性测试机构", "status": True, "maxConcurrentPlays": 4, "quotaGb": 10})
        assert r.status_code in (201, 400), r.text
        org_id = r.json()["id"] if r.status_code == 201 else 1

        r = await admin.get("/api/admin/users", params={"query": "visuser"})
        users = r.json()["list"]
        if users:
            uid = users[0]["id"]
        else:
            r = await admin.post("/api/admin/users", json={
                "username": "visuser", "password": "Vis@12345", "displayName": "可见性用户",
                "orgId": org_id, "role": "BANK_USER"})
            assert r.status_code == 201, r.text
            uid = r.json()["id"]

        r = await admin.put(f"/api/admin/users/{uid}/grants", json={"grants": [
            {"channelId": channels[WvpStub.CHANNEL_A]["id"], "canLive": True, "canPlayback": True, "canDownload": True},
            {"channelId": channels[WvpStub.CHANNEL_B]["id"], "canLive": True, "canPlayback": True, "canDownload": True},
        ]})
        assert r.status_code == 200, r.text
        yield {"channels": channels, "uid": uid, "admin": admin}
    finally:
        # 恢复设备目录并同步，避免影响其他测试文件
        stub.channel_ids = [WvpStub.CHANNEL_A, WvpStub.CHANNEL_B]
        await admin.post("/api/admin/channels/sync")
        await admin.aclose()


@pytest_asyncio.fixture
async def bank_client(client, seeded):
    r = await login(client, "visuser", "Vis@12345")
    assert r.status_code == 200, r.text
    return client


async def _tree_ids(bank_client) -> set[str]:
    r = await bank_client.get("/api/channels/tree")
    assert r.status_code == 200, r.text
    return {n["channelGbId"] for d in r.json()["devices"] for n in d["children"]}


async def test_active_channels_visible_before_removal(bank_client, seeded):
    ids = await _tree_ids(bank_client)
    assert ids == {WvpStub.CHANNEL_A, WvpStub.CHANNEL_B}


async def test_stale_channel_hidden_and_blocked(app_ctx, bank_client, seeded):
    app, stub = app_ctx
    admin = seeded["admin"]
    stale_id = seeded["channels"][WvpStub.CHANNEL_B]["id"]

    # 设备目录里只剩下通道 A（模拟通道 B 被移除）
    stub.channel_ids = [WvpStub.CHANNEL_A]
    r = await admin.post("/api/admin/channels/sync")
    assert r.status_code == 200, r.text

    # 1) 用户摄像树不再包含失效通道（历史授权仍在）
    ids = await _tree_ids(bank_client)
    assert WvpStub.CHANNEL_B not in ids, f"失效通道仍出现在摄像树: {ids}"
    assert ids == {WvpStub.CHANNEL_A}

    # 2) 失效通道不可再操作（统一 404，而不是带无效参数去调 WVP 报 502）
    assert (await bank_client.post(f"/api/play/{stale_id}")).status_code == 404
    assert (await bank_client.post(
        f"/api/playback/{stale_id}",
        json={"startTime": RANGE_START, "endTime": RANGE_END})).status_code == 404
    assert (await bank_client.get(
        f"/api/record/{stale_id}",
        params={"startTime": RANGE_START, "endTime": RANGE_END})).status_code == 404
    assert (await bank_client.post("/api/download-tasks", json={
        "channelId": stale_id, "startTime": RANGE_START, "endTime": RANGE_END})).status_code == 404

    # 3) 授权列表仍能看到它（带 active=false），便于管理员清理
    r = await admin.get(f"/api/admin/users/{seeded['uid']}/grants")
    grants = {g["channelId"]: g for g in r.json()}
    assert grants[stale_id]["active"] is False

    # 4) 不能再给失效通道新增授权
    r = await admin.put(f"/api/admin/users/{seeded['uid']}/grants", json={"grants": [
        {"channelId": seeded["channels"][WvpStub.CHANNEL_A]["id"], "canLive": True},
        {"channelId": stale_id, "canLive": True},
    ]})
    assert r.status_code == 400, r.text
    assert "失效" in r.json()["detail"]

    # 5) 管理端台账默认仍列出它（active=false），保留历史可追溯
    r = await admin.get("/api/admin/channels", params={"count": 50})
    ledger = {c["channelId"]: c for c in r.json()["list"]}
    assert ledger[WvpStub.CHANNEL_B]["active"] is False


async def test_stale_grant_can_be_revoked(app_ctx, bank_client, seeded):
    """只提交可用通道（失效通道不提交）即为收回其授权。"""
    admin = seeded["admin"]
    r = await admin.put(f"/api/admin/users/{seeded['uid']}/grants", json={"grants": [
        {"channelId": seeded["channels"][WvpStub.CHANNEL_A]["id"], "canLive": True},
    ]})
    assert r.status_code == 200, r.text
    r = await admin.get(f"/api/admin/users/{seeded['uid']}/grants")
    assert WvpStub.CHANNEL_B not in {g["channelGbId"] for g in r.json()}
    # 审计里应留下收回记录
    r = await admin.get("/api/admin/audit", params={"action": "GRANT_REMOVED", "count": 5})
    assert r.json()["total"] >= 1
