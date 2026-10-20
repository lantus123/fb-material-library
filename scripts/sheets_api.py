"""
FB素材庫 — Google Sheets API 共用模組
透過 gspread + 服務帳號直接讀寫 Google Sheets。
"""

import json
import os
from datetime import datetime, timedelta
from pathlib import Path
from time import time
from typing import Any, Callable

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


# ─── TTL Cache（避免 gspread 配額爆掉）───────────────────

_CACHE_STORE: dict[str, tuple[float, Any]] = {}
_DEFAULT_TTL = 60  # 秒


def _cached(key: str, fn: Callable[[], Any], ttl: int = _DEFAULT_TTL) -> Any:
    """簡易 TTL 快取。key 相同時在 ttl 秒內直接回傳快取值。"""
    now = time()
    entry = _CACHE_STORE.get(key)
    if entry and now - entry[0] < ttl:
        return entry[1]
    val = fn()
    _CACHE_STORE[key] = (now, val)
    return val


def invalidate_cache(prefix: str = "") -> int:
    """清除快取；若指定 prefix 只清除相符的 key。回傳清除筆數。"""
    if not prefix:
        count = len(_CACHE_STORE)
        _CACHE_STORE.clear()
        return count
    keys = [k for k in _CACHE_STORE.keys() if k.startswith(prefix)]
    for k in keys:
        del _CACHE_STORE[k]
    return len(keys)


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
    """取得或建立工作表，確保表頭與 headers 一致；允許向後擴欄不動既有資料。"""
    ss = _get_spreadsheet()
    try:
        ws = ss.worksheet(name)
    except gspread.WorksheetNotFound:
        ws = ss.add_worksheet(title=name, rows=100, cols=len(headers))
    first_row = ws.row_values(1)
    if first_row != headers:
        if ws.col_count < len(headers):
            ws.add_cols(len(headers) - ws.col_count)
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
    '分享數', '觸及人數', '最後更新',
    '原始內容', '修改原因', '修改原則',
    '發布狀態', '發布時間'
]

STYLE_HEADERS = [
    '收錄時間', '標題', '原文內容', '寫法亮點', '來源URL', '標籤'
]

PRINCIPLE_HEADERS = [
    '建立時間', '類型', '原則', '理由', '來源貼文', '主題',
    '使用次數', '最後引用時間', '狀態', '備註'
]

# 階段 2 常數
PRINCIPLE_DECAY_DAYS = 90          # 超過 N 天未引用的原則自動 archived
MIN_PRINCIPLES_FOR_INJECTION = 5   # 冷啟動門檻：少於 N 條不注入
MAX_PRINCIPLES_IN_PROMPT = 10      # prompt 預算：單次最多注入幾條


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
        post_content,  # 原始內容（AI 生成版，不可變）
        "",  # 修改原因
        "",  # 修改原則
        "",  # 發布狀態
        "",  # 發布時間
    ]
    ws.append_row(row, value_input_option="USER_ENTERED")
    last_row = len(ws.get_all_values())
    invalidate_cache("post_records")
    return {"success": True, "row": last_row, "total": last_row - 1}


def _load_post_records_uncached() -> list[dict]:
    ws = _get_or_create_sheet("貼文紀錄", POST_HEADERS)
    rows = ws.get_all_values()
    if len(rows) <= 1:
        return []

    n = len(POST_HEADERS)
    records = []
    for idx, row in enumerate(rows[1:], start=2):
        if len(row) < n:
            row.extend([""] * (n - len(row)))
        original = row[13] or row[4]
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
            "original_content": original,
            "edit_reasons": row[14],
            "edit_principle": row[15],
            "publish_status": row[16],
            "publish_time": row[17],
        })

    records.reverse()
    return records


def get_post_records(limit: int = 50) -> list[dict]:
    """取得貼文紀錄（60 秒 TTL 快取）。"""
    records = _cached("post_records", _load_post_records_uncached)
    return records[:limit]


def get_top_posts(limit: int = 3) -> list[dict]:
    """取得表現最好的貼文（用於 few-shot prompt）。

    權重：主觀評分 60% + 互動 40%（反轉自舊版 30/70 以避免迴音室）。
    主題平衡：優先確保每個 post_type 至少入選一篇，剩餘名額再依綜合分數填入。
    """
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
            p["composite_score"] = p["rating"] * 0.6 + engagement_score * 0.4

    posts.sort(key=lambda p: -p["composite_score"])

    selected: list[dict] = []
    seen_types: set[str] = set()
    for p in posts:
        pt = p.get("post_type") or "一般"
        if pt not in seen_types:
            selected.append(p)
            seen_types.add(pt)
            if len(selected) >= limit:
                break

    for p in posts:
        if len(selected) >= limit:
            break
        if p not in selected:
            selected.append(p)

    return selected[:limit]


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
    invalidate_cache("post_records")
    return True


