"""API 请求/响应模型。"""
from datetime import datetime

from pydantic import BaseModel, Field


# ---------- 认证 ----------

class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=128)


class ChangePasswordRequest(BaseModel):
    oldPassword: str
    newPassword: str = Field(min_length=8, max_length=128)


class UserInfo(BaseModel):
    id: int
    username: str
    displayName: str
    role: str
    orgId: int | None = None
    orgName: str | None = None
    mustChangePassword: bool


# ---------- 通道 ----------

class ChannelNode(BaseModel):
    channelId: int
    channelGbId: str
    name: str
    online: bool
    grants: dict[str, bool] | None = None


class DeviceGroup(BaseModel):
    deviceId: str
    deviceName: str
    children: list[ChannelNode]


class ChannelTree(BaseModel):
    total: int
    devices: list[DeviceGroup]


# ---------- 播放 ----------

class PlayStartResponse(BaseModel):
    sessionId: int
    channelId: int
    channelName: str
    channelGbId: str
    type: str
    stream: str
    urls: dict[str, str]
    expiresAt: str | None


class PlaybackStartRequest(BaseModel):
    startTime: str  # yyyy-MM-dd HH:mm:ss
    endTime: str


class SeekRequest(BaseModel):
    seconds: int = Field(ge=0)


class SpeedRequest(BaseModel):
    speed: float  # 0.25/0.5/1/2/4/8


# ---------- 录像 ----------

class RecordItem(BaseModel):
    startTime: str
    endTime: str
    durationSeconds: int
    type: str | None = None


class RecordQueryResponse(BaseModel):
    channelId: int
    records: list[RecordItem]


# ---------- 下载任务 ----------

class DownloadCreateRequest(BaseModel):
    channelId: int
    startTime: str
    endTime: str


class DownloadTaskInfo(BaseModel):
    id: int
    channelId: int
    channelName: str | None = None
    channelGbId: str | None = None
    username: str | None = None
    orgName: str | None = None
    startTime: str
    endTime: str
    status: str
    progress: int
    fileSize: int | None
    expiresAt: str | None
    error: str | None
    createdAt: str | None
    completedAt: str | None


# ---------- 管理端 ----------

class OrgCreate(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    status: bool = True
    ipWhitelist: str | None = None
    maxConcurrentPlays: int = Field(default=4, ge=1, le=64)
    quotaGb: int = Field(default=50, ge=1, le=10000)
    remark: str | None = None


class OrgUpdate(OrgCreate):
    pass


class UserCreate(BaseModel):
    username: str = Field(min_length=2, max_length=64, pattern=r"^[A-Za-z0-9_.\-]+$")
    password: str = Field(min_length=8, max_length=128)
    displayName: str = ""
    orgId: int | None = None
    role: str = Field(pattern=r"^(BANK_USER|ADMIN|AUDITOR)$")


class UserUpdate(BaseModel):
    displayName: str | None = None
    orgId: int | None = None
    role: str | None = Field(default=None, pattern=r"^(BANK_USER|ADMIN|AUDITOR)$")
    status: bool | None = None


class ResetPasswordRequest(BaseModel):
    newPassword: str = Field(min_length=8, max_length=128)


class GrantItem(BaseModel):
    channelId: int
    canLive: bool = False
    canPlayback: bool = False
    canDownload: bool = False
    validFrom: str | None = None
    validUntil: str | None = None


class GrantsSaveRequest(BaseModel):
    grants: list[GrantItem]


class ChannelUpdate(BaseModel):
    displayName: str | None = None
