#!/usr/bin/env python3
"""
FB素材庫 — 貼文生成腳本
從 Google Sheets 素材庫讀取素材，用 Gemini 生成 FB 貼文。
"""

import json
import os
import sys
from pathlib import Path

from google import genai
import requests
from dotenv import load_dotenv

# 載入環境變數
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
APPS_SCRIPT_API_URL = os.getenv("APPS_SCRIPT_API_URL")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

# 專案根目錄
PROJECT_ROOT = Path(__file__).resolve().parent.parent
COPYWRITING_PROMPT_PATH = PROJECT_ROOT / "prompts" / "copywriting.md"
BRAND_PATH = PROJECT_ROOT / "config" / "brand.json"


def load_copywriting_prompt() -> str:
    """載入貼文生成 prompt 模板。"""
    with open(COPYWRITING_PROMPT_PATH, "r", encoding="utf-8") as f:
        return f.read()


def load_brand() -> dict:
    """載入品牌設定。"""
    with open(BRAND_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def get_materials(topic: str | None = None, limit: int = 10) -> list[dict]:
    """從 Apps Script API 取得素材清單。"""
    params = {"action": "getMaterials", "limit": str(limit)}
    if topic:
        params["topic"] = topic

    try:
        resp = requests.get(APPS_SCRIPT_API_URL, params=params, timeout=30)
        data = resp.json()
        return data.get("materials", [])
    except Exception as e:
        print(f"❌ 取得素材失敗：{e}")
        return []


def get_stats() -> dict:
    """取得素材庫統計資料。"""
    try:
        resp = requests.get(
            APPS_SCRIPT_API_URL, params={"action": "getStats"}, timeout=30
        )
        return resp.json()
    except Exception as e:
        print(f"❌ 取得統計失敗：{e}")
        return {}


def mark_used(row_number: int) -> bool:
    """標記素材為已使用。"""
    try:
        resp = requests.post(
            APPS_SCRIPT_API_URL,
            json={"action": "markUsed", "row": row_number},
            timeout=30,
            headers={"Content-Type": "application/json"},
        )
        result = resp.json()
        return result.get("success", False)
    except Exception as e:
        print(f"❌ 標記失敗：{e}")
        return False


def display_materials(materials: list[dict]):
    """顯示素材清單供使用者選擇。"""
    if not materials:
        print("📭 目前沒有可用的素材")
        return

    print(f"\n📚 找到 {len(materials)} 筆素材：\n")
    for i, m in enumerate(materials, 1):
        used_mark = "✅" if m.get("used") else "🆕"
        score = m.get("relevance_score", 0)
        topics = ", ".join(m.get("topics", []))
        print(f"  {i}. {used_mark} [{score}分] {m.get('title', '無標題')}")
        print(f"     主題：{topics}")
        print(f"     摘要：{m.get('summary', '')[:60]}...")
        print(f"     來源：{m.get('source_title', '')} | 列號：{m.get('row_number', '?')}")
        print()


def generate_post(
    client: genai.Client,
    material: dict,
    prompt_template: str,
    post_type: str = "",
) -> str:
    """用 Gemini 生成 FB 貼文。"""
    prompt = prompt_template.replace("{{title}}", material.get("title", ""))
    prompt = prompt.replace("{{summary}}", material.get("summary", ""))
    prompt = prompt.replace("{{topics}}", ", ".join(material.get("topics", [])))
    prompt = prompt.replace("{{angles}}", " | ".join(material.get("angles", [])))
    prompt = prompt.replace("{{key_facts}}", " | ".join(material.get("key_facts", [])))
    prompt = prompt.replace("{{source_title}}", material.get("source_title", ""))
    prompt = prompt.replace("{{post_type}}", post_type)

    try:
        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=prompt,
        )
        return response.text
    except Exception as e:
        print(f"❌ Gemini API 錯誤：{e}")
        return ""