def update_post_publish(row: int, *, fb_post_id: str, status: str, publish_time: str) -> bool:
    """寫入發布結果；批次更新保留既有內容與成效欄位。"""
    if status not in {"published", "scheduled", "cancelled", "failed"}:
        raise ValueError("無效的發布狀態")
    ws = _get_or_create_sheet("貼文紀錄", POST_HEADERS)
    try:
        ws.batch_update([
            {"range": f"H{row}", "values": [[fb_post_id]]},
            {"range": f"Q{row}:R{row}", "values": [[status, publish_time]]},
        ], value_input_option="RAW")
    finally:
        invalidate_cache("post_records")
    return True


def update_post_rating(row: int, rating: int, notes: str = "") -> bool:
    """更新貼文的主觀評分和備註。"""
    ws = _get_or_create_sheet("貼文紀錄", POST_HEADERS)
    ws.update_cell(row, 6, rating)
    ws.update_cell(row, 7, notes)
    invalidate_cache("post_records")
    return True


def update_post_content(row: int, post_content: str) -> bool:
    """更新貼文內容（用於儲存手動修改後的版本）。不動原始內容欄位。"""
    ws = _get_or_create_sheet("貼文紀錄", POST_HEADERS)
    ws.update_cell(row, 5, post_content)
    invalidate_cache("post_records")
    return True


def update_edit_reasons(row: int, reasons: str) -> bool:
    """更新修改原因標籤（以 | 分隔的字串）。"""
    ws = _get_or_create_sheet("貼文紀錄", POST_HEADERS)
    ws.update_cell(row, 15, reasons)
    invalidate_cache("post_records")
    return True


def update_edit_principle(row: int, principle: str) -> bool:
    """寫入 diff 分析產出的修改原則。"""
    ws = _get_or_create_sheet("貼文紀錄", POST_HEADERS)
    ws.update_cell(row, 16, principle)
    invalidate_cache("post_records")
    return True


def revert_post_to_original(row: int) -> bool:
    """將貼文內容還原為原始 AI 生成版，同時清空修改原因與原則。"""
    ws = _get_or_create_sheet("貼文紀錄", POST_HEADERS)
    original = ws.cell(row, 14).value or ""
    if not original:
        return False
    ws.update_cell(row, 5, original)
    ws.update_cell(row, 15, "")
    ws.update_cell(row, 16, "")
    invalidate_cache("post_records")
    return True


def get_post_row(row: int) -> dict:
    """讀單一貼文紀錄（含原版/編輯版），供 diff 分析使用。"""
    ws = _get_or_create_sheet("貼文紀錄", POST_HEADERS)
    values = ws.row_values(row)
    n = len(POST_HEADERS)
    if len(values) < n:
        values.extend([""] * (n - len(values)))
    return {
        "row_number": row,
        "material_row": values[2],
        "fb_post_id": values[7],
        "publish_status": values[16],
        "publish_time": values[17],
        "post_content": values[4],
        "original_content": values[13] or values[4],
        "edit_reasons": values[14],
        "edit_principle": values[15],
    }


# ─── 修改原則庫（階段 2）──────────────────────────────────

def _parse_iso(ts: str) -> datetime | None:
    try:
        return datetime.fromisoformat(ts)
    except Exception:
        return None


def _load_principles_uncached() -> list[dict]:
    ws = _get_or_create_sheet("修改原則", PRINCIPLE_HEADERS)
    rows = ws.get_all_values()
    if len(rows) <= 1:
        return []
    n = len(PRINCIPLE_HEADERS)
    records = []
    for idx, row in enumerate(rows[1:], start=2):
        if len(row) < n:
            row.extend([""] * (n - len(row)))
        records.append({
            "row_number": idx,
            "created_at": row[0],
            "type": row[1],
            "principle": row[2],
            "reason": row[3],
            "source_post_row": row[4],
            "topic": row[5],
            "usage_count": int(row[6]) if row[6] and str(row[6]).isdigit() else 0,
            "last_used_at": row[7],
            "status": row[8] or "active",
            "notes": row[9],
        })
    records.reverse()
    return records


def get_all_principles() -> list[dict]:
    """取得全部原則（60 秒 TTL 快取），供管理頁面使用。"""
    return _cached("principles", _load_principles_uncached)


def get_active_principles(
    topic: str | None = None,
    limit: int = MAX_PRINCIPLES_IN_PROMPT,
) -> list[dict]:
    """取得啟用中的原則，供 prompt 注入使用。

    - 過濾掉 archived / disabled 狀態
    - 若指定 topic 則優先同主題，不足時補全不指定主題的原則
    - 超過 PRINCIPLE_DECAY_DAYS 未使用的自動視為 archived（lazy decay，不寫回 Sheet）
    - 排序：按最後引用時間降序，沒用過的按建立時間降序
    """
    all_principles = get_all_principles()
    now = datetime.now()

    def is_alive(p: dict) -> bool:
        if p["status"] != "active":
            return False
        ref_time = _parse_iso(p["last_used_at"]) or _parse_iso(p["created_at"])
        if ref_time and (now - ref_time).days > PRINCIPLE_DECAY_DAYS:
            return False
        return True

    alive = [p for p in all_principles if is_alive(p)]

    def sort_key(p: dict):
        t = _parse_iso(p["last_used_at"]) or _parse_iso(p["created_at"]) or datetime.min
        return -t.timestamp()

    alive.sort(key=sort_key)

    if topic:
        same_topic = [p for p in alive if p["topic"] == topic]
        other_topic = [p for p in alive if p["topic"] != topic]
        merged = same_topic + other_topic
    else:
        merged = alive

    return merged[:limit]


