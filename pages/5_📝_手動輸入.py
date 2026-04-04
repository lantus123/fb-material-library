"""手動輸入頁面 — 手動加入素材 + 管理寫法範本。"""

import sys
from pathlib import Path

import streamlit as st

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.sheets_api import add_style_example, get_style_examples
from scripts.post_generator import get_client, GEMINI_MODEL
from pages.auth import require_auth

st.set_page_config(page_title="手動輸入", page_icon="📝", layout="wide")
require_auth()
st.title("📝 手動輸入")

tab1, tab2, tab3 = st.tabs(["📎 手動加入素材", "✨ 新增寫法範本", "📖 寫法範本庫"])

# ─── Tab 1：手動加入素材（貼 URL 讓 AI 分析）─────────────
with tab1:
    st.subheader("📎 手動加入素材")
    st.markdown("看到好文章？貼上網址，AI 會自動分析並存入素材庫。")

    url = st.text_input("文章網址", placeholder="https://...")
    source_name = st.text_input("來源名稱（選填）", placeholder="例：親子天下、PTT")

    if st.button("🔍 分析並加入素材庫", type="primary"):
        if not url:
            st.error("請輸入網址")
        else:
            with st.spinner("⏳ 正在爬取並分析文章..."):
                try:
                    # 直接用 crawl.py 的邏輯
                    from scripts.crawl import fetch_page_content, analyze_article, post_to_sheets, load_analysis_prompt
                    from google import genai
                    from scripts.sheets_api import _get_secret

                    content = fetch_page_content(url)
                    if not content:
                        st.error("⚠ 無法取得文章內容，請確認網址是否正確")
                    else:
                        article = {
                            "title": source_name or url,
                            "url": url,
                            "content": content,
                            "source_name": source_name or "手動輸入",
                        }
                        client = genai.Client(api_key=_get_secret("GEMINI_API_KEY"))
                        prompt_template = load_analysis_prompt()
                        result = analyze_article(client, article, prompt_template)

                        if result:
                            score = result.get("relevance_score", 0)
                            st.markdown(f"### 分析結果（相關性：{score}/10）")
                            st.markdown(f"**標題：** {result.get('title', '')}")
                            st.markdown(f"**摘要：** {result.get('summary', '')}")
                            st.markdown(f"**主題：** {', '.join(result.get('topics', []))}")

                            if score >= 5:
                                if post_to_sheets(result):
                                    st.success("✅ 已存入素材庫！")
                                else:
                                    st.error("❌ 存入失敗")
                            else:
                                st.warning(f"⚠ 相關性分數只有 {score}，低於 5 分門檻，未自動存入。")
                                if st.button("強制存入"):
                                    if post_to_sheets(result):
                                        st.success("✅ 已強制存入素材庫！")
                        else:
                            st.error("⚠ 分析失敗，請稍後再試")
                except Exception as e:
                    st.error(f"❌ 錯誤：{e}")

# ─── Tab 2：新增寫法範本 ─────────────────────────────────
with tab2:
    st.subheader("✨ 新增寫法範本")
    st.markdown("看到寫法很棒的貼文？存下來讓 AI 學習它的技巧。內容不需要跟教育相關。")

    style_title = st.text_input("標題", placeholder="例：某牙醫診所的互動貼文")
    style_content = st.text_area(
        "貼文內容",
        height=250,
        placeholder="把你覺得寫得好的貼文內容貼在這裡...",
    )
    style_highlights = st.text_area(
        "寫法亮點（你覺得哪裡寫得好？）",
        height=100,
        placeholder="例：開頭用問句引起共鳴、結尾的互動引導很自然、emoji 用得恰到好處",
    )
    style_url = st.text_input("來源連結（選填）", placeholder="FB 貼文網址或其他來源")
    style_tags = st.multiselect(
        "標籤",
        ["開頭吸引", "互動引導", "情感連結", "數據引用", "故事敘事", "幽默風趣", "排版漂亮", "簡潔有力"],
    )

    if st.button("💾 儲存寫法範本", type="primary"):
        if not style_content:
            st.error("請填入貼文內容")
        elif not style_highlights:
            st.error("請填寫寫法亮點，這是 AI 學習的重點")
        else:
            result = add_style_example(
                title=style_title or "未命名範本",
                content=style_content,
                highlights=style_highlights,
                source_url=style_url,
                tags=style_tags,
            )
            if result.get("success"):
                st.success(f"✅ 已儲存！（第 {result.get('row')} 筆）下次生成貼文時 AI 會參考這個寫法。")
            else:
                st.error(f"❌ 儲存失敗：{result.get('error')}")

# ─── Tab 3：寫法範本庫 ───────────────────────────────────
with tab3:
    st.subheader("📖 寫法範本庫")

    examples = get_style_examples(limit=20)

    if not examples:
        st.info("📭 還沒有寫法範本，去「新增寫法範本」頁籤加入第一個吧！")
    else:
        st.markdown(f"共 **{len(examples)}** 個範本")

        for ex in examples:
            tags_str = " ".join([f"`{t}`" for t in ex.get("tags", [])])
            date = str(ex.get("created_at", ""))[:10]

            with st.expander(f"{date} | {ex.get('title', '無標題')} | {tags_str}"):
                st.markdown(f"**寫法亮點：** {ex.get('highlights', '')}")
                st.divider()
                st.text(ex.get("content", ""))
                if ex.get("source_url"):
                    st.markdown(f"[來源連結]({ex['source_url']})")
