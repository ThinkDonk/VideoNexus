"""认证：登录（含锁定）、登出、当前用户、修改密码。"""
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.core.db import get_db
from app.core.deps import client_ip, get_current_user, set_session_cookie
from app.core.security import COOKIE_NAME, create_session_token, hash_password, verify_password
from app.core.timezone import now
from app.models import Org, User
from app.schemas import ChangePasswordRequest, LoginRequest, UserInfo
from app.services import audit
from app.services.audit import AuditAction

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _set_login_cookie(response: Response, user: User) -> None:
    set_session_cookie(response, create_session_token(user.id, user.session_version))


@router.post("/login")
async def login(body: LoginRequest, request: Request, response: Response,
                db: AsyncSession = Depends(get_db)):
    s = get_settings()
    ip = client_ip(request)
    ua = request.headers.get("user-agent")

    r = await db.execute(select(User).where(User.username == body.username))
    user = r.scalar_one_or_none()

    generic_err = HTTPException(status_code=401, detail="用户名或密码错误")

    async def _fail(exc: HTTPException, **audit_kwargs):
        # 失败路径的锁定状态与审计必须落库（get_db 异常时会回滚未提交变更）
        await audit.write(db, **audit_kwargs)
        await db.commit()
        raise exc

    r = await db.execute(select(User).where(User.username == body.username))
    user = r.scalar_one_or_none()
    if user is None:
        await _fail(generic_err, action=AuditAction.LOGIN_FAIL, username=body.username,
                    result="user_not_found", ip=ip, ua=ua)
    if user.locked_until and now() < user.locked_until:
        await _fail(HTTPException(status_code=423, detail="账号已锁定，请稍后再试"),
                    action=AuditAction.LOGIN_LOCKED, user=user, result="locked", ip=ip, ua=ua)
    if not user.status:
        await _fail(HTTPException(status_code=403, detail="账号已停用，请联系管理员"),
                    action=AuditAction.LOGIN_FAIL, user=user, result="disabled", ip=ip, ua=ua)
    # 机构 IP 白名单
    if user.org_id is not None and user.role == "BANK_USER":
        org = (await db.execute(select(Org).where(Org.id == user.org_id))).scalar_one_or_none()
        if org and not org.status:
            await _fail(HTTPException(status_code=403, detail="所属机构已停用"),
                        action=AuditAction.LOGIN_FAIL, user=user, result="org_disabled", ip=ip, ua=ua)
        if org and org.ip_whitelist and not _ip_allowed(ip, org.ip_whitelist):
            await _fail(HTTPException(status_code=403, detail="当前网络不在允许范围内"),
                        action=AuditAction.LOGIN_FAIL, user=user,
                        result="ip_not_allowed", ip=ip, ua=ua)

    if not verify_password(body.password, user.password_hash):
        user.failed_attempts += 1
        if user.failed_attempts >= s.login_max_failures:
            from datetime import timedelta
            user.locked_until = now() + timedelta(minutes=s.login_lock_minutes)
            user.failed_attempts = 0
            await _fail(generic_err, action=AuditAction.LOGIN_LOCKED, user=user,
                        result="too_many_failures", ip=ip, ua=ua)
        else:
            await _fail(generic_err, action=AuditAction.LOGIN_FAIL, user=user,
                        result="wrong_password", ip=ip, ua=ua)

    # 登录成功
    user.failed_attempts = 0
    user.locked_until = None
    user.last_login_at = now()
    if s.single_session:
        user.session_version += 1
    _set_login_cookie(response, user)
    await audit.write(db, action=AuditAction.LOGIN_SUCCESS, user=user, ip=ip, ua=ua)
    return {"mustChangePassword": user.must_change_password}


def _ip_allowed(ip: str, whitelist: str) -> bool:
    import ipaddress
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return False
    for item in whitelist.split(","):
        item = item.strip()
        if not item:
            continue
        try:
            if addr in ipaddress.ip_network(item, strict=False):
                return True
        except ValueError:
            continue
    return False


@router.post("/logout")
async def logout(request: Request, response: Response, user: User = Depends(get_current_user),
                 db: AsyncSession = Depends(get_db)):
    response.delete_cookie(COOKIE_NAME, path="/")
    await audit.write(db, action=AuditAction.LOGOUT, user=user, ip=client_ip(request),
                      ua=request.headers.get("user-agent"))
    return {"ok": True}


@router.get("/me", response_model=UserInfo)
async def me(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    org_name = None
    if user.org_id is not None:
        org = (await db.execute(select(Org).where(Org.id == user.org_id))).scalar_one_or_none()
        org_name = org.name if org else None
    return UserInfo(id=user.id, username=user.username, displayName=user.display_name,
                    role=user.role, orgId=user.org_id, orgName=org_name,
                    mustChangePassword=user.must_change_password)


@router.post("/password")
async def change_password(body: ChangePasswordRequest, request: Request,
                          user: User = Depends(get_current_user),
                          db: AsyncSession = Depends(get_db)):
    if not verify_password(body.oldPassword, user.password_hash):
        raise HTTPException(status_code=400, detail="原密码错误")
    user.password_hash = hash_password(body.newPassword)
    user.must_change_password = False
    await audit.write(db, action=AuditAction.PASSWORD_CHANGE, user=user,
                      ip=client_ip(request), ua=request.headers.get("user-agent"))
    return {"ok": True}