def add_principle(
    principle_type: str,
    principle: str,
    reason: str = "",
    source_post_row: int | str = "",
    topic: str = "",
    notes: str = "",
) -> dict:
    """新增一條修改原則。回傳 {success, row}。"""
    ws = _get_or_create_sheet("修改原則", PRINCIPLE_HEADERS)
    row = [
        datetime.now().isoformat(),
        principle_type,
        principle,
        reason,
        str(source_post_row),
        topic,
        0,
        "",
        "active",
        notes,
    ]
    ws.append_row(row, value_input_option="USER_ENTERED")
    last_row = len(ws.get_all_values())
    invalidate_cache("principles")
    return {"success": True, "row": last_row}


def delete_principles_by_source(source_post_row: int) -> int:
    """刪除所有來源貼文列號等於 source_post_row 的原則。回傳刪除筆數。"""
    ws = _get_or_create_sheet("修改原則", PRINCIPLE_HEADERS)
    rows = ws.get_all_values()
    to_delete = []
    for idx, row in enumerate(rows[1:], start=2):
        if len(row) >= 5 and row[4] == str(source_post_row):
            to_delete.append(idx)
    for row_num in reversed(to_delete):
        ws.delete_rows(row_num)
    if to_delete:
        invalidate_cache("principles")
    return len(to_delete)


def update_principle(
    row: int,
    principle: str | None = None,
    reason: str | None = None,
    principle_type: str | None = None,
    topic: str | None = None,
    notes: str | None = None,
) -> bool:
    """手動更新原則內容。只更新非 None 的欄位。"""
    ws = _get_or_create_sheet("修改原則", PRINCIPLE_HEADERS)
    updates = []
    if principle_type is not None:
        updates.append((row, 2, principle_type))
    if principle is not None:
        updates.append((row, 3, principle))
    if reason is not None:
        updates.append((row, 4, reason))
    if topic is not None:
        updates.append((row, 6, topic))
    if notes is not None:
        updates.append((row, 10, notes))
    for r, c, v in updates:
        ws.update_cell(r, c, v)
    invalidate_cache("principles")
    return True


def set_principle_status(row: int, status: str) -> bool:
    """設定原則狀態：active / disabled / archived。"""
    if status not in ("active", "disabled", "archived"):
        return False
    ws = _get_or_create_sheet("修改原則", PRINCIPLE_HEADERS)
    ws.update_cell(row, 9, status)
    invalidate_cache("principles")
    return True


def delete_principle(row: int) -> bool:
    """永久刪除一條原則。"""
    ws = _get_or_create_sheet("修改原則", PRINCIPLE_HEADERS)
    ws.delete_rows(row)
    invalidate_cache("principles")
    return True


def bump_principles_usage(rows: list[int]) -> None:
    """批次更新多條原則的使用次數 +1 與最後引用時間。"""
    if not rows:
        return
    ws = _get_or_create_sheet("修改原則", PRINCIPLE_HEADERS)
    now = datetime.now().isoformat()
    for r in rows:
        try:
            cur = ws.cell(r, 7).value
            count = int(cur) if cur and str(cur).isdigit() else 0
        except Exception:
            count = 0
        ws.update_cell(r, 7, count + 1)
        ws.update_cell(r, 8, now)
    invalidate_cache("principles")


def apply_principle_decay() -> int:
    """把超過 PRINCIPLE_DECAY_DAYS 未使用的原則標為 archived。回傳受影響筆數。"""
    all_principles = get_all_principles()
    now = datetime.now()
    archived = 0
    for p in all_principles:
        if p["status"] != "active":
            continue
        ref_time = _parse_iso(p["last_used_at"]) or _parse_iso(p["created_at"])
        if ref_time and (now - ref_time).days > PRINCIPLE_DECAY_DAYS:
            set_principle_status(p["row_number"], "archived")
            archived += 1
    return archived


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
    invalidate_cache("style_examples")
    return {"success": True, "row": last_row, "total": last_row - 1}


def _load_style_examples_uncached() -> list[dict]:
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
    return examples


def get_style_examples(limit: int = 20) -> list[dict]:
    """取得寫法範本（60 秒 TTL 快取）。"""
    examples = _cached("style_examples", _load_style_examples_uncached)
    return examples[:limit]
