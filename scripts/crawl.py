#!/usr/bin/env python3
"""
FB素材庫 — 自動爬取與分析腳本
爬取教育網站文章，透過 Claude 分析後存入 Google Sheets 素材庫。
"""

import json
import os
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

import anthropic
import feedparser
import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv

# 載入環境變數
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
APPS_SCRIPT_API_URL = os.getenv("APPS_SCRIPT_API_URL")
CLAUDE_MODEL = os.getenv("CLAUDE_MODEL", "claude-sonnet-4-20250514")

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


def load_sources() -> dict:
    """載入爬取來源清單。"""
    with open(SOURCES_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def load_analysis_prompt() -> str:
    """載入文章分析 prompt 模板。"""
    with open(ANALYSIS_PROMPT_PATH, "r", encoding="utf-8") as f:
        return f.read()


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


def fetch_page_content(url: str) -> str | None:
    """抓取網頁內文。"""
    try:
        resp = requests.get(url, headers=REQUEST_HEADERS, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        # 移除無關元素
        for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
            tag.decompose()

        # 優先取 article 標籤，其次取 main，最後取 body
        content_tag = soup.find("article") or soup.find("main") or soup.find("body")
        if not content_tag:
            return None

        text = content_tag.get_text(separator="\n", strip=True)
        # 截取前 3000 字避免 token 過多
        return text[:3000] if len(text) > 3000 else text
    except Exception as e:
        print(f"  ⚠ 網頁抓取失敗 ({url}): {e}")
        return None


def analyze_article(client: anthropic.Anthropic, article: dict, prompt_template: str) -> dict | None:
    """用 Claude 分析文章。"""
    article_text = article.get("content") or article.get("summary", "")
    if not article_text or len(article_text.strip()) < 100:
        print(f"  ⏭ 內文太短，跳過：{article['title']}")
        return None

    prompt = prompt_template.replace("{{source_title}}", article.get("source_name", ""))
    prompt = prompt.replace("{{source_url}}", article.get("url", ""))
    prompt = prompt.replace("{{article_text}}", article_text)

    try:
        message = client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=1500,
            messages=[{"role": "user", "content": prompt}],
        )

        response_text = message.content[0].text

        # 嘗試從回應中提取 JSON
        json_start = response_text.find("{")
        json_end = response_text.rfind("}") + 1
        if json_start == -1 or json_end == 0:
            print(f"  ⚠ Claude 回應無 JSON：{article['title']}")
            return None

        result = json.loads(response_text[json_start:json_end])
        result["source_url"] = article.get("url", "")
        result["source_title"] = article.get("source_name", "")
        return result
    except json.JSONDecodeError as e:
        print(f"  ⚠ JSON 解析失敗：{e}")
        return None
    except anthropic.APIError as e:
        print(f"  ⚠ Claude API 錯誤：{e}")
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
        else:
            print(f"  ❌ 存入失敗：{result.get('error')}")
            return False
    except Exception as e:
        print(f"  ❌ API 請求失敗：{e}")
        return False


def crawl_single_url(client: anthropic.Anthropic, url: str, source_name: str, prompt_template: str) -> bool:
    """手動爬取並分析單一 URL。"""
    print(f"\n📄 處理手動來源：{url}")
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


def run_auto_crawl(client: anthropic.Anthropic, sources: list, prompt_template: str, max_days: int = 7):
    """執行自動爬取所有 RSS 來源。"""
    total_saved = 0
    total_processed = 0

    for source in sources:
        print(f"\n🔍 爬取來源：{source['name']}")
        articles = fetch_rss_articles(source, max_days=max_days)

        if not articles:
            print(f"  ℹ 無新文章或無 RSS feed")
            continue

        print(f"  📰 找到 {len(articles)} 篇文章")

        for article in articles:
            total_processed += 1
            print(f"\n  📝 分析：{article['title'][:50]}...")

            # 抓取完整內文
            content = fetch_page_content(article["url"])
            if content:
                article["content"] = content

            result = analyze_article(client, article, prompt_template)
            if not result:
                continue

            # 只存入相關性分數 >= 5 的文章
            score = result.get("relevance_score", 0)
            if score < 5:
                print(f"  ⏭ 相關性不足 (分數: {score})，跳過")
                continue

            if post_to_sheets(result):
                total_saved += 1

            # 避免 API rate limit
            time.sleep(2)

    print(f"\n{'='*50}")
    print(f"✅ 爬取完成！處理 {total_processed} 篇文章，存入 {total_saved} 篇素材")


def main():
    """主程式進入點。"""
    if not ANTHROPIC_API_KEY:
        print("❌ 錯誤：請設定 ANTHROPIC_API_KEY 環境變數")
        print("   複製 .env.example 為 .env 並填入 API Key")
        sys.exit(1)

    if not APPS_SCRIPT_API_URL:
        print("❌ 錯誤：請設定 APPS_SCRIPT_API_URL 環境變數")
        sys.exit(1)

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    sources = load_sources()
    prompt_template = load_analysis_prompt()

    # 命令列參數處理
    if len(sys.argv) > 1:
        if sys.argv[1] == "--url" and len(sys.argv) > 2:
            # 手動模式：爬取單一 URL
            url = sys.argv[2]
            source_name = sys.argv[3] if len(sys.argv) > 3 else ""
            crawl_single_url(client, url, source_name, prompt_template)
        elif sys.argv[1] == "--days" and len(sys.argv) > 2:
            # 指定天數
            max_days = int(sys.argv[2])
            run_auto_crawl(client, sources["auto_crawl"], prompt_template, max_days=max_days)
        elif sys.argv[1] == "--help":
            print("用法：")
            print("  python crawl.py                  # 自動爬取所有 RSS 來源（最近7天）")
            print("  python crawl.py --days 14        # 自動爬取（最近14天）")
            print("  python crawl.py --url <URL>      # 手動爬取單一網址")
            print("  python crawl.py --url <URL> 來源名稱  # 手動爬取並指定來源名稱")
        else:
            print(f"未知參數：{sys.argv[1]}，使用 --help 查看用法")
    else:
        # 預設：自動爬取
        print("🚀 FB素材庫 — 自動爬取開始")
        print(f"⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        run_auto_crawl(client, sources["auto_crawl"], prompt_template)


if __name__ == "__main__":
    main()
