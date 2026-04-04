"""
FB素材庫 — Google Sheets API 共用模組
透過 gspread + 服務帳號直接讀寫 Google Sheets。
"""

import json
import os
from datetime import datetime, timedelta
from pathlib import Path

import gspread
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

SPREADSHEET_ID = "1n3h0V2-w0edLkW3J5EJAmkfEazjHaXof7qLunJAHVHc"
PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _get_secret(key: str, default: str = "") -> str:
    """從 Streamlit secrets 或環境變數取得設定值。"""
    try:
        import streamlit as st
        return st.secrets.get(key, os.getenv(key, default))
    except Exception:
        return os.getenv(key, default)


def _get_client() -> gspread.Client:
    """取得 gspread client，支援本地 credentials.json 或 Streamlit secrets。"""
    creds_path = PROJECT_ROOT / "credentials.json"

    if creds_path.exists():
        return gspread.service_account(filename=str(creds_path))

    # Streamlit Cloud: 從 secrets 讀取
    try:
        import streamlit as st
        creds_dict = dict(st.secrets["gcp_service_account"])
        return gspread.service_account_from_dict(creds_dict)
    except Exception:
        pass

    raise RuntimeError("找不到 Google 憑證（credentials.json 或 Streamlit secrets）")


def _get_spreadsheet() -> gspread.Spreadsheet:
    """取得 Spreadsheet 物件。"""
    client = _get_client()
    return client.open_by_key(SPREADSHEET_ID)


def _get_or_create_sheet(name: str, headers: list[str]) -> gspread.Worksheet:
    """取得或建立工作表，確保有表頭。"""
    ss = _get_spreadsheet()
    try:
        ws = ss.worksheet(name)
    except gspread.WorksheetNotFound:
        ws = ss.add_worksheet(title=name, rows=100, cols=len(headers))
    # 確保表頭存在
    first_row = ws.row_values(1)
    if not first_row or first_row[0] != headers[0]:
        ws.update("A1", [headers])
    return ws


# ─── 工作表定義 ────────────────────────────────────────────

MATERIAL_HEADERS = [
    '收錄時間', '標題', '摘要', '主題標籤', '可用角度', '關鍵事實',
    '相關性分數', '相關性原因', '來源URL', '來源標題', '原文摘錄', '已使用'
]

POST_HEADERS = [
    '生成時間', '素材標題', '素材列號', '貼文類型', '貼文內容',
    '主觀評分', '備註', 'FB貼文ID', '按讚數', '留言數',
    '分享數', '觸及人數', '最後更新'
]

STYLE_HEADERS = [
    '收錄時間', '標題', '原文內容', '寫法亮點', '來源URL', '標籤'
]


# ─── 素材庫 ────────────────────────────────────────────────

def get_materials(topic: str | None = None, limit: int = 10) -> list[dict]:
    """取得素材清單。"""
    ws = _get_or_create_sheet("素材庫", MATERIAL_HEADERS)
    rows = ws.get_all_values()
    if len(rows) <= 1:
        return []

    materials = []
    for idx, row in enumerate(rows[1:], start=2):
        if len(row) < 12:
            row.extend([""] * (12 - len(row)))
        materials.append({
            "row_number": idx,
            "curated_at": row[0],
            "title": row[1],
            "summary": row[2],
            "topics": [t.strip() for t in row[3].split(",") if t.strip()] if row[3] else [],
            "angles": [a.strip() for a in row[4].split("|") if a.strip()] if row[4] else [],
            "key_facts": [f.strip() for f in row[5].split("|") if f.strip()] if row[5] else [],
            "relevance_score": int(row[6]) if row[6] and str(row[6]).isdigit() else 0,
            "relevance_reason": row[7],
            "source_url": row[8],
            "source_title": row[9],
            "used": row[11] == "Y",
        })

    if topic:
        materials = [m for m in materials if any(topic in t for t in m["topics"])]

    # 排序：未使用優先，分數高優先
    materials.sort(key=lambda m: (m["used"], -m["relevance_score"]))
    return materials[:limit]


