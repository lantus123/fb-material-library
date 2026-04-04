#!/bin/bash
# FB素材庫 — 排程爬取包裝腳本
# 用於 crontab 自動執行，包含環境設定、鎖定機制、log 管理

set -euo pipefail

PROJECT_DIR="/home/r19911219/fb-material-library"
LOG_DIR="${PROJECT_DIR}/logs"
LOCK_FILE="/tmp/fb-material-crawl.lock"
LOG_FILE="${LOG_DIR}/crawl_$(date +%Y%m%d_%H%M%S).log"

# 確保 log 目錄存在
mkdir -p "${LOG_DIR}"

# flock 防止重疊執行
exec 200>"${LOCK_FILE}"
if ! flock -n 200; then
    echo "$(date): 另一個爬取程序正在執行，跳過本次排程" >> "${LOG_DIR}/skipped.log"
    exit 0
fi

# 切換到專案目錄
cd "${PROJECT_DIR}"

# 載入環境變數
if [ -f .env ]; then
    set -a
    source .env
    set +a
fi

# 啟動虛擬環境（如有）
if [ -d ".venv" ]; then
    source .venv/bin/activate
elif [ -d "venv" ]; then
    source venv/bin/activate
fi

# 執行爬取（--scheduled 模式會寄送 email 報告）
python scripts/crawl.py --scheduled >> "${LOG_FILE}" 2>&1

# 清理 30 天以上的舊 log
find "${LOG_DIR}" -name "*.log" -mtime +30 -delete 2>/dev/null || true

echo "$(date): 爬取完成，log: ${LOG_FILE}" >> "${LOG_DIR}/history.log"
