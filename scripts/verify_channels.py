#!/usr/bin/env python3
"""验证2：设备与通道列表查询（门户通道同步依赖）。

验证内容：
1. 设备分页查询 /api/device/query/devices
2. 指定设备通道分页查询 /api/device/query/devices/{deviceId}/channels
3. 打印通道关键字段（国标编号、名称、在线状态），确认可作授权台账主键
"""
import json
from pathlib import Path

from wvp_client import WvpClient, load_config, section


def main():
    cfg = load_config()
    client = WvpClient(cfg)
    if not client.api_key:
        client.login()
    section("验证2：设备与通道列表查询")

    devices = client.devices()
    if devices.get("code") != 0:
        print(f"  [失败] 设备查询: {devices.get('msg')}")
        return
    device_list = devices["data"]["list"]
    print(f"  设备总数: {devices['data']['total']}")
    for d in device_list[:10]:
        print(f"    - {d['deviceId']}  name={d.get('name')}  在线={d.get('onLine')}  通道数={d.get('channelCount')}")

    # 逐设备枚举通道（保存结果供后续脚本使用）
    all_channels = []
    for d in device_list:
        page, total = 1, None
        while True:
            chans = client.channels(d["deviceId"], page=page, count=100)
            if chans.get("code") != 0:
                print(f"  [失败] 设备 {d['deviceId']} 通道查询: {chans.get('msg')}")
                break
            data = chans["data"]
            total = data["total"]
            all_channels.extend(data["list"])
            if page * 100 >= total:
                break
            page += 1
        print(f"  设备 {d['deviceId']} 通道数: {total}")

    print(f"\n  通道总数: {len(all_channels)}")
    for ch in all_channels[:20]:
        print(f"    - channelId={ch['deviceId']}  name={ch.get('name')}  status={ch.get('status')}")

    out = Path(__file__).parent / "_channels_snapshot.json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump(all_channels, f, ensure_ascii=False, indent=2)
    print(f"\n  通道快照已保存: {out}（供核对通道台账/配置 test.channel_id 用）")

    print("\n结论建议: 通道可用 (device_id, channel_id) 二元组作为门户授权与镜像表主键。")


if __name__ == "__main__":
    main()