def interactive_mode(client: genai.Client, prompt_template: str):
    """互動模式：選擇素材並生成貼文。"""
    # 顯示統計
    stats = get_stats()
    if stats and not stats.get("error"):
        print(f"\n📊 素材庫統計：")
        print(f"   總數：{stats.get('total', 0)} 筆")
        print(f"   本週新增：{stats.get('thisWeek', 0)} 筆")
        print(f"   高相關性：{stats.get('highRelevance', 0)} 筆")
        by_topic = stats.get("byTopic", {})
        if by_topic:
            print(f"   各主題分佈：")
            for topic, count in sorted(by_topic.items(), key=lambda x: -x[1]):
                print(f"     • {topic}: {count} 筆")

    # 選擇主題
    print("\n📂 選擇主題篩選（直接 Enter 顯示全部）：")
    topics = ["升學資訊", "親子教養", "學習方法", "教育政策趨勢", "在地學區資訊"]
    for i, t in enumerate(topics, 1):
        print(f"  {i}. {t}")

    choice = input("\n選擇 (1-5 或 Enter): ").strip()
    topic = topics[int(choice) - 1] if choice.isdigit() and 1 <= int(choice) <= 5 else None

    # 取得素材
    materials = get_materials(topic=topic, limit=10)
    # 篩選未使用的
    unused = [m for m in materials if not m.get("used")]
    if unused:
        print(f"\n🆕 以下只顯示未使用的素材：")
        display_materials(unused)
        available = unused
    else:
        print(f"\n⚠ 沒有未使用的素材，顯示全部：")
        display_materials(materials)
        available = materials

    if not available:
        return

    # 選擇素材
    idx = input("選擇素材編號 (1-N): ").strip()
    if not idx.isdigit() or int(idx) < 1 or int(idx) > len(available):
        print("❌ 無效選擇")
        return
    selected = available[int(idx) - 1]

    # 選擇貼文類型
    print("\n📝 貼文類型：")
    print("  1. 一般 (200-400字)")
    print("  2. 短文 (150字以內)")
    print("  3. 長文 (深入分析)")
    print("  4. 互動 (投票/問答)")
    print("  5. 知識 (科普/教學)")

    type_choice = input("選擇 (1-5, 預設1): ").strip()
    post_types = {"1": "", "2": "短文", "3": "長文", "4": "互動", "5": "知識"}
    post_type = post_types.get(type_choice, "")

    # 生成貼文
    print("\n⏳ 正在生成貼文...")
    post = generate_post(client, selected, prompt_template, post_type)

    if post:
        print("\n" + "=" * 60)
        print("📱 生成的 FB 貼文：")
        print("=" * 60)
        print(post)
        print("=" * 60)

        # 詢問是否標記為已使用
        mark = input("\n是否標記此素材為已使用？(y/N): ").strip().lower()
        if mark == "y" and selected.get("row_number"):
            if mark_used(selected["row_number"]):
                print("✅ 已標記為已使用")
            else:
                print("⚠ 標記失敗")

        # 詢問是否儲存
        save = input("是否儲存貼文到檔案？(y/N): ").strip().lower()
        if save == "y":
            filename = f"post_{selected.get('title', 'untitled')[:20]}_{post_type or 'general'}.txt"
            filename = "".join(c if c.isalnum() or c in "._-" else "_" for c in filename)
            output_path = PROJECT_ROOT / "output" / filename
            output_path.parent.mkdir(exist_ok=True)
            with open(output_path, "w", encoding="utf-8") as f:
                f.write(post)
            print(f"💾 已儲存至：{output_path}")


def quick_generate(client: genai.Client, prompt_template: str, topic: str | None = None):
    """快速模式：自動選擇最佳素材並生成貼文。"""
    materials = get_materials(topic=topic, limit=5)
    unused = [m for m in materials if not m.get("used")]

    if not unused:
        print("📭 沒有未使用的素材可用")
        return

    # 選擇相關性最高的未使用素材
    best = max(unused, key=lambda m: m.get("relevance_score", 0))
    print(f"🎯 自動選擇素材：{best.get('title', '無標題')} (分數: {best.get('relevance_score', 0)})")

    print("\n⏳ 正在生成貼文...")
    post = generate_post(client, best, prompt_template)

    if post:
        print("\n" + "=" * 60)
        print("📱 生成的 FB 貼文：")
        print("=" * 60)
        print(post)
        print("=" * 60)


def main():
    """主程式進入點。"""
    if not GEMINI_API_KEY:
        print("❌ 錯誤：請設定 GEMINI_API_KEY 環境變數")
        sys.exit(1)

    if not APPS_SCRIPT_API_URL:
        print("❌ 錯誤：請設定 APPS_SCRIPT_API_URL 環境變數")
        sys.exit(1)

    client = genai.Client(api_key=GEMINI_API_KEY)
    prompt_template = load_copywriting_prompt()

    if len(sys.argv) > 1:
        if sys.argv[1] == "--quick":
            topic = sys.argv[2] if len(sys.argv) > 2 else None
            quick_generate(client, prompt_template, topic)
        elif sys.argv[1] == "--stats":
            stats = get_stats()
            print(json.dumps(stats, ensure_ascii=False, indent=2))
        elif sys.argv[1] == "--list":
            topic = sys.argv[2] if len(sys.argv) > 2 else None
            materials = get_materials(topic=topic)
            display_materials(materials)
        elif sys.argv[1] == "--help":
            print("用法：")
            print("  python generate_post.py              # 互動模式")
            print("  python generate_post.py --quick      # 快速生成（自動選素材）")
            print("  python generate_post.py --quick 親子教養  # 指定主題快速生成")
            print("  python generate_post.py --list       # 列出素材")
            print("  python generate_post.py --list 升學資訊  # 列出特定主題素材")
            print("  python generate_post.py --stats      # 顯示統計")
        else:
            print(f"未知參數：{sys.argv[1]}，使用 --help 查看用法")
    else:
        interactive_mode(client, prompt_template)


if __name__ == "__main__":
    main()
