#!/bin/bash
# FB素材庫 — 啟動 Streamlit Web UI
# 用法：bash scripts/start_web.sh

PROJECT_DIR="/home/r19911219/fb-material-library"
LOG_FILE="${PROJECT_DIR}/logs/streamlit.log"

# 停止舊的 Streamlit 程序
pkill -f "streamlit run app.py" 2>/dev/null
sleep 1

cd "${PROJECT_DIR}"
mkdir -p logs

# 背景啟動
nohup streamlit run app.py \
    --server.headless true \
    --server.port 8501 \
    --server.address 0.0.0.0 \
    > "${LOG_FILE}" 2>&1 &

echo "✅ Streamlit 已啟動 (PID: $!)"
echo "🌐 網址：http://35.201.163.220:8501"
echo "📄 Log：${LOG_FILE}"
