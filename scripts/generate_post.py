#!/usr/bin/env python3
"""
FB素材庫 — 貼文生成腳本（CLI 介面）
從 Google Sheets 素材庫讀取素材，用 Gemini 生成 FB 貼文。
"""

import json
import sys
from pathlib import Path

# 確保專案根目錄在 sys.path 中
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.sheets_api import get_materials, get_stats, mark_used, add_post_record
from scripts.post_generator import get_client, generate_post, load_brand


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


def interactive_mode():
    """互動模式：選擇素材並生成貼文。"""
    client = get_client()

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
    post_types = {"1": "一般", "2": "短文", "3": "長文", "4": "互動", "5": "知識"}
    post_type = post_types.get(type_choice, "一般")

    # 生成貼文
    print("\n⏳ 正在生成貼文...")
    post = generate_post(client, selected, post_type)

    if post:
        print("\n" + "=" * 60)
        print("📱 生成的 FB 貼文：")
        print("=" * 60)
        print(post)
        print("=" * 60)

        # 評分
        rating_input = input("\n給這篇貼文評分 (1-5, Enter 跳過): ").strip()
        rating = int(rating_input) if rating_input.isdigit() and 1 <= int(rating_input) <= 5 else 0
        notes = ""
        if rating:
            notes = input("備註（哪裡好/不好，Enter 跳過）: ").strip()

        # 儲存紀錄
        save = input("是否儲存到貼文紀錄？(Y/n): ").strip().lower()
        if save != "n":
            result = add_post_record(
                material_title=selected.get("title", ""),
                material_row=selected.get("row_number", 0),
                post_type=post_type,
                post_content=post,
                rating=rating,
                notes=notes,
            )
            if result.get("success"):
                print(f"✅ 已儲存到貼文紀錄 (第 {result.get('row')} 列)")
            else:
                print(f"⚠ 儲存失敗：{result.get('error')}")

            # 標記素材為已使用
            if selected.get("row_number"):
                mark_used(selected["row_number"])
                print("✅ 素材已標記為已使用")


def quick_generate(topic: str | None = None):
    """快速模式：自動選擇最佳素材並生成貼文。"""
    client = get_client()
    materials = get_materials(topic=topic, limit=5)
    unused = [m for m in materials if not m.get("used")]

    if not unused:
        print("📭 沒有未使用的素材可用")
        return

    best = max(unused, key=lambda m: m.get("relevance_score", 0))
    print(f"🎯 自動選擇素材：{best.get('title', '無標題')} (分數: {best.get('relevance_score', 0)})")

    print("\n⏳ 正在生成貼文...")
    post = generate_post(client, best)

    if post:
        print("\n" + "=" * 60)
        print("📱 生成的 FB 貼文：")
        print("=" * 60)
        print(post)
        print("=" * 60)


def main():
    """主程式進入點。"""
    if len(sys.argv) > 1:
        if sys.argv[1] == "--quick":
            topic = sys.argv[2] if len(sys.argv) > 2 else None
            quick_generate(topic)
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
        interactive_mode()


if __name__ == "__main__":
    main()