def get_stats() -> dict:
    """取得素材庫統計資料。"""
    ws = _get_or_create_sheet("素材庫", MATERIAL_HEADERS)
    rows = ws.get_all_values()
    if len(rows) <= 1:
        return {"total": 0, "thisWeek": 0, "highRelevance": 0, "byTopic": {}, "lastUpdated": "N/A"}

    data = rows[1:]
    week_ago = datetime.now() - timedelta(days=7)
    this_week = 0
    high_relevance = 0
    by_topic = {}
    last_date = ""

    for row in data:
        if len(row) < 12:
            row.extend([""] * (12 - len(row)))
        try:
            date = datetime.fromisoformat(row[0].replace("Z", "+00:00").split(".")[0])
            if date.replace(tzinfo=None) >= week_ago:
                this_week += 1
        except (ValueError, IndexError):
            pass
        score = int(row[6]) if row[6] and str(row[6]).isdigit() else 0
        if score >= 8:
            high_relevance += 1
        topics = [t.strip() for t in row[3].split(",") if t.strip()] if row[3] else []
        for t in topics:
            by_topic[t] = by_topic.get(t, 0) + 1
        if row[0]:
            last_date = row[0]

    return {
        "total": len(data),
        "thisWeek": this_week,
        "highRelevance": high_relevance,
        "byTopic": by_topic,
        "lastUpdated": last_date,
    }


def add_material(data: dict) -> dict:
    """新增素材到素材庫。"""
    ws = _get_or_create_sheet("素材庫", MATERIAL_HEADERS)

    # 重複偵測
    source_url = (data.get("source_url") or "").rstrip("/")
    if source_url:
        existing_urls = ws.col_values(9)  # 來源URL 欄
        normalized = [u.rstrip("/") for u in existing_urls[1:]]
        if source_url in normalized:
            return {"success": False, "error": "duplicate", "message": "此 URL 已存在素材庫中"}

    row = [
        data.get("curated_at") or datetime.now().isoformat(),
        data.get("title", ""),
        data.get("summary", ""),
        ", ".join(data.get("topics", [])),
        " | ".join(data.get("angles", [])),
        " | ".join(data.get("key_facts", [])),
        data.get("relevance_score", 0),
        data.get("relevance_reason", ""),
        data.get("source_url", ""),
        data.get("source_title", ""),
        (data.get("raw_text") or "")[:500],
        "N",
    ]
    ws.append_row(row, value_input_option="USER_ENTERED")
    last_row = len(ws.get_all_values())
    return {"success": True, "row": last_row, "total": last_row - 1}


def get_existing_urls() -> tuple[set[str], list[str]]:
    """取得已存的 URL 和標題（重複偵測用）。"""
    ws = _get_or_create_sheet("素材庫", MATERIAL_HEADERS)
    rows = ws.get_all_values()
    if len(rows) <= 1:
        return set(), []
    urls = set()
    titles = []
    for row in rows[1:]:
        if len(row) > 8 and row[8]:
            urls.add(row[8].rstrip("/"))
        if len(row) > 1 and row[1]:
            titles.append(row[1])
    return urls, titles


def mark_used(row_number: int) -> bool:
    """標記素材為已使用。"""
    ws = _get_or_create_sheet("素材庫", MATERIAL_HEADERS)
    ws.update_cell(row_number, 12, "Y")
    return True


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
    ws = _get_or_create_sheet("貼文紀錄", POST_HEADERS)
    row = [
        datetime.now().isoformat(),
        material_title,
        material_row,
        post_type,
        post_content,
        rating,
        notes,
        "",  # FB貼文ID
        0,   # 按讚數
        0,   # 留言數
        0,   # 分享數
        0,   # 觸及人數
        "",  # 最後更新
    ]
    ws.append_row(row, value_input_option="USER_ENTERED")
    last_row = len(ws.get_all_values())
    return {"success": True, "row": last_row, "total": last_row - 1}


