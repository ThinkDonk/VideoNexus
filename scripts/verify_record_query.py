#!/usr/bin/env python3
"""验证4：录像查询（回放与下载的前提）。

验证内容：
1. /api/gb_record/query/{deviceId}/{channelId}?startTime&endTime 查询设备侧录像段
2. 打印录像段列表（起止时间、时长），确认录像存储在设备/NVR 侧可查
3. 顺便验证统一通道视图接口 /api/common/channel/playback/query（可选）
"""
from datetime import datetime

from wvp_client import WvpClient, load_config, section, check, pick_test_channel


def fmt_ts(ts: str) -> str:
    return ts.replace("T", " ") if isinstance(ts, str) else str(ts)


def main():
    cfg = load_config()
    client = WvpClient(cfg)
    if not client.api_key:
        client.login()
    section("验证4：录像查询")

    device_id, channel_id = pick_test_channel(cfg, client)
    t = cfg["test"]
    print(f"  目标: device={device_id} channel={channel_id}")
    print(f"  时间段: {t['record_start']} ~ {t['record_end']}")

    body = client.record_query(device_id, channel_id, t["record_start"], t["record_end"])
    if body.get("code") != 0:
        print(f"  [失败] gb_record/query: code={body.get('code')} msg={body.get('msg')}")
        return
    data = body["data"]
    record_list = data.get("recordList") or []
    print(f"  [成功] 录像段总数: {data.get('sumNum')}（本次返回 {len(record_list)} 段）")

    total_secs = 0.0
    for item in record_list[:30]:
        try:
            s = datetime.fromisoformat(fmt_ts(item["startTime"]))
            e = datetime.fromisoformat(fmt_ts(item["endTime"]))
            dur = (e - s).total_seconds()
        except Exception:
            dur = None
        total_secs += dur or 0
        print(f"    - {fmt_ts(item['startTime'])} ~ {fmt_ts(item['endTime'])}"
              f"  时长={dur}s  type={item.get('type')}")

    print(f"  前 {min(len(record_list), 30)} 段合计约 {total_secs/60:.1f} 分钟录像")
    print("\n结论建议: 录像在设备侧可查即支持回放/下载；注意确认录像实际存储位置（NVR/平台）。")


if __name__ == "__main__":
    main()
