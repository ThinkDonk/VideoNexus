"""FastAPI 依赖：当前用户、角色控制、客户端 IP。"""
import jwt as pyjwt
from fastapi import Depends, HTTPException, Request, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.security import COOKIE_NAME, create_session_token, decode_session_token, token_expiring_soon
from app.models import User


def client_ip(request: Request) -> str:
    # 部署形态下请求必经 Nginx，X-Real-IP 可信
    return request.headers.get("x-real-ip") or (request.client.host if request.client else "unknown")


async def _load_user(db: AsyncSession, user_id: int) -> User | None:
    result = await db.execute(select(User).where(User.id == user_id))
    return result.scalar_one_or_none()


async def get_current_user(
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> User:
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        raise HTTPException(status_code=401, detail="未登录")
    try:
        payload = decode_session_token(token)
    except pyjwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="会话已过期，请重新登录")

    user = await _load_user(db, int(payload["sub"]))
    if user is None or not user.status:
        raise HTTPException(status_code=401, detail="账号不存在或已停用")
    if payload.get("ver", 0) != user.session_version:
        raise HTTPException(status_code=401, detail="会话已在别处失效，请重新登录")

    # 滑动续期
    if token_expiring_soon(payload):
        set_session_cookie(response, create_session_token(user.id, user.session_version))
    return user


def set_session_cookie(response: Response, token: str) -> None:
    from app.config import get_settings
    s = get_settings()
    response.set_cookie(
        COOKIE_NAME,
        token,
        max_age=s.jwt_ttl_hours * 3600,
        httponly=True,
        secure=s.public_https,
        samesite="lax",
        path="/",
    )


def require_roles(*roles: str):
    async def _checker(user: User = Depends(get_current_user)) -> User:
        if user.role not in roles:
            raise HTTPException(status_code=403, detail="无权限执行此操作")
        return user
    return _checker


require_admin = require_roles("ADMIN")
require_auditor = require_roles("ADMIN", "AUDITOR")
