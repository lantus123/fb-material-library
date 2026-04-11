"""FB素材庫 — 學習效果量化指標。

核心指標：每月「AI 初版 → 最終版」平均字數 diff %。
若學習迴路有效，這個數字應該隨月份下降。

用法：
    python3 scripts/metrics.py           # 印出每月彙總
    python3 scripts/metrics.py --raw     # 印出每筆貼文 diff
"""

import sys
from collections import defaultdict
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.sheets_api import get_post_records


def _char_diff_ratio(original: str, edited: str) -> float:
    """以 |len(edited) - len(original)| / max(len(original),1) 衡量修改幅度。"""
    if not original:
        return 0.0
    return abs(len(edited) - len(original)) / max(len(original), 1) * 100


def compute_monthly_diff() -> dict:
    records = get_post_records(limit=500)
    buckets: dict[str, list[float]] = defaultdict(list)
    for r in records:
        original = r.get("original_content", "")
        edited = r.get("post_content", "")
        if not original or original.strip() == edited.strip():
            continue
        month = str(r.get("generated_at", ""))[:7]  # YYYY-MM
        if not month:
            continue
        buckets[month].append(_char_diff_ratio(original, edited))
    return {
        month: {
            "count": len(values),
            "avg_diff_pct": round(sum(values) / len(values), 1) if values else 0.0,
        }
        for month, values in sorted(buckets.items())
    }


def main():
    raw = "--raw" in sys.argv
    if raw:
        records = get_post_records(limit=500)
        print(f"{'row':>4} {'diff %':>8}  material_title")
        for r in records:
            original = r.get("original_content", "")
            edited = r.get("post_content", "")
            if not original:
                continue
            pct = _char_diff_ratio(original, edited)
            print(f"{r['row_number']:>4} {pct:>7.1f}%  {r['material_title'][:40]}")
        return

    monthly = compute_monthly_diff()
    if not monthly:
        print("⚠️ 沒有足夠資料計算指標（需要至少一筆被修改過的貼文）")
        return
    print("📊 每月學習指標（AI 初版 → 最終版平均字數差異）")
    print(f"{'月份':<10} {'樣本數':>6} {'平均差異':>10}")
    for month, stats in monthly.items():
        print(f"{month:<10} {stats['count']:>6} {stats['avg_diff_pct']:>9.1f}%")
    print("\n💡 若學習迴路有效，平均差異 % 應該逐月下降。")


if __name__ == "__main__":
    main()
