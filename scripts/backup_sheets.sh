#!/bin/bash
# FB素材庫 — 每週備份所有工作表為 CSV
# 建議 cron 設定：0 3 * * 0 /home/r19911219/fb-material-library/scripts/backup_sheets.sh

set -e
PROJECT_DIR="/home/r19911219/fb-material-library"
cd "$PROJECT_DIR"

DATE_DIR=$(date +%Y-%m-%d)
BACKUP_DIR="$PROJECT_DIR/logs/backups/$DATE_DIR"
mkdir -p "$BACKUP_DIR"

python3 - <<PYEOF
import csv
import sys
from pathlib import Path
sys.path.insert(0, "$PROJECT_DIR")
from scripts.sheets_api import _get_spreadsheet

out_dir = Path("$BACKUP_DIR")
ss = _get_spreadsheet()
for ws in ss.worksheets():
    rows = ws.get_all_values()
    safe_name = ws.title.replace("/", "_")
    with open(out_dir / f"{safe_name}.csv", "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerows(rows)
    print(f"✅ {ws.title}: {len(rows)} 列")
PYEOF

# 僅保留最近 12 份備份
cd "$PROJECT_DIR/logs/backups"
ls -1 -t | tail -n +13 | xargs -r rm -rf

echo "📦 備份完成：$BACKUP_DIR"
