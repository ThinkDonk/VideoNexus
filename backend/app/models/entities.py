"""数据模型：机构/用户/通道镜像/通道授权/播放会话/下载任务/审计日志。"""
from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


def _now() -> datetime:
    from app.core.timezone import now
    return now()


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)


class Org(Base, TimestampMixin):
    __tablename__ = "orgs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(128), unique=True)
    status: Mapped[bool] = mapped_column(Boolean, default=True)
    ip_whitelist: Mapped[str | None] = mapped_column(Text, nullable=True)  # 逗号分隔 IP/CIDR，空=不限
    max_concurrent_plays: Mapped[int] = mapped_column(Integer, default=4)  # 机构同时在线播放路数上限
    quota_gb: Mapped[int] = mapped_column(Integer, default=50)  # 下载文件存储配额
    remark: Mapped[str | None] = mapped_column(Text, nullable=True)


class User(Base, TimestampMixin):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    org_id: Mapped[int | None] = mapped_column(ForeignKey("orgs.id"), nullable=True)  # ADMIN/AUDITOR 可无机构
    username: Mapped[str] = mapped_column(String(64), unique=True)
    password_hash: Mapped[str] = mapped_column(String(128))
    display_name: Mapped[str] = mapped_column(String(128), default="")
    role: Mapped[str] = mapped_column(String(16), default="BANK_USER")  # ADMIN / AUDITOR / BANK_USER
    status: Mapped[bool] = mapped_column(Boolean, default=True)
    must_change_password: Mapped[bool] = mapped_column(Boolean, default=True)
    failed_attempts: Mapped[int] = mapped_column(Integer, default=0)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    session_version: Mapped[int] = mapped_column(Integer, default=0)  # 单会话模式下递增使旧 token 失效
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class Channel(Base, TimestampMixin):
    """通道镜像：数据来源为 WVP 定时同步，display_name 为对银行展示的可编辑别名。"""
    __tablename__ = "channels"
    __table_args__ = (UniqueConstraint("device_id", "channel_id", name="uq_channel_device"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    device_id: Mapped[str] = mapped_column(String(64), index=True)  # 设备国标编号
    channel_id: Mapped[str] = mapped_column(String(64), index=True)  # 通道国标编号
    device_name: Mapped[str] = mapped_column(String(128), default="")
    name: Mapped[str] = mapped_column(String(128), default="")
    display_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    online: Mapped[bool] = mapped_column(Boolean, default=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True)  # 最近一次同步是否仍存在于 WVP
    # 回放暂停/恢复能力：部分设备（如海康 NVR）不支持，WVP 会固定报错；
    # 实测失败即置 false，播放接口据此让前端置灰按钮（成功后自愈）
    pause_supported: Mapped[bool] = mapped_column(Boolean, default=True, server_default="1")
    last_sync_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class ChannelGrant(Base, TimestampMixin):
    """核心数据权限：用户↔通道，三种动作开关 + 有效期。"""
    __tablename__ = "channel_grants"
    __table_args__ = (UniqueConstraint("user_id", "channel_id", name="uq_grant_user_channel"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    channel_id: Mapped[int] = mapped_column(ForeignKey("channels.id"), index=True)
    can_live: Mapped[bool] = mapped_column(Boolean, default=False)
    can_playback: Mapped[bool] = mapped_column(Boolean, default=False)
    can_download: Mapped[bool] = mapped_column(Boolean, default=False)
    valid_from: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    valid_until: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    granted_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)


class PlaySession(Base):
    """一次点播/回放：stream_token 供 Nginx auth_request 校验（st 参数）。"""
    __tablename__ = "play_sessions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    channel_id: Mapped[int] = mapped_column(ForeignKey("channels.id"), index=True)
    session_type: Mapped[str] = mapped_column(String(16))  # LIVE / PLAYBACK
    app: Mapped[str] = mapped_column(String(32), default="rtp")
    stream: Mapped[str] = mapped_column(String(128))
    stream_token: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    duration_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime)  # 超时由清理任务强制关闭


class DownloadTask(Base, TimestampMixin):
    __tablename__ = "download_tasks"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    channel_id: Mapped[int] = mapped_column(ForeignKey("channels.id"), index=True)
    start_time: Mapped[datetime] = mapped_column(DateTime)
    end_time: Mapped[datetime] = mapped_column(DateTime)
    status: Mapped[str] = mapped_column(String(16), default="PENDING")  # PENDING/RUNNING/COMPLETE/FAILED/EXPIRED
    wvp_stream: Mapped[str | None] = mapped_column(String(128), nullable=True)
    progress: Mapped[int] = mapped_column(Integer, default=0)
    file_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    file_size: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class AuditLog(Base):
    """审计日志：只追加。username/org_name 为快照，防止事后删号影响追责。"""
    __tablename__ = "audit_logs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ts: Mapped[datetime] = mapped_column(DateTime, default=_now, index=True)
    user_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    username: Mapped[str | None] = mapped_column(String(64), nullable=True)
    org_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    org_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    action: Mapped[str] = mapped_column(String(32), index=True)
    object_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    object_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    params: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON 字符串
    result: Mapped[str | None] = mapped_column(String(16), nullable=True)
    ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    ua: Mapped[str | None] = mapped_column(String(255), nullable=True)


Index("ix_audit_action_ts", AuditLog.action, AuditLog.ts)
