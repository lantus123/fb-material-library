"""
FB素材庫 — 貼文生成核心模組
組裝 prompt（含回饋範例注入）並呼叫 Gemini 生成貼文。
"""

import json
import os
from pathlib import Path

from google import genai
from dotenv import load_dotenv

from scripts.sheets_api import get_top_posts

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
COPYWRITING_PROMPT_PATH = PROJECT_ROOT / "prompts" / "copywriting.md"
BRAND_PATH = PROJECT_ROOT / "config" / "brand.json"


def get_client() -> genai.Client:
    """取得 Gemini client。"""
    return genai.Client(api_key=GEMINI_API_KEY)


def load_copywriting_prompt() -> str:
    """載入貼文生成 prompt 模板。"""
    with open(COPYWRITING_PROMPT_PATH, "r", encoding="utf-8") as f:
        return f.read()


def load_brand() -> dict:
    """載入品牌設定。"""
    with open(BRAND_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def _format_top_posts(top_posts: list[dict]) -> str:
    """將高效能貼文格式化為 few-shot 範例。"""
    if not top_posts:
        return ""

    sections = []
    for i, post in enumerate(top_posts, 1):
        metrics = []
        if post.get("likes"):
            metrics.append(f"按讚：{post['likes']}")
        if post.get("comments"):
            metrics.append(f"留言：{post['comments']}")
        if post.get("shares"):
            metrics.append(f"分享：{post['shares']}")
        metrics_str = "、".join(metrics) if metrics else "尚無數據"

        content = post.get("post_content", "")[:300]
        if len(post.get("post_content", "")) > 300:
            content += "..."

        sections.append(
            f"### 參考貼文 {i}（類型：{post.get('post_type', '一般')}，"
            f"評分：{post.get('rating', 0)}/5，{metrics_str}）\n{content}"
        )

    return "\n\n".join(sections)


def build_prompt(
    material: dict,
    post_type: str = "",
    top_posts: list[dict] | None = None,
) -> str:
    """組裝完整的貼文生成 prompt，含回饋範例注入。"""
    template = load_copywriting_prompt()

    # 替換素材資料
    prompt = template.replace("{{title}}", material.get("title", ""))
    prompt = prompt.replace("{{summary}}", material.get("summary", ""))
    prompt = prompt.replace("{{topics}}", ", ".join(material.get("topics", [])))
    prompt = prompt.replace("{{angles}}", " | ".join(material.get("angles", [])))
    prompt = prompt.replace("{{key_facts}}", " | ".join(material.get("key_facts", [])))
    prompt = prompt.replace("{{source_title}}", material.get("source_title", ""))
    prompt = prompt.replace("{{post_type}}", post_type)

    # 注入高效能貼文範例
    if top_posts is None:
        try:
            top_posts = get_top_posts(limit=3)
        except Exception:
            top_posts = []

    top_posts_text = _format_top_posts(top_posts)
    if top_posts_text:
        prompt = prompt.replace(
            "{{top_posts}}",
            top_posts_text,
        )
    else:
        # 移除整個 top_posts 條件區塊
        import re
        prompt = re.sub(
            r'\{\{#if top_posts\}\}.*?\{\{/if\}\}',
            '',
            prompt,
            flags=re.DOTALL,
        )

    return prompt


def generate_post(
    client: genai.Client,
    material: dict,
    post_type: str = "",
    top_posts: list[dict] | None = None,
) -> str:
    """生成 FB 貼文。回傳生成的貼文文字。"""
    prompt = build_prompt(material, post_type, top_posts)

    try:
        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=prompt,
        )
        return response.text
    except Exception as e:
        return f"❌ Gemini API 錯誤：{e}"
