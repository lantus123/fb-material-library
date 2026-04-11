"""
FB素材庫 — 貼文生成核心模組
組裝 prompt（含回饋範例注入）並呼叫 Gemini 生成貼文。
"""

import json
import os
import re
from pathlib import Path

from google import genai
from dotenv import load_dotenv

from scripts.sheets_api import (
    _get_secret,
    get_top_posts,
    get_style_examples,
    get_active_principles,
    add_principle,
    delete_principles_by_source,
    bump_principles_usage,
    MIN_PRINCIPLES_FOR_INJECTION,
    MAX_PRINCIPLES_IN_PROMPT,
)

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

GEMINI_API_KEY = _get_secret("GEMINI_API_KEY")
GEMINI_MODEL = _get_secret("GEMINI_MODEL", "gemini-2.5-flash")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
COPYWRITING_PROMPT_PATH = PROJECT_ROOT / "prompts" / "copywriting.md"
DIFF_ANALYSIS_PROMPT_PATH = PROJECT_ROOT / "prompts" / "diff_analysis.md"
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
    """將高效能貼文格式化為 few-shot 範例。若有編輯版則顯示 A/B 對照。"""
    if not top_posts:
        return ""

    def _truncate(text: str, n: int = 300) -> str:
        return text[:n] + ("..." if len(text) > n else "")

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

        header = (
            f"### 參考貼文 {i}（類型：{post.get('post_type', '一般')}，"
            f"評分：{post.get('rating', 0)}/5，{metrics_str}）"
        )

        edited = post.get("post_content", "")
        original = post.get("original_content", "")
        if original and original.strip() != edited.strip():
            section = (
                f"{header}\n\n"
                f"**AI 初版（修改前，❌ 不要模仿）：**\n{_truncate(original)}\n\n"
                f"**最終版（人類編輯後，✅ 請學習這種修改方向）：**\n{_truncate(edited)}"
            )
        else:
            section = f"{header}\n{_truncate(edited)}"
        sections.append(section)

    return "\n\n".join(sections)


def _format_principles(principles: list[dict]) -> str:
    """將原則清單格式化為 prompt 文字。"""
    if not principles:
        return ""
    lines = []
    for p in principles:
        marker = "✅" if "正" in (p.get("type") or "") else "❌"
        topic_tag = f"（{p['topic']}）" if p.get("topic") else ""
        lines.append(
            f"- {marker}{topic_tag} {p.get('principle','').strip()}"
            + (f" — {p.get('reason','').strip()}" if p.get("reason") else "")
        )
    return "\n".join(lines)


_PRINCIPLE_TYPE_RE = re.compile(r"【類型】\s*(.+?)(?:\n|$)")
_PRINCIPLE_TEXT_RE = re.compile(r"【原則】\s*(.+?)(?:\n|$)")
_PRINCIPLE_REASON_RE = re.compile(r"【理由】\s*(.+?)(?:\n|$)")


def _parse_diff_result(raw: str) -> dict | None:
    """解析 diff_analysis 輸出；無顯著差異回傳 None。"""
    if not raw or "【無顯著差異】" in raw:
        return None
    t = _PRINCIPLE_TYPE_RE.search(raw)
    p = _PRINCIPLE_TEXT_RE.search(raw)
    r = _PRINCIPLE_REASON_RE.search(raw)
    if not (t and p):
        return None
    raw_type = t.group(1).strip()
    principle_type = "正向" if "正" in raw_type else ("負向" if "負" in raw_type else raw_type)
    return {
        "type": principle_type,
        "principle": p.group(1).strip(),
        "reason": r.group(1).strip() if r else "",
    }


def _format_style_examples(examples: list[dict]) -> str:
    """將寫法範本格式化為 prompt 內容。"""
    if not examples:
        return ""

    sections = []
    for i, ex in enumerate(examples, 1):
        content = ex.get("content", "")[:300]
        if len(ex.get("content", "")) > 300:
            content += "..."
        sections.append(
            f"### 範本 {i}：{ex.get('title', '無標題')}\n"
            f"**寫法亮點：** {ex.get('highlights', '')}\n"
            f"**內容：**\n{content}"
        )

    return "\n\n".join(sections)


def _format_materials(materials: list[dict]) -> str:
    """將多篇素材格式化為 prompt 內容。"""
    sections = []
    for i, m in enumerate(materials, 1):
        sections.append(
            f"### 素材 {i}\n"
            f"- **標題**: {m.get('title', '')}\n"
            f"- **摘要**: {m.get('summary', '')}\n"
            f"- **主題標籤**: {', '.join(m.get('topics', []))}\n"
            f"- **可用角度**: {' | '.join(m.get('angles', []))}\n"
            f"- **關鍵事實**: {' | '.join(m.get('key_facts', []))}\n"
            f"- **來源**: {m.get('source_title', '')}"
        )
    return "\n\n".join(sections)


