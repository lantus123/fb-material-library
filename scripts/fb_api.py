#!/usr/bin/env python3
"""
FB素材庫 — Facebook Graph API 模組
讀取粉專成效，並提供人工確認後的發布與排程取消入口。
"""

import difflib
import argparse
import re
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import requests
GRAPH_API_BASE = "https://graph.facebook.com/v21.0"

# 確保專案根目錄在 sys.path 中
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts import sheets_api

TAIPEI = ZoneInfo("Asia/Taipei")


def redact_token(text: str) -> str:
    """遮蔽 URL 中的 access_token 與設定中的完整 token。"""
    text = re.sub(r"access_token=[^&\s\"']*", "access_token=***", str(text))
    token = sheets_api._get_secret("FB_PAGE_ACCESS_TOKEN")
    if token:
        text = text.replace(token, "***")
    return text


class FBPublishError(Exception):
    def __init__(self, message: str, code=None):
        self.code = code
        self.message = redact_token(message)
        super().__init__(self.message)


class _PublishArgumentParser(argparse.ArgumentParser):
    def error(self, message):
        raise FBPublishError("發布參數錯誤，請使用 --help 查看用法")


def _configuration() -> tuple[str, str]:
    page = sheets_api._get_secret("FB_PAGE_ID")
    token = sheets_api._get_secret("FB_PAGE_ACCESS_TOKEN")
    if not page or not token:
        raise FBPublishError("尚未設定 FB_PAGE_ID／FB_PAGE_ACCESS_TOKEN")
    return page, token


def _request(method: str, url: str, **kwargs) -> dict:
    """共用錯誤處理；不重試發布，以免網路逾時造成重複貼文。"""
    try:
        response = getattr(requests, method)(url, **kwargs)
        try:
            payload = response.json()
        except ValueError:
            raise FBPublishError(f"FB API 回應格式錯誤（HTTP {response.status_code}）") from None
        if not isinstance(payload, dict):
            raise FBPublishError("FB API 回應格式錯誤")
        error = payload.get("error")
        if "error" in payload or not 200 <= response.status_code < 300:
            error = error if isinstance(error, dict) else {}
            raise FBPublishError(
                error.get("message") or f"FB API 請求失敗（HTTP {response.status_code}）",
                code=error.get("code"),
            )
        return payload
    except requests.RequestException as exc:
        raise FBPublishError(f"FB API 請求失敗：{exc}") from None


def publish_post(
    message: str, *, link: str | None = None, image_path: str | None = None,
    image_url: str | None = None, scheduled_at: datetime | None = None,
) -> dict:
    """發布單篇文字／單圖貼文；呼叫端必須先取得人工確認。"""
    message = message.strip()
    if not message:
        raise ValueError("貼文內容不可為空")
    if image_path is not None and image_url is not None:
        raise ValueError("本機圖片與圖片網址只能擇一")
    now = datetime.now(TAIPEI)
    publish_time = now
    data = {"message": message}
    if scheduled_at is not None:
        publish_time = scheduled_at.replace(tzinfo=TAIPEI) if scheduled_at.tzinfo is None else scheduled_at
        delay = publish_time.timestamp() - now.timestamp()
        if not 600 <= delay <= 28 * 86400:
            raise FBPublishError("排程時間須距現在至少 10 分鐘、最多 28 天（含邊界）。")
        data.update(published="false", scheduled_publish_time=int(publish_time.timestamp()))
    page, token = _configuration()
    data["access_token"] = token
    endpoint = "photos" if image_path or image_url else "feed"
    url = f"{GRAPH_API_BASE}/{page}/{endpoint}"
    if image_url:
        data["url"] = image_url
    elif link and not image_path:
        data["link"] = link
    if image_path:
        try:
            with open(image_path, "rb") as fh:
                payload = _request("post", url, data=data, files={"source": fh}, timeout=60)
        except OSError as exc:
            raise FBPublishError(f"無法讀取圖片：{exc}") from None
    else:
        payload = _request("post", url, data=data, timeout=60 if image_url else 30)
    post_id = payload.get("post_id") or payload.get("id")
    if not post_id:
        raise FBPublishError("FB 未回傳貼文 ID，請先到粉專確認結果，避免重複發布。")
    return {
        "post_id": str(post_id),
        "status": "scheduled" if scheduled_at is not None else "published",
        "publish_time": publish_time.astimezone(TAIPEI).isoformat(),
    }


def delete_post(post_id: str) -> bool:
    """刪除指定 ID；使用者入口僅允許取消排程。"""
    _, token = _configuration()
    return bool(_request(
        "delete", f"{GRAPH_API_BASE}/{post_id}",
        params={"access_token": token}, timeout=30,
    ).get("success"))