def get_post_records(limit: int = 50) -> list[dict]:
    """取得貼文紀錄。"""
    ws = _get_or_create_sheet("貼文紀錄", POST_HEADERS)
    rows = ws.get_all_values()
    if len(rows) <= 1:
        return []

    records = []
    for idx, row in enumerate(rows[1:], start=2):
        if len(row) < 13:
            row.extend([""] * (13 - len(row)))
        records.append({
            "row_number": idx,
            "generated_at": row[0],
            "material_title": row[1],
            "material_row": row[2],
            "post_type": row[3],
            "post_content": row[4],
            "rating": int(row[5]) if row[5] and str(row[5]).isdigit() else 0,
            "notes": row[6],
            "fb_post_id": row[7],
            "likes": int(row[8]) if row[8] and str(row[8]).isdigit() else 0,
            "comments": int(row[9]) if row[9] and str(row[9]).isdigit() else 0,
            "shares": int(row[10]) if row[10] and str(row[10]).isdigit() else 0,
            "reach": int(row[11]) if row[11] and str(row[11]).isdigit() else 0,
            "last_updated": row[12],
        })

    records.reverse()
    return records[:limit]


def get_top_posts(limit: int = 3) -> list[dict]:
    """取得表現最好的貼文（用於 few-shot prompt）。"""
    records = get_post_records(limit=100)
    posts = [r for r in records if r.get("rating", 0) > 0]
    if not posts:
        return []

    max_engagement = max(1, max(
        p["likes"] + p["comments"] * 2 + p["shares"] * 3 for p in posts
    ))

    for p in posts:
        engagement_score = (p["likes"] + p["comments"] * 2 + p["shares"] * 3) / max_engagement * 5
        if p["likes"] == 0 and p["comments"] == 0 and p["shares"] == 0:
            p["composite_score"] = p["rating"]
        else:
            p["composite_score"] = p["rating"] * 0.3 + engagement_score * 0.7

    posts.sort(key=lambda p: -p["composite_score"])
    return posts[:limit]


def update_post_metrics(
    row: int,
    fb_post_id: str = "",
    likes: int = 0,
    comments: int = 0,
    shares: int = 0,
    reach: int = 0,
) -> bool:
    """更新貼文的 FB 成效數據。"""
    ws = _get_or_create_sheet("貼文紀錄", POST_HEADERS)
    updates = []
    if fb_post_id:
        updates.append({"row": row, "col": 8, "val": fb_post_id})
    updates.append({"row": row, "col": 9, "val": likes})
    updates.append({"row": row, "col": 10, "val": comments})
    updates.append({"row": row, "col": 11, "val": shares})
    updates.append({"row": row, "col": 12, "val": reach})
    updates.append({"row": row, "col": 13, "val": datetime.now().isoformat()})
    for u in updates:
        ws.update_cell(u["row"], u["col"], u["val"])
    return True


def update_post_rating(row: int, rating: int, notes: str = "") -> bool:
    """更新貼文的主觀評分和備註。"""
    ws = _get_or_create_sheet("貼文紀錄", POST_HEADERS)
    ws.update_cell(row, 6, rating)
    ws.update_cell(row, 7, notes)
    return True


def update_post_content(row: int, post_content: str) -> bool:
    """更新貼文內容（用於儲存手動修改後的版本）。"""
    ws = _get_or_create_sheet("貼文紀錄", POST_HEADERS)
    ws.update_cell(row, 5, post_content)
    return True


# ─── 寫法範本 ──────────────────────────────────────────────

def add_style_example(
    title: str,
    content: str,
    highlights: str,
    source_url: str = "",
    tags: list[str] | None = None,
) -> dict:
    """新增寫法範本。"""
    ws = _get_or_create_sheet("寫法範本", STYLE_HEADERS)
    row = [
        datetime.now().isoformat(),
        title,
        content,
        highlights,
        source_url,
        ", ".join(tags or []),
    ]
    ws.append_row(row, value_input_option="USER_ENTERED")
    last_row = len(ws.get_all_values())
    return {"success": True, "row": last_row, "total": last_row - 1}


def get_style_examples(limit: int = 20) -> list[dict]:
    """取得寫法範本。"""
    ws = _get_or_create_sheet("寫法範本", STYLE_HEADERS)
    rows = ws.get_all_values()
    if len(rows) <= 1:
        return []

    examples = []
    for idx, row in enumerate(rows[1:], start=2):
        if len(row) < 6:
            row.extend([""] * (6 - len(row)))
        examples.append({
            "row_number": idx,
            "created_at": row[0],
            "title": row[1],
            "content": row[2],
            "highlights": row[3],
            "source_url": row[4],
            "tags": [t.strip() for t in row[5].split(",") if t.strip()] if row[5] else [],
        })

    examples.reverse()
    return examples[:limit]
