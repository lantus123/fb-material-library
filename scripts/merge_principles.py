"""FB素材庫 — 月度原則合併腳本

呼叫 Gemini 分析啟用中的原則，合併相似/重複者。
合併前會先匯出快照到 logs/principles_snapshots/ 供回滾。

建議 cron：0 4 1 * *  # 每月 1 號凌晨 4 點
"""

import json
import sys
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.sheets_api import (
    get_all_principles,
    add_principle,
    set_principle_status,
    _get_secret,
)


MERGE_PROMPT_TEMPLATE = """你是一位文案編輯，任務是把一份累積的「修改原則庫」去重與合併。

## 目前的原則清單（啟用中）

{principles}

## 你的任務

找出相似或意思重疊的原則，把它們合併成更精煉的一條。回傳 JSON 格式如下：

```json
{{
  "merges": [
    {{
      "merged_from": [列號1, 列號2],
      "type": "正向" 或 "負向",
      "principle": "合併後的原則（一句話，具體可執行）",
      "reason": "合併後的理由（一句話）",
      "topic": "共同主題或留空"
    }}
  ]
}}
```

規則：
- 只合併真的在講同一件事的原則。若意思不同就不要硬湊
- 合併後原則必須比任何一條原版更具體、更準確
- 若沒有任何可合併的，回傳 `{{"merges": []}}`
- 直接輸出 JSON，不要加 markdown code fence 或任何引言
"""


def main():
    all_principles = get_all_principles()
    active = [p for p in all_principles if p["status"] == "active"]

    if len(active) < 3:
        print(f"啟用中原則僅 {len(active)} 條，無合併必要。")
        return

    # 1. 快照
    snap_dir = PROJECT_ROOT / "logs" / "principles_snapshots"
    snap_dir.mkdir(parents=True, exist_ok=True)
    snap_path = snap_dir / f"{datetime.now().strftime('%Y-%m-%d')}.json"
    snap_path.write_text(
        json.dumps(all_principles, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"📸 已快照到 {snap_path}")

    # 2. 呼叫 Gemini
    principles_text = "\n".join(
        f"- 列號 {p['row_number']}：【{p['type']}】{p['principle']}"
        + (f" — {p['reason']}" if p['reason'] else "")
        + (f"（主題：{p['topic']}）" if p['topic'] else "")
        for p in active
    )
    prompt = MERGE_PROMPT_TEMPLATE.format(principles=principles_text)

    from google import genai
    client = genai.Client(api_key=_get_secret("GEMINI_API_KEY"))
    model = _get_secret("GEMINI_MODEL", "gemini-2.5-pro")
    resp = client.models.generate_content(model=model, contents=prompt)
    raw = (resp.text or "").strip()

    # 3. 解析 JSON（移除可能的 code fence）
    clean = raw
    if clean.startswith("```"):
        clean = clean.split("```", 2)[1]
        if clean.lstrip().startswith("json"):
            clean = clean.lstrip()[4:]
    try:
        data = json.loads(clean.strip())
    except Exception as e:
        print(f"❌ 無法解析 Gemini 輸出為 JSON：{e}")
        print(f"原始輸出：{raw[:500]}")
        return

    merges = data.get("merges", [])
    if not merges:
        print("✅ Gemini 判斷無合併必要。")
        return

    # 4. 套用合併
    for m in merges:
        merged_from = m.get("merged_from", [])
        if len(merged_from) < 2:
            continue
        print(f"🔀 合併 {merged_from} → {m['principle'][:40]}")

        # 寫入新的合併原則
        add_principle(
            principle_type=m.get("type", "正向"),
            principle=m.get("principle", ""),
            reason=m.get("reason", ""),
            source_post_row=f"merged:{','.join(str(x) for x in merged_from)}",
            topic=m.get("topic", ""),
            notes=f"{datetime.now().strftime('%Y-%m-%d')} 自動合併",
        )

        # 原始條目標為 archived
        for row in merged_from:
            try:
                set_principle_status(int(row), "archived")
            except Exception:
                pass

    print(f"✅ 完成 {len(merges)} 組合併")


if __name__ == "__main__":
    main()
