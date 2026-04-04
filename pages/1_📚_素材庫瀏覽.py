"""素材庫瀏覽頁面 — 查看和篩選素材。"""

import sys
from pathlib import Path

import streamlit as st

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.sheets_api import get_materials
from pages.auth import require_auth

st.set_page_config(page_title="素材庫瀏覽", page_icon="📚", layout="wide")
require_auth()
st.title("📚 素材庫瀏覽")

# 篩選器
col1, col2 = st.columns([1, 1])
with col1:
    topic_filter = st.selectbox(
        "主題篩選",
        ["全部", "升學資訊", "親子教養", "學習方法", "教育政策趨勢", "在地學區資訊"],
    )
with col2:
    limit = st.slider("顯示筆數", 5, 50, 20)

# 取得素材
topic = None if topic_filter == "全部" else topic_filter
materials = get_materials(topic=topic, limit=limit)

if not materials:
    st.info("📭 目前沒有素材，請先執行爬取。")
else:
    # 篩選按鈕
    show_unused_only = st.checkbox("只顯示未使用的素材", value=True)
    if show_unused_only:
        materials = [m for m in materials if not m.get("used")]

    st.markdown(f"共 **{len(materials)}** 筆素材")

    for m in materials:
        used_badge = "✅ 已使用" if m.get("used") else "🆕 未使用"
        score = m.get("relevance_score", 0)
        topics_str = ", ".join(m.get("topics", []))

        with st.expander(
            f"[{score}分] {m.get('title', '無標題')} — {used_badge}"
        ):
            st.markdown(f"**主題：** {topics_str}")
            st.markdown(f"**摘要：** {m.get('summary', '')}")
            st.markdown(f"**來源：** {m.get('source_title', '')} | [原文連結]({m.get('source_url', '')})")

            if m.get("angles"):
                st.markdown("**可用角度：**")
                for angle in m["angles"]:
                    st.markdown(f"- {angle}")

            if m.get("key_facts"):
                st.markdown("**關鍵事實：**")
                for fact in m["key_facts"]:
                    st.markdown(f"- {fact}")

            st.markdown(f"**相關性原因：** {m.get('relevance_reason', '')}")

            # 用這篇生成貼文
            if st.button("✏️ 用這篇生成貼文", key=f"gen_{m.get('row_number')}"):
                st.session_state["selected_material"] = m
                st.switch_page("pages/2_✏️_貼文生成.py")
