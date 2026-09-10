"""统一使用本地时区（默认 Asia/Shanghai）的 naive datetime，与 WVP 接口口径一致。

说明：SQLite/MySQL 的 DateTime 列按 naive 值存取；中国无夏令时，naive 本地时间无歧义。
JWT 过期时间单独用 UTC epoch 计算，见 core/security.py。
"""
from datetime import datetime
from zoneinfo import ZoneInfo

from app.config import get_settings

_TZ = None


def _tz() -> ZoneInfo:
    global _TZ
    if _TZ is None:
        _TZ = ZoneInfo(get_settings().tz)
    return _TZ


def now() -> datetime:
    return datetime.now(_tz()).replace(tzinfo=None)


def parse_dt(s: str) -> datetime:
    """解析 'yyyy-MM-dd HH:mm:ss'（WVP 口径），返回 naive 本地时间。"""
    s = s.strip().replace("T", " ")
    return datetime.strptime(s, "%Y-%m-%d %H:%M:%S")


def fmt_dt(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    return dt.strftime("%Y-%m-%d %H:%M:%S")
