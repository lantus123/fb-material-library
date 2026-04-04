"""貼文生成頁面 — 選素材、生成、編輯、評分、儲存。"""

import sys
from pathlib import Path

import streamlit as st

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.sheets_api import get_materials, mark_used, add_post_record
from scripts.post_generator import get_client, generate_post
from pages.auth import require_auth

st.set_page_config(page_title="貼文生成", page_icon="✏️", layout="wide")
require_auth()
st.title("✏️ 貼文生成")

# 初始化 session state
if "generated_post" not in st.session_state:
    st.session_state["generated_post"] = ""
if "selected_material" not in st.session_state:
    st.session_state["selected_material"] = None

# ─── 左欄：素材選擇 ─────────────────────────────────────
left, right = st.columns([1, 1])

with left:
    st.subheader("📄 選擇素材")

    material = st.session_state.get("selected_material")

    if not material:
        # 讓使用者從下拉選單選素材
        materials = get_materials(limit=20)
        unused = [m for m in materials if not m.get("used")]
        available = unused if unused else materials

        if not available:
            st.info("📭 沒有可用素材")
            st.stop()

        options = {
            f"[{m.get('relevance_score', 0)}分] {m.get('title', '無標題')}": m
            for m in available
        }
        selected_key = st.selectbox("選擇素材", list(options.keys()))
        material = options[selected_key]
        st.session_state["selected_material"] = material

    # 顯示素材詳情
    st.markdown(f"### {material.get('title', '無標題')}")
    st.markdown(f"**來源：** {material.get('source_title', '')}")
    st.markdown(f"**相關性：** {material.get('relevance_score', 0)}/10")
    st.markdown(f"**主題：** {', '.join(material.get('topics', []))}")
    st.markdown(f"**摘要：** {material.get('summary', '')}")

    if material.get("angles"):
        st.markdown("**可用角度：**")
        for angle in material["angles"]:
            st.markdown(f"- {angle}")

    if st.button("🔄 重新選擇素材"):
        st.session_state["selected_material"] = None
        st.session_state["generated_post"] = ""
        st.rerun()

# ─── 右欄：生成與編輯 ───────────────────────────────────
with right:
    st.subheader("📱 生成貼文")

    # 貼文類型
    post_type = st.radio(
        "貼文類型",
        ["一般 (200-400字)", "短文 (150字以內)", "長文 (深入分析)", "互動 (投票/問答)", "知識 (科普/教學)"],
        horizontal=True,
    )
    type_map = {
        "一般 (200-400字)": "一般",
        "短文 (150字以內)": "短文",
        "長文 (深入分析)": "長文",
        "互動 (投票/問答)": "互動",
        "知識 (科普/教學)": "知識",
    }
    post_type_value = type_map[post_type]

    # 生成按鈕
    col_gen, col_regen = st.columns(2)
    with col_gen:
        if st.button("🚀 生成貼文", type="primary", use_container_width=True):
            with st.spinner("⏳ AI 正在生成貼文..."):
                client = get_client()
                result = generate_post(client, material, post_type_value)
                st.session_state["generated_post"] = result
    with col_regen:
        if st.button("🔄 重新生成", use_container_width=True):
            with st.spinner("⏳ 重新生成中..."):
                client = get_client()
                result = generate_post(client, material, post_type_value)
                st.session_state["generated_post"] = result

    # 顯示 / 編輯貼文
    post_content = st.text_area(
        "貼文內容（可直接編輯）",
        value=st.session_state.get("generated_post", ""),
        height=400,
        placeholder="點擊「生成貼文」開始...",
    )

    if post_content:
        # 複製提示
        st.code(post_content, language=None)
        st.caption("👆 點擊右上角複製按鈕即可複製貼文")

        st.divider()

        # 評分與儲存
        st.subheader("⭐ 評分與儲存")
        rating = st.slider("主觀評分", 1, 5, 3, help="1=很差 5=很好")
        notes = st.text_input("備註（哪裡好/不好）", placeholder="例：開頭很吸引人，但結尾太制式")

        if st.button("💾 儲存到貼文紀錄", type="primary", use_container_width=True):
            result = add_post_record(
                material_title=material.get("title", ""),
                material_row=material.get("row_number", 0),
                post_type=post_type_value,
                post_content=post_content,
                rating=rating,
                notes=notes,
            )
            if result.get("success"):
                # 標記素材為已使用
                if material.get("row_number"):
                    mark_used(material["row_number"])
                st.success(f"✅ 已儲存！（第 {result.get('row')} 列）素材已標記為已使用。")
                st.session_state["selected_material"] = None
                st.session_state["generated_post"] = ""
            else:
                st.error(f"❌ 儲存失敗：{result.get('error')}")