def get_scheduled_posts() -> list[dict]:
    page, token = _configuration()
    return _request(
        "get", f"{GRAPH_API_BASE}/{page}/scheduled_posts",
        params={"access_token": token, "fields": "id,message,scheduled_publish_time"},
        timeout=30,
    ).get("data", [])


def publish_record(row: int, *, scheduled_at=None, image_path=None, image_url=None,
                   expected_content: str | None = None) -> dict:
    try:
        record = sheets_api.get_post_row(row)
    except Exception as exc:
        raise FBPublishError(f"讀取貼文紀錄失敗：{exc}") from None
    if expected_content is not None and record.get("post_content", "") != expected_content:
        raise FBPublishError("貼文內容已變更，請重新載入、預覽並確認後再發布。")
    if record.get("publish_status") in {"published", "scheduled"}:
        raise FBPublishError("這筆紀錄已發布或已排程，請勿重複發布。")
    result = publish_post(
        record.get("post_content", ""), scheduled_at=scheduled_at,
        image_path=image_path, image_url=image_url,
    )
    errors = []
    try:
        if not sheets_api.update_post_publish(
            row, fb_post_id=result["post_id"], status=result["status"],
            publish_time=result["publish_time"],
        ):
            raise RuntimeError("發布紀錄寫入失敗")
    except Exception as exc:
        errors.append(f"發布紀錄：{redact_token(str(exc))}")
    material_row = str(record.get("material_row") or "").strip()
    if material_row.isascii() and material_row.isdigit() and int(material_row) >= 2:
        try:
            if not sheets_api.mark_used(int(material_row)):
                raise RuntimeError("素材標記失敗")
        except Exception as exc:
            errors.append(f"素材標記：{redact_token(str(exc))}")
    if errors:
        result["sheet_error"] = "；".join(errors)
    return result


def cancel_scheduled(row: int) -> bool:
    try:
        record = sheets_api.get_post_row(row)
    except Exception as exc:
        raise FBPublishError(f"讀取貼文紀錄失敗：{exc}") from None
    if record.get("publish_status") != "scheduled" or not record.get("fb_post_id"):
        raise FBPublishError("只能取消狀態為 scheduled 且有貼文 ID 的排程。")
    if record.get("publish_time"):
        try:
            scheduled_time = datetime.fromisoformat(record["publish_time"])
        except ValueError:
            raise FBPublishError("排程時間無法辨識，請先到粉專確認排程狀態。") from None
        if scheduled_time.tzinfo is None:
            scheduled_time = scheduled_time.replace(tzinfo=TAIPEI)
        if scheduled_time <= datetime.now(TAIPEI):
            raise FBPublishError("排程時間已到，貼文可能已發布，請到粉專確認狀態。")
    post_id = record["fb_post_id"]
    if not delete_post(post_id):
        return False
    try:
        if not sheets_api.update_post_publish(
            row, fb_post_id=post_id, status="cancelled",
            publish_time=record.get("publish_time", ""),
        ):
            raise RuntimeError("取消紀錄寫入失敗")
    except Exception as exc:
        raise FBPublishError(
            f"FB 排程已取消但紀錄沒更新，貼文 ID 是 {post_id}，請人工補登：{exc}"
        ) from None
    return True


def is_configured() -> bool:
    """檢查 FB API 是否已設定。"""
    return bool(sheets_api._get_secret("FB_PAGE_ID") and sheets_api._get_secret("FB_PAGE_ACCESS_TOKEN"))


def get_page_posts(since_days: int = 30, limit: int = 50) -> list[dict]:
    """取得粉專近期貼文。"""
    if not is_configured():
        return []

    from datetime import datetime, timedelta
    since_ts = int((datetime.now() - timedelta(days=since_days)).timestamp())

    page, token = _configuration()
    url = f"{GRAPH_API_BASE}/{page}/published_posts"
    params = {
        "access_token": token,
        "fields": "id,message,created_time,shares",
        "since": since_ts,
        "limit": limit,
    }

    try:
        resp = requests.get(url, params=params, timeout=30)
        data = resp.json()
        if "error" in data:
            print(redact_token(f"❌ FB API 錯誤：{data['error'].get('message', '')}"))
            return []
        return data.get("data", [])
    except Exception as e:
        print(redact_token(f"❌ FB API 請求失敗：{e}"))
        return []


