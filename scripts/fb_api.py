#!/usr/bin/env python3
"""
FB素材庫 — Facebook Graph API 模組
自動抓取粉專貼文成效數據。
"""

import difflib
import os
import sys
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

FB_PAGE_ID = os.getenv("FB_PAGE_ID", "")
FB_PAGE_ACCESS_TOKEN = os.getenv("FB_PAGE_ACCESS_TOKEN", "")
GRAPH_API_BASE = "https://graph.facebook.com/v21.0"

# 確保專案根目錄在 sys.path 中
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def is_configured() -> bool:
    """檢查 FB API 是否已設定。"""
    return bool(FB_PAGE_ID and FB_PAGE_ACCESS_TOKEN)


def get_page_posts(since_days: int = 30, limit: int = 50) -> list[dict]:
    """取得粉專近期貼文。"""
    if not is_configured():
        return []

    from datetime import datetime, timedelta
    since_ts = int((datetime.now() - timedelta(days=since_days)).timestamp())

    url = f"{GRAPH_API_BASE}/{FB_PAGE_ID}/published_posts"
    params = {
        "access_token": FB_PAGE_ACCESS_TOKEN,
        "fields": "id,message,created_time,shares",
        "since": since_ts,
        "limit": limit,
    }

    try:
        resp = requests.get(url, params=params, timeout=30)
        data = resp.json()
        if "error" in data:
            print(f"❌ FB API 錯誤：{data['error'].get('message', '')}")
            return []
        return data.get("data", [])
    except Exception as e:
        print(f"❌ FB API 請求失敗：{e}")
        return []


def get_post_insights(post_id: str) -> dict:
    """取得單篇貼文的成效數據。"""
    if not is_configured():
        return {}

    url = f"{GRAPH_API_BASE}/{post_id}"
    params = {
        "access_token": FB_PAGE_ACCESS_TOKEN,
        "fields": "likes.summary(true),comments.summary(true),shares",
    }

    try:
        resp = requests.get(url, params=params, timeout=30)
        data = resp.json()
        if "error" in data:
            print(f"❌ FB API 錯誤：{data['error'].get('message', '')}")
            return {}

        likes = data.get("likes", {}).get("summary", {}).get("total_count", 0)
        comments = data.get("comments", {}).get("summary", {}).get("total_count", 0)
        shares = data.get("shares", {}).get("count", 0) if data.get("shares") else 0

        # 嘗試取得觸及數
        reach = 0
        try:
            insights_url = f"{GRAPH_API_BASE}/{post_id}/insights"
            insights_params = {
                "access_token": FB_PAGE_ACCESS_TOKEN,
                "metric": "post_impressions_unique",
            }
            insights_resp = requests.get(insights_url, params=insights_params, timeout=30)
            insights_data = insights_resp.json()
            if "data" in insights_data and insights_data["data"]:
                reach = insights_data["data"][0].get("values", [{}])[0].get("value", 0)
        except Exception:
            pass

        return {
            "likes": likes,
            "comments": comments,
            "shares": shares,
            "reach": reach,
        }
    except Exception as e:
        print(f"❌ FB API 請求失敗：{e}")
        return {}


def match_post_to_record(fb_posts: list[dict], records: list[dict]) -> list[tuple]:
    """模糊比對 FB 貼文和紀錄，回傳 (record, fb_post, similarity) 的列表。"""
    matches = []

    for record in records:
        record_content = record.get("post_content", "")[:100]
        if not record_content:
            continue

        best_match = None
        best_ratio = 0

        for fb_post in fb_posts:
            fb_message = fb_post.get("message", "")[:100]
            if not fb_message:
                continue

            ratio = difflib.SequenceMatcher(None, record_content, fb_message).ratio()
            if ratio > best_ratio:
                best_ratio = ratio
                best_match = fb_post

        if best_match and best_ratio >= 0.6:
            matches.append((record, best_match, best_ratio))

    return matches


def update_all_metrics() -> int:
    """批次更新所有有 FB 貼文 ID 的紀錄。回傳更新筆數。"""
    from scripts.sheets_api import get_post_records, update_post_metrics

    records = get_post_records(limit=100)
    updated = 0

    for r in records:
        fb_post_id = r.get("fb_post_id", "")
        if not fb_post_id:
            continue

        insights = get_post_insights(fb_post_id)
        if insights:
            success = update_post_metrics(
                row=r["row_number"],
                fb_post_id=fb_post_id,
                likes=insights.get("likes", 0),
                comments=insights.get("comments", 0),
                shares=insights.get("shares", 0),
                reach=insights.get("reach", 0),
            )
            if success:
                updated += 1
                print(f"  ✅ 更新成功：{r.get('material_title', '?')} (👍{insights.get('likes', 0)})")

    return updated


def main():
    """CLI 入口。"""
    if not is_configured():
        print("⚠ 尚未設定 FB_PAGE_ID 和 FB_PAGE_ACCESS_TOKEN")
        print("  請在 .env 中設定這兩個變數")
        sys.exit(1)

    args = sys.argv[1:]

    if not args or args[0] == "--refresh":
        print("🔄 批次更新 FB 成效數據...")
        count = update_all_metrics()
        print(f"✅ 完成，更新了 {count} 筆紀錄")

    elif args[0] == "--match":
        print("🔍 自動比對 FB 貼文...")
        from scripts.sheets_api import get_post_records
        fb_posts = get_page_posts(since_days=30)
        records = get_post_records(limit=50)
        matches = match_post_to_record(fb_posts, records)
        for record, fb_post, ratio in matches:
            print(f"\n  📝 {record.get('material_title', '?')} (相似度: {ratio:.0%})")
            print(f"     FB: {fb_post.get('message', '')[:50]}...")
            print(f"     FB ID: {fb_post.get('id', '')}")

    elif args[0] == "--help":
        print("用法：")
        print("  python fb_api.py --refresh  # 批次更新所有 FB 成效")
        print("  python fb_api.py --match    # 自動比對 FB 貼文與紀錄")
    else:
        print(f"未知參數：{args[0]}，使用 --help 查看用法")


if __name__ == "__main__":
    main()
