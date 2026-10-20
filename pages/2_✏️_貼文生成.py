"""貼文生成頁面 — 選素材、生成、編輯、評分、儲存。支援單篇或多篇素材組合。"""

import sys
from pathlib import Path

import streamlit as st

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.sheets_api import get_materials, mark_used, add_post_record
from scripts.post_generator import get_client, generate_post
from scripts.publish_ui import render_publish_panel
from pages.auth import require_auth

st.set_page_config(page_title="貼文生成", page_icon="✏️", layout="wide")
require_auth()
st.title("✏️ 貼文生成")

# 初始化 session state
if "generated_post" not in st.session_state:
    st.session_state["generated_post"] = ""
if "selected_materials" not in st.session_state:
    st.session_state["selected_materials"] = []


def render_last_saved():
    row = st.session_state.get("last_saved_row")
    if row:
        with st.expander("📤 發布到粉專", expanded=True):
            st.caption(f"已儲存的貼文紀錄：第 {row} 列")
            render_publish_panel(
                row, st.session_state.get("last_saved_content", ""), key_prefix=f"gen_{row}",
            )


# ─── 左欄：素材選擇 ─────────────────────────────────────
left, right = st.columns([1, 1])

with left:
    st.subheader("📄 選擇素材")

    # 從素材庫瀏覽頁面帶過來的單篇素材
    if st.session_state.get("selected_material") and not st.session_state["selected_materials"]:
        st.session_state["selected_materials"] = [st.session_state["selected_material"]]
        st.session_state["selected_material"] = None

    # 取得所有素材
    all_materials = get_materials(limit=30)
    unused = [m for m in all_materials if not m.get("used")]
    available = unused if unused else all_materials

    if not available:
        st.info("📭 ��有可用素材")
        render_last_saved()
        st.stop()

    # 多選素材
    options_map = {
        f"[{m.get('relevance_score', 0)}分] {m.get('title', '無標題')}": m
        for m in available
    }

    # 預設選項（如果已有選擇）
    default_keys = []
    for sm in st.session_state.get("selected_materials", []):
        for key, m in options_map.items():
            if m.get("row_number") == sm.get("row_number"):
                default_keys.append(key)
                break

    selected_keys = st.multiselect(
        "選擇素材（可多選來組合）",
        list(options_map.keys()),
        default=default_keys,
        help="選擇 1 篇為單篇模式，選 2-3 篇會自動融合觀點",
    )

    selected_materials = [options_map[k] for k in selected_keys]
    st.session_state["selected_materials"] = selected_materials

    if not selected_materials:
        st.info("👆 請選擇至少一篇素材")
        render_last_saved()
        st.stop()

    # 顯示已選素材
    if len(selected_materials) > 1:
        st.success(f"🔗 已選 {len(selected_materials)} 篇素材，將融合生成")

    for i, m in enumerate(selected_materials):
        with st.container(border=True):
            st.markdown(f"**素材 {i+1}：** {m.get('title', '無標題')}")
            st.caption(
                f"來源：{m.get('source_title', '')} | "
                f"分數：{m.get('relevance_score', 0)}/10 | "
                f"主題：{', '.join(m.get('topics', []))}"
            )
            st.markdown(f"{m.get('summary', '')[:100]}...")

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
    material_input = selected_materials if len(selected_materials) > 1 else selected_materials[0]

    col_gen, col_regen = st.columns(2)
    with col_gen:
        if st.button("🚀 生成貼文", type="primary", use_container_width=True):
            with st.spinner("⏳ AI 正在生成貼文..."):
                client = get_client()
                result = generate_post(client, material_input, post_type_value)
                st.session_state["generated_post"] = result
    with col_regen:
        if st.button("🔄 重新生成", use_container_width=True):
            with st.spinner("⏳ 重新生成中..."):
                client = get_client()
                result = generate_post(client, material_input, post_type_value)
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
            # 組合素材標題
            titles = [m.get("title", "") for m in selected_materials]
            combined_title = " + ".join(titles) if len(titles) > 1 else titles[0]
            first_row = selected_materials[0].get("row_number", 0)

            result = add_post_record(
                material_title=combined_title,
                material_row=first_row,
                post_type=post_type_value,
                post_content=post_content,
                rating=rating,
                notes=notes,
            )
            if result.get("success"):
                st.session_state["last_saved_row"] = result["row"]
                st.session_state["last_saved_content"] = post_content
                # 標記所有素材為已使用
                for m in selected_materials:
                    if m.get("row_number"):
                        mark_used(m["row_number"])
                st.success(
                    f"✅ 已儲存！（第 {result.get('row')} 列）"
                    f"{len(selected_materials)} 篇素材已標記為已使用。"
                )
                st.session_state["selected_materials"] = []
                st.session_state["generated_post"] = ""
            else:
                st.error(f"❌ 儲存失敗：{result.get('error')}")

    render_last_saved()
