#!/usr/bin/env bash
# =============================================================================
# VideoNexus 数据库备份脚本（每日 03:00 由 portal-backup 容器内 crond 调用）
# -----------------------------------------------------------------------------
#   1. sqlite3 .backup 生成一致性快照（在线备份，业务不中断，自动处理 WAL）
#   2. gzip 压缩为 /backups/portal_YYYYmmdd_HHMMSS.db.gz
#   3. 轮转：仅保留最近 30 份，超出自动删除
#   4. 输出 /data/downloads 占用统计（下载的 mp4 不备份 —— 可由 ZLM 重新下载生成，
#      且按 FILE_RETENTION_DAYS 过期自动清理；只备份数据库）
#
# 手动立即执行一次：
#   docker exec portal-backup bash /usr/local/bin/backup.sh
# 恢复方法见 deploy/README.md「备份与恢复」。
# =============================================================================
set -euo pipefail

BACKUP_DIR="/backups"
DB_FILE="/data/portal.db"
KEEP=30
STAMP="$(date +%Y%m%d_%H%M%S)"
TARGET="${BACKUP_DIR}/portal_${STAMP}.db"

log() { echo "[backup $(date '+%Y-%m-%d %H:%M:%S')] $*"; }

# 数据库尚未初始化（首次启动前）时跳过本次备份
if [ ! -f "$DB_FILE" ]; then
    log "SKIP: ${DB_FILE} not found"
    exit 0
fi

# 在线一致性备份：.backup 由 sqlite 自身完成快照拷贝，无需停库/停后端
sqlite3 "$DB_FILE" ".backup '${TARGET}'"
gzip -f "${TARGET}"

log "OK: portal_${STAMP}.db.gz ($(du -h "${TARGET}.gz" | cut -f1))"

# 轮转：按修改时间倒序，超出 KEEP 的最旧文件删除
OLD="$(ls -1t "${BACKUP_DIR}"/portal_*.db.gz 2>/dev/null | tail -n +$((KEEP + 1)) || true)"
if [ -n "${OLD}" ]; then
    echo "${OLD}" | while read -r f; do
        rm -f -- "$f"
        log "ROTATE: removed $(basename -- "$f")"
    done
fi

# 下载文件仅统计不备份
if [ -d /data/downloads ]; then
    log "downloads: $(du -sh /data/downloads 2>/dev/null | cut -f1 || echo '?') total, $(find /data/downloads -type f 2>/dev/null | wc -l) files (not backed up)"
fi

log "done"
