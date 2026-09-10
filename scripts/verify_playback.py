#!/usr/bin/env python3
"""验证5：录像回放与回放控制。

验证内容：
1. /api/playback/start/{deviceId}/{channelId}?startTime&endTime 开始回放
2. 回放流地址探测（http-flv 读首块）
3. 控制接口: pause / resume / seek / speed
4. /api/playback/stop 停止回放
"""
import time

import requests

from wvp_client import WvpClient, load_config, section, check, pick_test_channel


def main():
    cfg = load_config()
    client = WvpClient(cfg)
    if not client.api_key:
        client.login()
    section("验证5：录像回放")

    device_id, channel_id = pick_test_channel(cfg, client)
    t = cfg["test"]
    print(f"  目标: device={device_id} channel={channel_id}")
    print(f"  回放时间段: {t['record_start']} ~ {t['record_end']}")

    t0 = time.time()
    body = client.playback_start(device_id, channel_id, t["record_start"], t["record_end"])
    if body.get("code") != 0:
        print(f"  [失败] playback/start: code={body.get('code')} msg={body.get('msg')}")
        return
    stream = body["data"]
    stream_id = stream.get("stream")
    print(f"  [成功] playback/start 耗时 {time.time()-t0:.1f}s")
    print(f"    app={stream.get('app')} stream={stream_id}")
    print(f"    ws_flv={stream.get('ws_flv')}")

    flv_url = stream.get("https_flv") or stream.get("flv")
    if flv_url:
        try:
            with requests.get(flv_url, stream=True, timeout=(5, 15)) as r:
                first = next(r.iter_content(64 * 1024), b"")
                print(f"  [探测] 回放 http-flv 首块 {len(first)} 字节 -> {'有流 ✓' if first else '空流 ✗'}")
        except Exception as e:
            print(f"  [探测] 回放 http-flv 失败: {e}")

    if not stream_id:
        print("  [失败] 未返回 stream 标识，无法继续验证控制接口")
        return

    # 控制接口（失败不阻断，逐个记录结果）
    time.sleep(2)
    check(client.playback_control("pause", stream_id), "pause 暂停")
    time.sleep(2)
    check(client.playback_control("resume", stream_id), "resume 恢复")
    check(client.playback_control("seek", stream_id, "60"), "seek 跳到第 60 秒")
    check(client.playback_control("speed", stream_id, "4"), "speed 4 倍速")
    time.sleep(3)
    check(client.playback_control("speed", stream_id, "1"), "speed 恢复 1 倍速")

    check(client.playback_stop(device_id, channel_id, stream_id), "playback/stop")

    print("\n结论建议: 回放控制接口可透传给门户前端（seek 用秒偏移，speed 支持 0.25/0.5/1/2/4/8）。")


if __name__ == "__main__":
    main()
