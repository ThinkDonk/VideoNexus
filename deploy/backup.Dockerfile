# =============================================================================
# VideoNexus 备份镜像：alpine + sqlite + bash + tzdata，busybox crond 前台运行
# -----------------------------------------------------------------------------
# crontab：每日 03:00 执行备份脚本（sqlite .backup + gzip + 保留 30 份）。
# 在 deploy/ 目录执行：docker compose build portal-backup
# =============================================================================
FROM alpine:3.20

# sqlite：在线一致性备份（.backup 命令）；bash：脚本解释器；tzdata：本地时区
RUN apk add --no-cache sqlite bash tzdata

ENV TZ=Asia/Shanghai

# 备份脚本打进镜像（compose 中另将 deploy/backup 挂载到 /scripts，宿主侧可改可查）
COPY deploy/backup/backup.sh /usr/local/bin/backup.sh
# 防御 Windows 检出带来的 CRLF；并赋予执行权限
RUN sed -i 's/\r$//' /usr/local/bin/backup.sh && chmod +x /usr/local/bin/backup.sh

# root 的 crontab（busybox crond 默认读取 /etc/crontabs/root）：
# 优先执行宿主挂载的 /scripts/backup.sh（改脚本无需重建镜像），
# 该挂载不存在时回退镜像内置副本；输出统一追加到 /backups/backup.log。
# 注意 crontab 行内 % 是特殊字符（换行），时间格式化一律放在脚本内部完成。
RUN echo '0 3 * * * if [ -f /scripts/backup.sh ]; then /scripts/backup.sh; else /usr/local/bin/backup.sh; fi >> /backups/backup.log 2>&1' \
    > /etc/crontabs/root

# 前台运行 crond（-f 前台，-l 8 日志级别：后台静默、出错时 docker logs 可见）
ENTRYPOINT ["crond", "-f", "-l", "8"]