def build_prompt(
    material: dict | list[dict],
    post_type: str = "",
    top_posts: list[dict] | None = None,
    return_used_principles: bool = False,
) -> str | tuple[str, list[int]]:
    """組裝完整的貼文生成 prompt，含回饋範例注入。支援單篇或多篇素材。

    若 return_used_principles=True，回傳 (prompt, 實際被注入的原則列號 list)，
    供呼叫端在生成成功後呼叫 bump_principles_usage 更新使用次數。
    """
    template = load_copywriting_prompt()

    # 判斷是單篇還是多篇
    if isinstance(material, list):
        materials = material
    else:
        materials = [material]

    if len(materials) == 1:
        m = materials[0]
        prompt = template.replace("{{title}}", m.get("title", ""))
        prompt = prompt.replace("{{summary}}", m.get("summary", ""))
        prompt = prompt.replace("{{topics}}", ", ".join(m.get("topics", [])))
        prompt = prompt.replace("{{angles}}", " | ".join(m.get("angles", [])))
        prompt = prompt.replace("{{key_facts}}", " | ".join(m.get("key_facts", [])))
        prompt = prompt.replace("{{source_title}}", m.get("source_title", ""))
        # 移除多素材區塊
        import re
        prompt = re.sub(
            r'\{\{#if combined\}\}.*?\{\{/if combined\}\}',
            '',
            prompt,
            flags=re.DOTALL,
        )
    else:
        # 多篇素材模式：替換為組合內容
        all_topics = set()
        all_angles = []
        all_facts = []
        titles = []
        sources = []
        for m in materials:
            titles.append(m.get("title", ""))
            sources.append(m.get("source_title", ""))
            all_topics.update(m.get("topics", []))
            all_angles.extend(m.get("angles", []))
            all_facts.extend(m.get("key_facts", []))

        prompt = template.replace("{{title}}", " + ".join(titles))
        prompt = prompt.replace("{{summary}}", "（多篇素材組合，詳見下方）")
        prompt = prompt.replace("{{topics}}", ", ".join(all_topics))
        prompt = prompt.replace("{{angles}}", " | ".join(all_angles))
        prompt = prompt.replace("{{key_facts}}", " | ".join(all_facts))
        prompt = prompt.replace("{{source_title}}", ", ".join(sources))
        prompt = prompt.replace("{{combined_materials}}", _format_materials(materials))
        # 保留多素材區塊內容，移除標記
        import re
        prompt = re.sub(r'\{\{#if combined\}\}', '', prompt)
        prompt = re.sub(r'\{\{/if combined\}\}', '', prompt)

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

    # 注入寫法範本
    try:
        style_examples = get_style_examples(limit=3)
    except Exception:
        style_examples = []

    if style_examples:
        style_text = _format_style_examples(style_examples)
        prompt = prompt.replace("{{style_examples}}", style_text)
    else:
        import re
        prompt = re.sub(
            r'\{\{#if style_examples\}\}.*?\{\{/if style_examples\}\}',
            '',
            prompt,
            flags=re.DOTALL,
        )

    # 注入修改原則庫（階段 2）
    used_principle_rows: list[int] = []
    try:
        principles = get_active_principles(
            topic=post_type or None,
            limit=MAX_PRINCIPLES_IN_PROMPT,
        )
    except Exception:
        principles = []

    if len(principles) >= MIN_PRINCIPLES_FOR_INJECTION:
        principles_text = _format_principles(principles)
        prompt = prompt.replace("{{principles}}", principles_text)
        used_principle_rows = [p["row_number"] for p in principles]
    else:
        import re
        prompt = re.sub(
            r'\{\{#if principles\}\}.*?\{\{/if principles\}\}',
            '',
            prompt,
            flags=re.DOTALL,
        )

    if return_used_principles:
        return prompt, used_principle_rows
    return prompt


def generate_post(
    client: genai.Client,
    material: dict | list[dict],
    post_type: str = "",
    top_posts: list[dict] | None = None,
) -> str:
    """生成 FB 貼文。支援單篇或多篇素材。回傳生成的貼文文字。

    生成成功後會自動 bump 被注入的原則使用次數，形成閉環。
    """
    prompt, used_principle_rows = build_prompt(
        material, post_type, top_posts, return_used_principles=True
    )

    try:
        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=prompt,
        )
        text = response.text
        if used_principle_rows:
            try:
                bump_principles_usage(used_principle_rows)
            except Exception:
                pass  # bump 失敗不影響主要生成流程
        return text
    except Exception as e:
        return f"❌ Gemini API 錯誤：{e}"


def analyze_edit_diff(
    original: str,
    edited: str,
    reasons: str = "",
    source_post_row: int | None = None,
    post_type: str = "",
) -> str:
    """比對原版與編輯版，萃取一條修改原則並寫入原則庫。

    回傳 Gemini 原始輸出（供貼文紀錄頁面顯示）。若解析成功且提供 source_post_row，
    會先清除該來源的既有原則再寫入新的，避免重複累積。
    """
    if not original or not edited:
        return "【無顯著差異】（缺少原版或編輯版）"
    if original.strip() == edited.strip():
        return "【無顯著差異】"

    template = DIFF_ANALYSIS_PROMPT_PATH.read_text(encoding="utf-8")
    prompt = (
        template
        .replace("{{original}}", original)
        .replace("{{edited}}", edited)
        .replace("{{reasons}}", reasons.strip() or "（未標註）")
    )

    try:
        client = get_client()
        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=prompt,
        )
        raw = (response.text or "").strip()
    except Exception as e:
        return f"❌ Gemini API 錯誤：{e}"

    parsed = _parse_diff_result(raw)
    if parsed and source_post_row is not None:
        try:
            delete_principles_by_source(source_post_row)
            add_principle(
                principle_type=parsed["type"],
                principle=parsed["principle"],
                reason=parsed["reason"],
                source_post_row=source_post_row,
                topic=post_type,
            )
        except Exception:
            pass  # 寫入原則庫失敗不影響回傳結果

    return raw
