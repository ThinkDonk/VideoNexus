"""回放暂停/恢复设备能力标记测试。

背景：部分 NVR（如海康）不支持 GB28181 回放的 pause/resume，WVP 固定返回
"暂停RTP接收失败"。门户应改为把该通道标记为不支持，让前端置灰按钮，
并且设备恢复支持后能自愈。
"""
import pytest_asyncio

RANGE_START = "2026-09-01 00:00:00"
RANGE_END = "2026-09-01 05:00:00"


@pytest_asyncio.fixture(scope="module", autouse=True)
async def seeded(app_ctx):
    """复用 admin（ADMIN 角色对所有通道有权限），确保通道台账已同步。"""
    from httpx import ASGITransport, AsyncClient as _AC
    app, stub = app_ctx
    async with _AC(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.post("/api/auth/login",
                              json={"username": "admin", "password": "Admin@12345"})
        assert r.status_code == 200, r.text
        r = await client.post("/api/admin/channels/sync")
        assert r.status_code == 200, r.text
        r = await client.get("/api/admin/channels", params={"count": 50})
        channels = {c["channelId"]: c for c in r.json()["list"]}
        return {"channels": channels}


async def _start_playback(client, channel_pk):
    r = await client.post(f"/api/playback/{channel_pk}",
                          json={"startTime": RANGE_START, "endTime": RANGE_END})
    assert r.status_code == 200, r.text
    return r.json()


async def test_pause_unsupported_marks_channel(app_ctx, admin_client, seeded):
    app, stub = app_ctx
    ch_pk = next(iter(seeded["channels"].values()))["id"]
    stub.pause_fails = True

    body = await _start_playback(admin_client, ch_pk)
    assert body["capabilities"]["pause"] is True  # 初始默认支持
    sid = body["sessionId"]

    r = await admin_client.post(f"/api/playback/sessions/{sid}/pause")
    assert r.status_code == 409, r.text
    assert "不支持" in r.json()["detail"]

    # 重新发起回放：capabilities 反映为不支持
    body2 = await _start_playback(admin_client, ch_pk)
    assert body2["capabilities"]["pause"] is False
    assert body2["capabilities"]["seek"] is True and body2["capabilities"]["speed"] is True

    # resume 同样返回友好错误
    r = await admin_client.post(f"/api/playback/sessions/{body2['sessionId']}/resume")
    assert r.status_code == 409, r.text


async def test_pause_recovers_when_supported_again(app_ctx, admin_client, seeded):
    app, stub = app_ctx
    ch_pk = next(iter(seeded["channels"].values()))["id"]

    stub.pause_fails = False  # 设备恢复支持
    body = await _start_playback(admin_client, ch_pk)
    assert body["capabilities"]["pause"] is False  # 仍是上次标记的不支持
    r = await admin_client.post(f"/api/playback/sessions/{body['sessionId']}/pause")
    assert r.status_code == 200, r.text  # 实测成功

    body2 = await _start_playback(admin_client, ch_pk)
    assert body2["capabilities"]["pause"] is True  # 自愈


async def test_seek_speed_unaffected(app_ctx, admin_client, seeded):
    app, stub = app_ctx
    ch_pk = next(iter(seeded["channels"].values()))["id"]
    body = await _start_playback(admin_client, ch_pk)
    sid = body["sessionId"]
    assert (await admin_client.post(f"/api/playback/sessions/{sid}/seek",
                              json={"seconds": 30})).status_code == 200
    assert (await admin_client.post(f"/api/playback/sessions/{sid}/speed",
                              json={"speed": 4})).status_code == 200
