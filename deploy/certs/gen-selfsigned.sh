#!/usr/bin/env bash
# =============================================================================
# 自签 TLS 证书生成（仅内网测试/联调用）
# -----------------------------------------------------------------------------
# 用法：在装有 openssl 的机器上执行  bash gen-selfsigned.sh [有效天数]
#   bash gen-selfsigned.sh        # 默认 825 天（约 2.26 年，<=10 年）
# 产出（与 compose 挂载路径约定一致）：
#   deploy/certs/fullchain.pem    证书（含 SAN）
#   deploy/certs/privkey.pem      私钥
# 正式环境请改用 CA 签发证书，替换上述两个同名文件后
# `docker compose restart portal-web` 即可。
# 注意：浏览器访问 https://<主机IP> 仍会提示“证书不受信任”（IP 未列入 SAN 属正常），
# 内网测试点击继续访问或手动信任即可。
# =============================================================================
set -euo pipefail

DAYS="${1:-825}"
CERT_DIR="$(cd "$(dirname "$0")" && pwd)"

command -v openssl >/dev/null 2>&1 || { echo "错误：未找到 openssl，请先安装"; exit 1; }

openssl req -x509 -nodes -newkey rsa:2048 -sha256 -days "$DAYS" \
    -keyout "${CERT_DIR}/privkey.pem" \
    -out "${CERT_DIR}/fullchain.pem" \
    -subj "/CN=portal.local/O=VideoNexus" \
    -addext "subjectAltName=DNS:portal.local,DNS:localhost,IP:127.0.0.1"

chmod 600 "${CERT_DIR}/privkey.pem"
chmod 644 "${CERT_DIR}/fullchain.pem"

echo "已生成 ${CERT_DIR}/fullchain.pem 与 ${CERT_DIR}/privkey.pem（CN=portal.local，有效期 ${DAYS} 天）"
echo "如需匹配真实域名/IP，可编辑本脚本中 -subj 与 subjectAltName 后重新生成。"
