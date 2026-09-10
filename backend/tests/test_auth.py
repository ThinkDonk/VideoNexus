"""认证链路测试：登录、锁定、改密、会话。"""
import pytest
from tests.conftest import login


async def _reset_admin_lock():
    from app.core.db import _session_factory
    from app.models import User
    from sqlalchemy import select
    async with _session_factory() as db:
        r = await db.execute(select(User).where(User.username == "admin"))
        u = r.scalar_one()
        u.failed_attempts = 0
        u.locked_until = None
        await db.commit()


async def test_login_success_sets_cookie(admin_client):
    r = await admin_client.get("/api/auth/me")
    assert r.status_code == 200
    body = r.json()
    assert body["username"] == "admin"
    assert body["role"] == "ADMIN"
    assert body["mustChangePassword"] is True


async def test_login_wrong_password(client):
    r = await login(client, "admin", "wrong-password-1")
    assert r.status_code == 401
    await _reset_admin_lock()


async def test_login_lockout(client):
    # LOGIN_MAX_FAILURES=3：连续失败 3 次后锁定，正确密码也进不来
    for _ in range(3):
        r = await login(client, "admin", "wrong-password-1")
        assert r.status_code == 401
    r = await login(client, "admin", "Admin@12345")
    assert r.status_code == 423
    r = await login(client, "admin", "Admin@12345")
    assert r.status_code == 423
    await _reset_admin_lock()


async def test_change_password(client):
    r = await login(client, "admin", "Admin@12345")
    assert r.status_code == 200
    r = await client.post("/api/auth/password",
                          json={"oldPassword": "Admin@12345", "newPassword": "NewPass@12345"})
    assert r.status_code == 200
    # 旧密码失效
    r = await login(client, "admin", "Admin@12345")
    assert r.status_code == 401
    # 新密码可用
    r = await login(client, "admin", "NewPass@12345")
    assert r.status_code == 200
    r = await client.get("/api/auth/me")
    assert r.status_code == 200
    assert r.json()["mustChangePassword"] is False
    # 改回，避免影响其他测试
    await client.post("/api/auth/password",
                      json={"oldPassword": "NewPass@12345", "newPassword": "Admin@12345"})


async def test_unauthenticated_access(client):
    r = await client.get("/api/channels/tree")
    assert r.status_code == 401


async def test_logout(admin_client):
    r = await admin_client.post("/api/auth/logout")
    assert r.status_code == 200
    r = await admin_client.get("/api/auth/me")
    assert r.status_code == 401
