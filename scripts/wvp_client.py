"""WVP API 验证脚本公共客户端与配置加载。

使用前：复制 wvp_config.example.json 为 wvp_config.json 并填写真实环境信息。
优先使用 wvp_api_key（WVP >= 2.7.x 支持）；留空则回退为账号密码自动登录。
"""
import hashlib
import json
import os
import sys
from pathlib import Path

import requests

CONFIG_PATH = Path(__file__).parent / "wvp_config.json"


def load_config() -> dict:
    if not CONFIG_PATH.exists():
        print(f"[错误] 未找到配置文件 {CONFIG_PATH}")
        print("       请先执行: cp wvp_config.example.json wvp_config.json 并填写真实环境信息")
        sys.exit(1)
    with open(CONFIG_PATH, encoding="utf-8") as f:
        return json.load(f)


class WvpClient:
    """最小 WVP REST 客户端（验证用），支持 api-key 与账号登录两种认证。"""

    def __init__(self, cfg: dict):
        self.base = cfg["wvp_base_url"].rstrip("/")
        self.api_key = (cfg.get("wvp_api_key") or "").strip()
        self.username = (cfg.get("wvp_username") or "").strip()
        self.password = (cfg.get("wvp_password") or "").strip()
        self.timeout = 60  # play/playback/download 为异步 DeferredResult，需留足时间
        self.http = requests.Session()
        self.token = None
        self.auth_mode = "api-key" if self.api_key else "login"

    # ---------- 认证 ----------

    def _headers(self) -> dict:
        if self.api_key:
            return {"api-key": self.api_key}
        if self.token:
            return {"access-token": self.token}
        return {}

    def login(self) -> None:
        # WVP 登录接口要求密码为 32 位小写 MD5
        pwd_md5 = hashlib.md5(self.password.encode()).hexdigest()
        r = self.http.get(
            f"{self.base}/api/user/login",
            params={"username": self.username, "password": pwd_md5},
            timeout=self.timeout,
        )
        body = r.json()
        if body.get("code") != 0:
            raise RuntimeError(f"登录失败: {body}")
        self.token = body["data"]["accessToken"]

    def request(self, method: str, path: str, *, params=None, **kw) -> dict:
        url = f"{self.base}{path}"
        resp = self.http.request(method, url, params=params, headers=self._headers(),
                                 timeout=self.timeout, **kw)
        if resp.status_code == 401 and not self.api_key:
            # token 过期自动重登一次
            self.login()
            resp = self.http.request(method, url, params=params, headers=self._headers(),
                                     timeout=self.timeout, **kw)
        resp.raise_for_status()
        return resp.json()

    def get(self, path: str, params=None) -> dict:
        return self.request("GET", path, params=params)

    # ---------- 业务接口封装 ----------

    def devices(self, page=1, count=100) -> dict:
        return self.get("/api/device/query/devices", {"page": page, "count": count})

    def channels(self, device_id: str, page=1, count=100) -> dict:
        return self.get(f"/api/device/query/devices/{device_id}/channels",
                        {"page": page, "count": count})

    def play_start(self, device_id: str, channel_id: str) -> dict:
        return self.get(f"/api/play/start/{device_id}/{channel_id}")

    def play_stop(self, device_id: str, channel_id: str) -> dict:
        return self.get(f"/api/play/stop/{device_id}/{channel_id}")

    def record_query(self, device_id: str, channel_id: str, start: str, end: str) -> dict:
        return self.get(f"/api/gb_record/query/{device_id}/{channel_id}",
                        {"startTime": start, "endTime": end})

    def playback_start(self, device_id: str, channel_id: str, start: str, end: str) -> dict:
        return self.get(f"/api/playback/start/{device_id}/{channel_id}",
                        {"startTime": start, "endTime": end})

    def playback_control(self, op: str, stream_id: str, *args) -> dict:
        return self.get(f"/api/playback/{op}/{stream_id}" + ("/" + "/".join(args) if args else ""))

    def playback_stop(self, device_id: str, channel_id: str, stream: str) -> dict:
        return self.get(f"/api/playback/stop/{device_id}/{channel_id}/{stream}")

    def download_start(self, device_id: str, channel_id: str, start: str, end: str, speed: int) -> dict:
        return self.get(f"/api/gb_record/download/start/{device_id}/{channel_id}",
                        {"startTime": start, "endTime": end, "downloadSpeed": speed})

    def download_progress(self, device_id: str, channel_id: str, stream: str) -> dict:
        return self.get(f"/api/gb_record/download/progress/{device_id}/{channel_id}/{stream}")

    def download_stop(self, device_id: str, channel_id: str, stream: str) -> dict:
        return self.get(f"/api/gb_record/download/stop/{device_id}/{channel_id}/{stream}")


def check(body: dict, what: str) -> dict:
    """校验 WVPResult 包装，code==0 视为成功。"""
    if body.get("code") != 0:
        print(f"  [失败] {what}: code={body.get('code')} msg={body.get('msg')}")
        return body
    print(f"  [成功] {what}")
    return body


def section(title: str) -> None:
    print("\n" + "=" * 60)
    print(f"# {title}")
    print("=" * 60)


def pick_test_channel(cfg: dict, client: WvpClient):
    """返回 (device_id, channel_id)：优先取配置，否则取第一个在线设备的首个通道。"""
    t = cfg["test"]
    if t.get("device_id") and t.get("channel_id"):
        return t["device_id"], t["channel_id"]
    print("  配置中未指定 test.device_id/channel_id，自动选取第一个设备的首个通道 ...")
    devices = client.devices()
    if devices.get("code") != 0 or not devices["data"].get("list"):
        raise RuntimeError(f"未查询到任何设备: {devices}")
    dev = devices["data"]["list"][0]
    print(f"  选用设备: {dev['deviceId']} ({dev.get('name', '')}) 在线={dev.get('onLine')}")
    chans = client.channels(dev["deviceId"])
    if chans.get("code") != 0 or not chans["data"].get("list"):
        raise RuntimeError(f"该设备下未查询到通道: {chans}")
    ch = chans["data"]["list"][0]
    print(f"  选用通道: {ch['deviceId']} ({ch.get('name', '')})")
    return dev["deviceId"], ch["deviceId"]


if __name__ == "__main__":
    cfg = load_config()
    c = WvpClient(cfg)
    if not c.api_key:
        c.login()
        print("登录 OK, token 已获取")
