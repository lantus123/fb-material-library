#!/usr/bin/env python3
"""
FB素材庫 — 自動爬取與分析腳本
爬取教育網站文章，透過 Gemini 分析後存入 Google Sheets 素材庫。
"""

import difflib
import json
import os
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import urlparse, urlunparse, urljoin

from google import genai
import feedparser
import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv

# 載入環境變數
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
APPS_SCRIPT_API_URL = os.getenv("APPS_SCRIPT_API_URL")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

# 專案根目錄
PROJECT_ROOT = Path(__file__).resolve().parent.parent
SOURCES_PATH = PROJECT_ROOT / "config" / "sources.json"
ANALYSIS_PROMPT_PATH = PROJECT_ROOT / "prompts" / "analysis.md"

# 請求設定
REQUEST_TIMEOUT = 30
REQUEST_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; YouJianBot/1.0; "
        "+https://github.com/lantus123/fb-material-library)"
    )
}

# 重複偵測設定
TITLE_SIMILARITY_THRESHOLD = 0.85


def load_sources() -> dict:
    """載入爬取來源清單。"""
    with open(SOURCES_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def load_analysis_prompt() -> str:
    """載入文章分析 prompt 模板。"""
    with open(ANALYSIS_PROMPT_PATH, "r", encoding="utf-8") as f:
        return f.read()


# ─── 重複偵測 ───────────────────────────────────────────────

def normalize_url(url: str) -> str:
    """正規化 URL，移除尾端斜線、query 參數、fragment。"""
    parsed = urlparse(url)
    # 移除 www. 前綴
    netloc = parsed.netloc.lower()
    if netloc.startswith("www."):
        netloc = netloc[4:]
    path = parsed.path.rstrip("/")
    return urlunparse((parsed.scheme.lower(), netloc, path, "", "", ""))


def fetch_existing_urls() -> tuple[set[str], list[str]]:
    """從 Google Sheets 取得已存的 URL 和標題，用於重複偵測。"""
    try:
        resp = requests.get(
            APPS_SCRIPT_API_URL,
            params={"action": "getExistingUrls"},
            timeout=REQUEST_TIMEOUT,
        )
        data = resp.json()
        urls = {normalize_url(u) for u in data.get("urls", []) if u}
        titles = [t for t in data.get("titles", []) if t]
        return urls, titles
    except Exception as e:
        print(f"  ⚠ 無法取得已存 URL（將跳過重複偵測）：{e}")
        return set(), []


def is_duplicate(article: dict, existing_urls: set[str], existing_titles: list[str]) -> bool:
    """檢查文章是否重複（URL 比對 + 標題相似度）。"""
    # Tier 1: URL 比對
    url = article.get("url", "")
    if url and normalize_url(url) in existing_urls:
        return True

    # Tier 2: 標題相似度
    title = article.get("title", "")
    if title:
        for existing_title in existing_titles:
            ratio = difflib.SequenceMatcher(None, title, existing_title).ratio()
            if ratio >= TITLE_SIMILARITY_THRESHOLD:
                return True

    return False


# ─── 文章抓取 ───────────────────────────────────────────────

def fetch_rss_articles(source: dict, max_days: int = 7) -> list[dict]:
    """從 RSS feed 抓取最近的文章。"""
    feed_url = source.get("feed_url")
    if not feed_url:
        return []

    try:
        feed = feedparser.parse(feed_url)
        articles = []
        cutoff = datetime.now() - timedelta(days=max_days)

        for entry in feed.entries[:10]:  # 每個來源最多處理 10 篇
            # 解析發布日期
            published = None
            if hasattr(entry, "published_parsed") and entry.published_parsed:
                published = datetime(*entry.published_parsed[:6])
            elif hasattr(entry, "updated_parsed") and entry.updated_parsed:
                published = datetime(*entry.updated_parsed[:6])

            if published and published < cutoff:
                continue

            articles.append({
                "title": entry.get("title", ""),
                "url": entry.get("link", ""),
                "summary": entry.get("summary", ""),
                "source_name": source["name"],
            })

        return articles
    except Exception as e:
        print(f"  ⚠ RSS 抓取失敗 ({source['name']}): {e}")
        return []


def fetch_scraped_articles(source: dict, max_days: int = 7) -> list[dict]:
    """從網頁列表頁抓取文章連結（用於無 RSS 的來源）。"""
    listing_url = source.get("listing_url")
    link_selector = source.get("link_selector")
    if not listing_url or not link_selector:
        print(f"  ⚠ 缺少 listing_url 或 link_selector ({source['name']})")
        return []

    try:
        resp = requests.get(listing_url, headers=REQUEST_HEADERS, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        # 處理編碼（某些中文網站可能不是 UTF-8）
        if resp.apparent_encoding:
            resp.encoding = resp.apparent_encoding
        soup = BeautifulSoup(resp.text, "html.parser")

        articles = []
        links = soup.select(link_selector)[:10]  # 最多 10 篇

        for link in links:
            href = link.get("href", "")
            if not href:
                continue
            # 處理相對路徑
            full_url = urljoin(listing_url, href)
            title = link.get_text(strip=True) or full_url

            articles.append({
                "title": title,
                "url": full_url,
                "summary": "",
                "source_name": source["name"],
            })

        return articles
    except Exception as e:
        print(f"  ⚠ 網頁列表抓取失敗 ({source['name']}): {e}")
        return []


def fetch_page_content(url: str, content_selector: str | None = None) -> str | None:
    """抓取網頁內文。"""
    try:
        resp = requests.get(url, headers=REQUEST_HEADERS, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        # 處理編碼
        if resp.apparent_encoding:
            resp.encoding = resp.apparent_encoding
        soup = BeautifulSoup(resp.text, "html.parser")

        # 移除無關元素
        for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
            tag.decompose()

        # 優先使用自訂 selector，其次用通用邏輯
        content_tag = None
        if content_selector:
            content_tag = soup.select_one(content_selector)
        if not content_tag:
            content_tag = soup.find("article") or soup.find("main") or soup.find("body")
        if not content_tag:
            return None

        text = content_tag.get_text(separator="\n", strip=True)
        # 中文內容較密集，給多一點字數空間
        max_chars = 4000
        return text[:max_chars] if len(text) > max_chars else text
    except Exception as e:
        print(f"  ⚠ 網頁抓取失敗 ({url}): {e}")
        return None


def analyze_article(client: genai.Client, article: dict, prompt_template: str) -> dict | None:
    """用 Gemini 分析文章。"""
    article_text = article.get("content") or article.get("summary", "")
    if not article_text or len(article_text.strip()) < 100:
        print(f"  ⏭ 內文太短，跳過：{article['title']}")
        return None

    prompt = prompt_template.replace("{{source_title}}", article.get("source_name", ""))
    prompt = prompt.replace("{{source_url}}", article.get("url", ""))
    prompt = prompt.replace("{{article_text}}", article_text)

    try:
        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=prompt,
        )

        response_text = response.text

        # 嘗試從回應中提取 JSON
        json_start = response_text.find("{")
        json_end = response_text.rfind("}") + 1
        if json_start == -1 or json_end == 0:
            print(f"  ⚠ Gemini 回應無 JSON：{article['title']}")
            return None

        result = json.loads(response_text[json_start:json_end])
        result["source_url"] = article.get("url", "")
        result["source_title"] = article.get("source_name", "")
        return result
    except json.JSONDecodeError as e:
        print(f"  ⚠ JSON 解析失敗：{e}")
        return None
    except Exception as e:
        print(f"  ⚠ Gemini API 錯誤：{e}")
        return None


def post_to_sheets(material: dict) -> bool:
    """將分析結果 POST 到 Apps Script API。"""
    payload = {
        "action": "addMaterial",
        "curated_at": datetime.now().isoformat(),
        "title": material.get("title", ""),
        "summary": material.get("summary", ""),
        "topics": material.get("topics", []),
        "angles": material.get("angles", []),
        "key_facts": material.get("key_facts", []),
        "relevance_score": material.get("relevance_score", 0),
        "relevance_reason": material.get("relevance_reason", ""),
        "source_url": material.get("source_url", ""),
        "source_title": material.get("source_title", ""),
        "raw_text": material.get("raw_text", ""),
    }

    try:
        resp = requests.post(
            APPS_SCRIPT_API_URL,
            json=payload,
            timeout=REQUEST_TIMEOUT,
            headers={"Content-Type": "application/json"},
        )
        result = resp.json()
        if result.get("success"):
            print(f"  ✅ 已存入素材庫 (第 {result.get('row')} 列，共 {result.get('total')} 筆)")
            return True
        elif result.get("error") == "duplicate":
            print(f"  ⏭ Sheets 端偵測到重複，跳過")
            return False
        else:
            print(f"  ❌ 存入失敗：{result.get('error')}")
            return False
    except Exception as e:
        print(f"  ❌ API 請求失敗：{e}")
        return False


# ─── Email 報告 ──────────────────────────────────────────────

def send_email_report(stats: dict):
    """透過 Apps Script 寄送爬取報告 email。"""
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    body = f"""
    <h2>📊 FB素材庫 — 爬取報告</h2>
    <p><strong>時間：</strong>{now}</p>
    <hr>
    <table style="border-collapse:collapse; font-size:14px;">
      <tr><td style="padding:4px 12px;">📰 處理文章數</td><td><strong>{stats.get('processed', 0)}</strong></td></tr>
      <tr><td style="padding:4px 12px;">✅ 新增素材數</td><td><strong>{stats.get('saved', 0)}</strong></td></tr>
      <tr><td style="padding:4px 12px;">⏭ 重複跳過</td><td><strong>{stats.get('duplicates', 0)}</strong></td></tr>
      <tr><td style="padding:4px 12px;">🚫 分數不足</td><td><strong>{stats.get('low_score', 0)}</strong></td></tr>
      <tr><td style="padding:4px 12px;">❌ 失敗</td><td><strong>{stats.get('errors', 0)}</strong></td></tr>
    </table>
    <hr>
    <p style="color:#888; font-size:12px;">此信件由 FB素材庫自動排程系統發送</p>
    """

    subject = f"FB素材庫爬取報告 — {now}（新增 {stats.get('saved', 0)} 篇）"

    payload = {
        "action": "sendReport",
        "email": "r19911219@gmail.com",
        "subject": subject,
        "body": body,
    }

    try:
        resp = requests.post(
            APPS_SCRIPT_API_URL,
            json=payload,
            timeout=REQUEST_TIMEOUT,
            headers={"Content-Type": "application/json"},
        )
        result = resp.json()
        if result.get("success"):
            print(f"  📧 報告已寄出至 r19911219@gmail.com")
        else:
            print(f"  ⚠ 寄信失敗：{result.get('error')}")
    except Exception as e:
        print(f"  ⚠ 寄信請求失敗：{e}")


# ─── 主要爬取邏輯 ────────────────────────────────────────────

def crawl_single_url(
    client: genai.Client,
    url: str,
    source_name: str,
    prompt_template: str,
    existing_urls: set[str] | None = None,
    force: bool = False,
) -> bool:
    """手動爬取並分析單一 URL。"""
    print(f"\n📄 處理手動來源：{url}")

    # 重複偵測
    if not force and existing_urls and normalize_url(url) in existing_urls:
        print("  ⏭ 此 URL 已存在素材庫中，跳過（使用 --force 可強制重新分析）")
        return False

    content = fetch_page_content(url)
    if not content:
        print("  ⚠ 無法取得內文")
        return False

    article = {
        "title": source_name or url,
        "url": url,
        "content": content,
        "source_name": source_name or "手動輸入",
    }

    result = analyze_article(client, article, prompt_template)
    if not result:
        return False

    return post_to_sheets(result)


def run_auto_crawl(
    client: genai.Client,
    sources: list,
    prompt_template: str,
    max_days: int = 7,
    force: bool = False,
    scheduled: bool = False,
) -> dict:
    """執行自動爬取所有來源。回傳統計資料。"""
    stats = {"processed": 0, "saved": 0, "duplicates": 0, "low_score": 0, "errors": 0}

    # 取得已存 URL 和標題（重複偵測用）
    existing_urls, existing_titles = set(), []
    if not force:
        print("🔍 載入已存素材清單（重複偵測）...")
        existing_urls, existing_titles = fetch_existing_urls()
        print(f"  📋 已有 {len(existing_urls)} 筆素材")

    for source in sources:
        print(f"\n🔍 爬取來源：{source['name']}")

        # 根據 crawl_type 分流
        crawl_type = source.get("crawl_type", "rss")
        if crawl_type == "scrape":
            articles = fetch_scraped_articles(source, max_days=max_days)
        else:
            articles = fetch_rss_articles(source, max_days=max_days)

        if not articles:
            print(f"  ℹ 無新文章或無法取得文章列表")
            continue

        print(f"  📰 找到 {len(articles)} 篇文章")

        for article in articles:
            stats["processed"] += 1
            print(f"\n  📝 分析：{article['title'][:50]}...")

            # 重複偵測
            if not force and is_duplicate(article, existing_urls, existing_titles):
                print(f"  ⏭ 重複文章，跳過")
                stats["duplicates"] += 1
                continue

            # 抓取完整內文
            content_selector = source.get("content_selector")
            content = fetch_page_content(article["url"], content_selector=content_selector)
            if content:
                article["content"] = content

            result = analyze_article(client, article, prompt_template)
            if not result:
                stats["errors"] += 1
                continue

            # 只存入相關性分數 >= 5 的文章
            score = result.get("relevance_score", 0)
            if score < 5:
                print(f"  ⏭ 相關性不足 (分數: {score})，跳過")
                stats["low_score"] += 1
                continue

            if post_to_sheets(result):
                stats["saved"] += 1
                # 更新本地快取，避免同一次爬取中重複
                existing_urls.add(normalize_url(article["url"]))
                existing_titles.append(result.get("title", article["title"]))

            # 避免 API rate limit
            time.sleep(2)

    print(f"\n{'='*50}")
    print(f"✅ 爬取完成！處理 {stats['processed']} 篇文章，存入 {stats['saved']} 篇素材")
    print(f"   重複跳過 {stats['duplicates']} 篇，分數不足 {stats['low_score']} 篇，失敗 {stats['errors']} 篇")

    return stats


def main():
    """主程式進入點。"""
    if not GEMINI_API_KEY:
        print("❌ 錯誤：請設定 GEMINI_API_KEY 環境變數")
        print("   複製 .env.example 為 .env 並填入 API Key")
        sys.exit(1)

    if not APPS_SCRIPT_API_URL:
        print("❌ 錯誤：請設定 APPS_SCRIPT_API_URL 環境變數")
        sys.exit(1)

    client = genai.Client(api_key=GEMINI_API_KEY)
    sources = load_sources()
    prompt_template = load_analysis_prompt()

    # 解析參數
    args = sys.argv[1:]
    force = "--force" in args
    scheduled = "--scheduled" in args
    if force:
        args.remove("--force")
    if scheduled:
        args.remove("--scheduled")

    # 命令列參數處理
    if args:
        if args[0] == "--url" and len(args) > 1:
            # 手動模式：爬取單一 URL
            url = args[1]
            source_name = args[2] if len(args) > 2 else ""
            existing_urls, _ = (set(), []) if force else fetch_existing_urls()
            crawl_single_url(client, url, source_name, prompt_template, existing_urls, force)
        elif args[0] == "--days" and len(args) > 1:
            # 指定天數
            max_days = int(args[1])
            stats = run_auto_crawl(client, sources["auto_crawl"], prompt_template, max_days=max_days, force=force, scheduled=scheduled)
            if scheduled:
                send_email_report(stats)
        elif args[0] == "--help":
            print("用法：")
            print("  python crawl.py                  # 自動爬取所有來源（最近7天）")
            print("  python crawl.py --days 14        # 自動爬取（最近14天）")
            print("  python crawl.py --url <URL>      # 手動爬取單一網址")
            print("  python crawl.py --url <URL> 來源名稱  # 手動爬取並指定來源名稱")
            print("  python crawl.py --force           # 強制略過重複偵測")
            print("  python crawl.py --scheduled       # 排程模式（完成後寄送 email 報告）")
        else:
            print(f"未知參數：{args[0]}，使用 --help 查看用法")
    else:
        # 預設：自動爬取
        print("🚀 FB素材庫 — 自動爬取開始")
        print(f"⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        stats = run_auto_crawl(client, sources["auto_crawl"], prompt_template, force=force, scheduled=scheduled)
        if scheduled:
            send_email_report(stats)


if __name__ == "__main__":
    main()
