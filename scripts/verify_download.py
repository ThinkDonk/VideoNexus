#!/usr/bin/env python3
"""验证6：录像下载全链路（门户下载任务的技术底座）。

验证内容：
1. /api/gb_record/download/start 以指定倍速发起 GB28181 下载
2. 轮询 /api/gb_record/download/progress 直至完成，统计总耗时与等效倍速
3. 完成后拿到 downLoadFilePath（ZLM 上的 MP4 直链）
4. 实测 ZLM downloadFile 接口是否需要 secret（决定门户拉文件的方式）
5. 完整下载 MP4 文件到本地，核对文件大小

注意：下载耗时长，请把 test.download_max_wait_minutes 设置得足够大。
"""
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import requests

from wvp_client import WvpClient, load_config, section, check, pick_test_channel

OUT_DIR = Path(__file__).parent / "_download_out"


def rewrite_zlm_host(url: str, zlm_base: str) -> str:
    """若返回的直链 host 从本机不可达（如配置了公网 stream-ip），用 zlm_base_url 替换。"""
    if not zlm_base:
        return url
    b = urlsplit(zlm_base)
    s = urlsplit(url)
    if s.netloc == b.netloc:
        return url
    return urlunsplit((b.scheme, b.netloc, s.path, s.query, s.frag if hasattr(s, 'frag') else ""))


def try_download(url: str, tag: str) -> tuple[bool, int]:
    """GET 一个 URL，返回 (是否成功, 状态码)。"""
    try:
        r = requests.get(url, stream=True, timeout=(5, 20))
        if r.status_code == 200:
            r.close()
            print(f"  [{tag}] HTTP 200 -> 可下载 ✓")
            return True, 200
        print(f"  [{tag}] HTTP {r.status_code} -> {'不可用' if r.status_code in (401, 403) else '异常'} "
              f"(body: {r.text[:120]})")
        return False, r.status_code
    except Exception as e:
        print(f"  [{tag}] 请求异常: {e}")
        return False, -1


def main():
    cfg = load_config()
    client = WvpClient(cfg)
    if not client.api_key:
        client.login()
    section("验证6：录像下载全链路")

    device_id, channel_id = pick_test_channel(cfg, client)
    t = cfg["test"]
    speed = int(t.get("download_speed", 4))
    print(f"  目标: device={device_id} channel={channel_id}")
    print(f"  下载时间段: {t['record_start']} ~ {t['record_end']}  倍速: {speed}")

    # 预估录像时长
    try:
        s = datetime.fromisoformat(t["record_start"])
        e = datetime.fromisoformat(t["record_end"])
        span_min = (e - s).total_seconds() / 60
        print(f"  申请跨度: {span_min:.0f} 分钟；预估耗时 ≈ {span_min/speed:.0f} 分钟（{speed} 倍速）")
    except Exception:
        pass

    t0 = time.time()
    body = client.download_start(device_id, channel_id, t["record_start"], t["record_end"], speed)
    if body.get("code") != 0:
        print(f"  [失败] download/start: code={body.get('code')} msg={body.get('msg')}")
        return
    stream = body["data"]
    stream_id = stream.get("stream")
    print(f"  [成功] download/start 耗时 {time.time()-t0:.1f}s  stream={stream_id}")

    # 轮询进度
    max_wait = int(t.get("download_max_wait_minutes", 30)) * 60
    last_progress = -1
    file_path = None
    while time.time() - t0 < max_wait:
        time.sleep(10)
        prog = client.download_progress(device_id, channel_id, stream_id)
        if prog.get("code") != 0:
            print(f"  [失败] progress: {prog.get('msg')}")
            break
        data = prog["data"]
        p = data.get("progress")
        if p is not None and p != last_progress:
            print(f"  进度: {p}%  (已耗时 {(time.time()-t0)/60:.1f} 分钟)")
            last_progress = p
        dl = data.get("downLoadFilePath") or (data.get("mediaInfo") or {}).get("downLoadFilePath")
        if isinstance(dl, dict):
            file_path = dl
            break
        if data.get("progress") == 100:
            # 有的版本完成后 downLoadFilePath 放在 mediaInfo 里，再等一轮
            time.sleep(3)
            prog2 = client.download_progress(device_id, channel_id, stream_id)
            dl2 = (prog2.get("data") or {}).get("downLoadFilePath")
            if isinstance(dl2, dict):
                file_path = dl2
            break
    if not file_path:
        print(f"  [失败] 等待 {max_wait/60:.0f} 分钟未完成下载（progress={last_progress}%）")
        print("         可调大 test.download_max_wait_minutes 后重试，或 download/stop 后检查环境")
        client.download_stop(device_id, channel_id, stream_id)
        return

    elapsed = time.time() - t0
    print(f"  [成功] 下载完成，总耗时 {elapsed/60:.1f} 分钟")
    print(f"    httpPath  = {file_path.get('httpPath')}")
    print(f"    httpsPath = {file_path.get('httpsPath')}")

    # ZLM downloadFile 是否需要 secret
    url = rewrite_zlm_host(file_path["httpPath"], cfg.get("zlm_base_url", ""))
    print(f"\n  实测 ZLM downloadFile（经 {urlsplit(url).netloc}）:")
    ok_no_secret, _ = try_download(url, "无 secret")
    if not ok_no_secret and cfg.get("zlm_secret"):
        sep = "&" if "?" in url else "?"
        ok_secret, _ = try_download(f"{url}{sep}secret={cfg['zlm_secret']}", "带 secret")
        needs_secret = ok_secret
    else:
        needs_secret = False

    print(f"\n  结论: ZLM downloadFile {'需要' if needs_secret else '不需要'} secret 参数")
    print("         （门户侧无论如何都会由后端代理下载文件，secret 不会下发给银行用户）")

    # 完整下载文件核对
    OUT_DIR.mkdir(exist_ok=True)
    final_url = url
    if needs_secret:
        sep = "&" if "?" in final_url else "?"
        final_url += f"{sep}secret={cfg['zlm_secret']}"
    out_file = OUT_DIR / f"verify_download_{int(time.time())}.mp4"
    t1 = time.time()
    try:
        with requests.get(final_url, stream=True, timeout=(10, 60)) as r:
            r.raise_for_status()
            size = 0
            with open(out_file, "wb") as f:
                for chunk in r.iter_content(1024 * 512):
                    f.write(chunk)
                    size += len(chunk)
        dt = time.time() - t1
        print(f"  [成功] 文件已保存: {out_file}  大小={size/1024/1024:.1f}MB  传输耗时={dt:.1f}s"
              f"（{(size/1024/1024)/dt:.2f} MB/s）")
    except Exception as e:
        print(f"  [失败] 下载文件: {e}")

    client.download_stop(device_id, channel_id, stream_id)
    print("\n结论建议: 门户下载任务 = download/start + 轮询 progress + 从 ZLM 拉取 MP4 落盘，")
    print(f"          本次 {speed} 倍速实测数据可作为线上限速/并发上限设定的依据。")


if __name__ == "__main__":
    main()
