"""密码哈希（bcrypt）与 JWT 会话令牌。"""
import base64
import secrets
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt

from app.config import get_settings

COOKIE_NAME = "portal_session"


def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt(rounds=12)).decode("ascii")


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("ascii"))
    except ValueError:
        return False


def _jwt_secret() -> str:
    s = get_settings().jwt_secret
    if not s:
        # 未配置时随机生成并写回内存（重启即全部会话失效，生产必须配置 JWT_SECRET）
        import logging
        generated = secrets.token_urlsafe(48)
        get_settings().jwt_secret = generated
        logging.getLogger(__name__).warning("JWT_SECRET 未配置，已生成临时密钥（重启后所有会话失效）")
        return generated
    return s


def create_session_token(user_id: int, session_version: int) -> str:
    ttl_hours = get_settings().jwt_ttl_hours
    payload = {
        "sub": str(user_id),
        "ver": session_version,
        "iat": int(datetime.now(timezone.utc).timestamp()),
        "exp": datetime.now(timezone.utc) + timedelta(hours=ttl_hours),
    }
    return jwt.encode(payload, _jwt_secret(), algorithm="HS256")


def decode_session_token(token: str) -> dict:
    """返回 payload；无效/过期抛 jwt.InvalidTokenError。"""
    return jwt.decode(token, _jwt_secret(), algorithms=["HS256"])


def token_expiring_soon(payload: dict) -> bool:
    """剩余有效期不足一半时滑动续期。"""
    exp = payload.get("exp")
    if not exp:
        return False
    remaining = exp - datetime.now(timezone.utc).timestamp()
    return remaining < get_settings().jwt_ttl_hours * 3600 / 2


def new_stream_token() -> str:
    return secrets.token_urlsafe(32)