def get_post_insights(post_id: str) -> dict:
    """取得單篇貼文的成效數據。"""
    if not is_configured():
        return {}

    _, token = _configuration()
    url = f"{GRAPH_API_BASE}/{post_id}"
    params = {
        "access_token": token,
        "fields": "likes.summary(true),comments.summary(true),shares",
    }

    try:
        resp = requests.get(url, params=params, timeout=30)
        data = resp.json()
        if "error" in data:
            print(redact_token(f"❌ FB API 錯誤：{data['error'].get('message', '')}"))
            return {}

        likes = data.get("likes", {}).get("summary", {}).get("total_count", 0)
        comments = data.get("comments", {}).get("summary", {}).get("total_count", 0)
        shares = data.get("shares", {}).get("count", 0) if data.get("shares") else 0

        # 嘗試取得觸及數
        reach = 0
        try:
            insights_url = f"{GRAPH_API_BASE}/{post_id}/insights"
            insights_params = {
                "access_token": token,
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
        print(redact_token(f"❌ FB API 請求失敗：{e}"))
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
                print(redact_token(f"  ✅ 更新成功：{r.get('material_title', '?')} (👍{insights.get('likes', 0)})"))

    return updated


def _main():
    """CLI 入口。"""
    if not is_configured():
        print("⚠ 尚未設定 FB_PAGE_ID 和 FB_PAGE_ACCESS_TOKEN")
        print("  請在 Streamlit secrets 或 .env 中設定這兩個變數")
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
            print(redact_token(f"\n  📝 {record.get('material_title', '?')} (相似度: {ratio:.0%})"))
            print(redact_token(f"     FB: {fb_post.get('message', '')[:50]}..."))
            print(redact_token(f"     FB ID: {fb_post.get('id', '')}"))

    elif args[0] == "--publish":
        parser = _PublishArgumentParser(add_help=False)
        parser.add_argument("--publish", type=int, required=True)
        parser.add_argument("--at")
        parser.add_argument("--image")
        parser.add_argument("--yes", action="store_true")
        # 不使用 argparse 的原始錯誤輸出，避免參數內含 token 時外洩。
        options, unknown = parser.parse_known_args(args)
        if unknown or options.publish < 2:
            raise FBPublishError("發布參數不正確，請使用 --help 查看用法")
        try:
            scheduled_at = datetime.strptime(options.at, "%Y-%m-%d %H:%M").replace(tzinfo=TAIPEI) if options.at else None
        except ValueError:
            raise FBPublishError("排程時間格式須為 YYYY-MM-DD HH:MM（台北時間）") from None
        record = sheets_api.get_post_row(options.publish)
        content = record.get("post_content", "")
        print(redact_token(f"將發布的全文：\n{content}"))
        print(f"目標：{scheduled_at.isoformat() if scheduled_at else '立即發布'}")
        print(redact_token(f"圖片：{options.image or '無'}"))
        if not options.yes:
            if not sys.stdin.isatty():
                print("非互動環境請加 --yes")
                sys.exit(2)
            if input("確認發布？(y/N) ").strip().lower() != "y":
                print("已取消發布")
                return
        image_arg = {}
        if options.image:
            image_arg["image_url" if options.image.lower().startswith(("http://", "https://")) else "image_path"] = options.image
        result = publish_record(
            options.publish, scheduled_at=scheduled_at, expected_content=content, **image_arg,
        )
        status = "已排程" if result["status"] == "scheduled" else "已發布"
        print(redact_token(f"✅ {status}：https://www.facebook.com/{result['post_id']}"))
        if result.get("sheet_error"):
            print(redact_token(
                f"⚠ 已發布／排程但紀錄沒更新，貼文 ID 是 {result['post_id']}，請人工補登：{result['sheet_error']}"
            ))

    elif args[0] == "--scheduled":
        for post in get_scheduled_posts():
            timestamp = post.get("scheduled_publish_time")
            when = datetime.fromtimestamp(int(timestamp), TAIPEI).strftime("%Y-%m-%d %H:%M")
            print(redact_token(f"{post.get('id', '')} | {when} 台北 | {post.get('message', '')[:40]}"))

    elif args[0] == "--cancel":
        if len(args) != 2 or not args[1].isdigit() or int(args[1]) < 2:
            raise FBPublishError("用法：--cancel <貼文紀錄列號>")
        if cancel_scheduled(int(args[1])):
            print("✅ 已取消排程")
        else:
            raise FBPublishError("FB 未確認取消成功，請先查看粉專排程")

    elif args[0] == "--help":
        print("用法：")
        print("  python fb_api.py --refresh  # 批次更新所有 FB 成效")
        print("  python fb_api.py --match    # 自動比對 FB 貼文與紀錄")
        print('  python fb_api.py --publish <row> [--at "YYYY-MM-DD HH:MM"] [--image <path|url>] [--yes]')
        print("    發布前預覽全文；時間採台北時區，排程限 10 分鐘至 28 天")
        print("    非互動環境必須加 --yes；互動環境需確認 y")
        print("  python fb_api.py --scheduled  # 列出排程中貼文")
        print("  python fb_api.py --cancel <row>  # 取消排程")
    else:
        print(redact_token(f"未知參數：{args[0]}，使用 --help 查看用法"))


def main():
    try:
        _main()
    except Exception as exc:
        print(redact_token(f"❌ {exc}"))
        sys.exit(1)


if __name__ == "__main__":
    main()
