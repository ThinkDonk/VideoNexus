"""门户配置：全部来自环境变量（部署时由 docker-compose 注入），见 deploy/.env.example。"""
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # --- 基础 ---
    data_dir: str = "./data"
    database_url: str = ""  # 留空则自动使用 sqlite+aiosqlite://{data_dir}/portal.db
    tz: str = "Asia/Shanghai"

    # --- 会话 ---
    jwt_secret: str = ""  # 留空则启动时随机生成（重启失效，生产必须显式配置）
    jwt_ttl_hours: int = 2  # 滑动续期：剩余不足一半时自动续
    public_https: bool = True  # 决定签发 ws:// 还是 wss:// 播放地址
    single_session: bool = False  # true=同一账号新登录踢旧会话

    # --- 登录安全 ---
    login_max_failures: int = 5
    login_lock_minutes: int = 30

    # --- WVP / ZLM ---
    wvp_base_url: str = "http://127.0.0.1:18080"
    wvp_api_key: str = ""  # 优先；为空时回退账号密码自动重登
    wvp_username: str = ""
    wvp_password: str = ""
    wvp_request_timeout: float = 70.0  # WVP 点播/回放为异步接口，需覆盖其 play-timeout
    zlm_download_base_url: str = ""  # 可选：改写 WVP 返回的 ZLM 下载直链 host（门户后端拉文件用）
    zlm_secret: str = ""

    # --- 本地开发（无 Nginx）---
    dev_stream_proxy: bool = False  # true=后端自身承担 /stream/ 鉴权与转发（本地跑通播放用）

    # --- 初始管理员（首次启动无管理员时创建）---
    initial_admin_username: str = "admin"
    initial_admin_password: str = ""  # 留空则随机生成并打印到日志一次

    # --- 通道同步 ---
    channel_sync_minutes: int = 5

    # --- 播放会话 ---
    play_session_max_hours: int = 12  # 播放会话最长存续，超时由清理任务关闭

    # --- 下载任务 ---
    download_speed: int = 4  # GB28181 下载倍速
    download_max_duration_hours: int = 4  # 单次下载时间段上限
    download_max_running_per_user: int = 2
    download_poll_seconds: int = 10
    file_retention_days: int = 7
    org_default_quota_gb: int = 50  # 机构下载文件存储配额

    @property
    def effective_database_url(self) -> str:
        if self.database_url:
            return self.database_url
        Path(self.data_dir).mkdir(parents=True, exist_ok=True)
        return f"sqlite+aiosqlite:///{self.data_dir}/portal.db"

    @property
    def downloads_dir(self) -> Path:
        p = Path(self.data_dir) / "downloads"
        p.mkdir(parents=True, exist_ok=True)
        return p


_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings


def reset_settings() -> None:
    """仅测试用：让下一次 get_settings 重新读环境。"""
    global _settings
    _settings = None
