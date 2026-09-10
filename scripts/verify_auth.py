#!/usr/bin/env python3
"""验证1：WVP 认证方式。

验证内容：
1. api-key 模式（若配置了 wvp_api_key）：用 api-key 头调一个业务接口是否 200
2. 账号登录模式：MD5 密码登录 -> 取 access-token -> 调业务接口
结论会打印出来，用于确定门户集成采用哪种认证。
"""
from wvp_client import WvpClient, load_config, section


def main():
    cfg = load_config()
    section("验证1：WVP 认证方式")

    # 方式 A：api-key（推荐，长效免续期）
    api_key = (cfg.get("wvp_api_key") or "").strip()
    if api_key:
        client = WvpClient({**cfg, "wvp_api_key": api_key})
        try:
            body = client.devices()
            ok = body.get("code") == 0
            total = body.get("data", {}).get("total", "?") if ok else body
            print(f"  [A] api-key 认证: {'可用 ✓' if ok else '不可用 ✗'}"
                  f"（设备总数={total if ok else body.get('msg')}）")
        except Exception as e:
            print(f"  [A] api-key 认证: 不可用 ✗ —— {e}")
            print("      提示: 在 WVP 管理端创建 API Key（用户/API Key 管理），或确认 WVP 版本 >= 2.7.x")
    else:
        print("  [A] api-key: 未配置（wvp_api_key 为空），跳过")

    # 方式 B：账号登录
    client = WvpClient({**cfg, "wvp_api_key": ""})
    try:
        client.login()
        print(f"  [B] 账号登录: 成功 ✓（username={client.username}，token 已获取）")
        body = client.devices()
        ok = body.get("code") == 0
        print(f"  [B] access-token 调用业务接口: {'可用 ✓' if ok else '失败 ✗: ' + str(body.get('msg'))}")
    except Exception as e:
        print(f"  [B] 账号登录: 失败 ✗ —— {e}")

    print("\n结论建议: 若 A 可用，门户固定使用 api-key；否则使用 B 并依赖 401 自动重登。")


if __name__ == "__main__":
    main()
