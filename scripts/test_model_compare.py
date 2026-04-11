"""一次性腳本：比較 gemini-2.5-flash vs gemini-2.5-pro 的貼文生成品質。"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from google import genai

from scripts.post_generator import build_prompt, GEMINI_API_KEY
from scripts.sheets_api import get_materials

TEST_MATERIAL_ROWS = [6, 7]
MODELS = ["gemini-2.5-pro"]


def main():
    mats = {m["row_number"]: m for m in get_materials(limit=30)}
    selected = [mats[r] for r in TEST_MATERIAL_ROWS if r in mats]
    client = genai.Client(api_key=GEMINI_API_KEY)

    out_path = PROJECT_ROOT / "logs" / "model_compare.md"
    out_path.parent.mkdir(exist_ok=True)
    lines = ["# 模型對照測試\n"]

    for m in selected:
        title = m.get("title", "")
        topics = ", ".join(m.get("topics", []))
        lines.append(f"\n---\n\n## 素材：{title}\n\n**主題**：{topics}\n")
        prompt = build_prompt(m, post_type="")
        for model in MODELS:
            print(f"[{model}] {title[:30]} ...", flush=True)
            try:
                resp = client.models.generate_content(model=model, contents=prompt)
                text = resp.text or "(空)"
            except Exception as e:
                text = f"錯誤：{e}"
            lines.append(f"\n### {model}\n\n```\n{text}\n```\n")

    out_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"\n輸出：{out_path}")


if __name__ == "__main__":
    main()
