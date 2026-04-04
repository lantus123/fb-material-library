"""
FB素材庫 — Google Sheets API 共用模組
透過 Apps Script Web App 操作 Google Sheets。
"""

import os
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

APPS_SCRIPT_API_URL = os.getenv("APPS_SCRIPT_API_URL")
REQUEST_TIMEOUT = 30


def _get(params: dict) -> dict:
    """發送 GET 請求到 Apps Script API。"""
    resp = requests.get(APPS_SCRIPT_API_URL, params=params, timeout=REQUEST_TIMEOUT)
    return resp.json()


def _post(data: dict) -> dict:
    """發送 POST 請求到 Apps Script API。"""
    resp = requests.post(
        APPS_SCRIPT_API_URL,
        json=data,
        timeout=REQUEST_TIMEOUT,
        headers={"Content-Type": "application/json"},
    )
    return resp.json()


# ─── 素材庫 ────────────────────────────────────────────────

def get_materials(topic: str | None = None, limit: int = 10) -> list[dict]:
    """取得素材清單。"""
    params = {"action": "getMaterials", "limit": str(limit)}
    if topic:
        params["topic"] = topic
    data = _get(params)
    return data.get("materials", [])


def get_stats() -> dict:
    """取得素材庫統計資料。"""
    return _get({"action": "getStats"})


def mark_used(row_number: int) -> bool:
    """標記素材為已使用。"""
    result = _post({"action": "markUsed", "row": row_number})
    return result.get("success", False)


# ─── 貼文紀錄 ──────────────────────────────────────────────

def add_post_record(
    material_title: str,
    material_row: int,
    post_type: str,
    post_content: str,
    rating: int = 0,
    notes: str = "",
) -> dict:
    """儲存生成的貼文紀錄。"""
    return _post({
        "action": "addPostRecord",
        "material_title": material_title,
        "material_row": material_row,
        "post_type": post_type,
        "post_content": post_content,
        "rating": rating,
        "notes": notes,
    })


def get_post_records(limit: int = 50) -> list[dict]:
    """取得貼文紀錄。"""
    data = _get({"action": "getPostRecords", "limit": str(limit)})
    return data.get("records", [])


def get_top_posts(limit: int = 3) -> list[dict]:
    """取得表現最好的貼文（用於 few-shot prompt）。"""
    data = _get({"action": "getTopPosts", "limit": str(limit)})
    return data.get("posts", [])


def update_post_metrics(
    row: int,
    fb_post_id: str = "",
    likes: int = 0,
    comments: int = 0,
    shares: int = 0,
    reach: int = 0,
) -> bool:
    """更新貼文的 FB 成效數據。"""
    result = _post({
        "action": "updatePostMetrics",
        "row": row,
        "fb_post_id": fb_post_id,
        "likes": likes,
        "comments": comments,
        "shares": shares,
        "reach": reach,
    })
    return result.get("success", False)


def update_post_rating(row: int, rating: int, notes: str = "") -> bool:
    """更新貼文的主觀評分和備註。"""
    result = _post({
        "action": "updatePostRating",
        "row": row,
        "rating": rating,
        "notes": notes,
    })
    return result.get("success", False)
