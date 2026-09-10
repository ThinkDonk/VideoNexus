#!/usr/bin/env python3
"""验证3：实时点播与流地址探测。

验证内容：
1. /api/play/start/{deviceId}/{channelId} 取全协议流地址
2. http-flv 地址连通性探测（读首段字节确认流可拉）
3. 打印 ws-flv 地址供浏览器播放验证（H.265 解码性能请在 WVP 自带前端验证 Jessibuca/h265web 页签）
4. /api/play/stop 停止点播
"""
import time

import requests

from wvp_client import WvpClient, load_config, section, check, pick_test_channel


def main():
    cfg = load_config()
    client = WvpClient(cfg)
    if not client.api_key:
        client.login()
    section("验证3：实时点播")

    device_id, channel_id = pick_test_channel(cfg, client)
    print(f"  目标: device={device_id} channel={channel_id}")

    t0 = time.time()
    body = client.play_start(device_id, channel_id)
    if body.get("code") != 0:
        print(f"  [失败] play/start: code={body.get('code')} msg={body.get('msg')}")
        return
    stream = body["data"]
    print(f"  [成功] play/start 耗时 {time.time()-t0:.1f}s  app={stream.get('app')} stream={stream.get('stream')}")

    print("  返回的流地址:")
    for key in ("ws_flv", "wss_flv", "flv", "https_flv", "hls", "https_hls", "ws_hls",
                "fmp4", "rtc", "rtcs", "rtsp", "rtmp"):
        if stream.get(key):
            print(f"    {key:10s} = {stream[key]}")

    # http-flv 探测：读前 64KB 判断流是否真的有数据
    flv_url = stream.get("https_flv") or stream.get("flv")
    if flv_url:
        try:
            t0 = time.time()
            with requests.get(flv_url, stream=True, timeout=(5, 15)) as r:
                print(f"  [探测] http-flv HTTP 状态: {r.status_code} content-type={r.headers.get('Content-Type')}")
                first = next(r.iter_content(64 * 1024), b"")
                print(f"  [探测] 首块 {len(first)} 字节，用时 {time.time()-t0:.2f}s -> "
                      f"{'有流 ✓' if len(first) > 0 else '空流 ✗（设备可能不在线）'}")
        except Exception as e:
            print(f"  [探测] http-flv 失败: {e}")
    else:
        print("  [探测] 无 http-flv 地址可探测")

    # 停止点播
    check(client.play_stop(device_id, channel_id), "play/stop（释放设备会话）")

    print("\n结论建议: 门户签发播放地址应改写为 wss://门户域名/stream/{app}/{stream}.live.flv 形式，")
    print("          H.265 解码性能请在 WVP 自带前端（Jessibuca / h265web 页签）用同一路通道实测。")


if __name__ == "__main__":
    main()
