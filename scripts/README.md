# 第 0 期：WVP API 验证脚本

在门户开发前，先用这组脚本对**现有 WVP 环境**逐项验证技术可行性，并把结论记录到 `docs/phase0-验证结果.md`（留给后续联调参考）。

## 准备

```bash
cd scripts
pip install -r requirements.txt
cp wvp_config.example.json wvp_config.json   # 填写真实环境信息
```

配置说明：

| 字段 | 说明 |
|---|---|
| `wvp_base_url` | WVP 地址（如 `http://192.168.1.100:18080`） |
| `wvp_api_key` | WVP 管理端创建的 API Key（推荐，留空则走账号登录） |
| `wvp_username` / `wvp_password` | WVP 管理员账号（明文，仅本机验证用） |
| `zlm_base_url` | ZLM 地址，用于下载直链 host 改写与 secret 测试 |
| `zlm_secret` | ZLM 的 api secret |
| `test.device_id` / `test.channel_id` | 指定测试通道（留空自动取第一个设备首个通道） |
| `test.record_start` / `test.record_end` | 录像查询/回放/下载的时间段（选有录像的时段） |
| `test.download_speed` | GB28181 下载倍速（1/2/4/8，按设备能力） |

## 执行顺序

```bash
python verify_auth.py         # 1 认证方式（api-key / 账号登录）
python verify_channels.py     # 2 设备与通道列表（生成 _channels_snapshot.json）
python verify_play.py         # 3 实时点播 + 流地址探测
python verify_record_query.py # 4 录像段查询
python verify_playback.py     # 5 回放 + pause/resume/seek/speed 控制
python verify_download.py     # 6 下载全链路（耗时长，见脚本内预估）
```

## 需要人工确认的事项

1. **H.265 播放性能**：在 WVP 自带前端用同一路通道实测 Jessibuca（ws-flv）与 h265web 两个页签的解码流畅度。仓库 GB28181 摄像头大概率 H.265，若 Jessibuca 软解卡顿，门户播放器需引入 h265web 或考虑 ZLM 转码。
2. **录像存储位置**：确认录像在设备/NVR 侧还是平台侧（影响下载耗时预估与限制策略）。
3. **ZLM downloadFile 是否需要 secret**：脚本 6 会自动实测并打印结论。
4. **与合规方确认审计字段清单和导出格式**（CSV 字段名、时间范围口径）。
5. **WVP 生产版本**：确认是否 >= 2.7.x（决定 api-key 可用性；脚本 1 自动给出结论）。

## 结论记录模板（docs/phase0-验证结果.md）

每跑完一个脚本，把关键输出（成功/失败、耗时、倍速实测数据）记录下来，作为门户参数设定依据。
