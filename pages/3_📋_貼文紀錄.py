"""貼文紀錄頁面 — 查看歷史貼文、更新回饋、分析修改差異。"""

import sys
from pathlib import Path

import streamlit as st

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.sheets_api import (
    get_post_records,
    update_post_metrics,
    update_post_rating,
    update_post_content,
    update_edit_reasons,
    update_edit_principle,
    revert_post_to_original,
)
from scripts.post_generator import analyze_edit_diff
from pages.auth import require_auth

st.set_page_config(page_title="貼文紀錄", page_icon="📋", layout="wide")
require_auth()
st.title("📋 貼文紀錄")

EDIT_REASON_OPTIONS = [
    "太長", "太短", "太學術", "太口語", "開頭弱", "結尾弱",
    "CTA不明", "語氣不對", "資訊錯誤", "結構鬆散",
    "emoji過多", "emoji不足", "hashtag不對", "蹭熱點非學習訊號",
]

records = get_post_records(limit=50)

if not records:
    st.info("📭 還沒有貼文紀錄，先去「貼文生成」頁面生成一篇吧！")
    st.stop()

st.markdown(f"共 **{len(records)}** 筆紀錄")

for r in records:
    row = r.get("row_number", "?")
    title = r.get("material_title", "無標題")
    post_type = r.get("post_type", "一般")
    rating = r.get("rating", 0)
    date = str(r.get("generated_at", ""))[:10]
    stars = "⭐" * int(rating) if rating else "未評分"

    likes = r.get("likes", 0)
    comments = r.get("comments", 0)
    shares = r.get("shares", 0)
    has_fb = likes or comments or shares
    fb_summary = f"👍{likes} 💬{comments} 🔄{shares}" if has_fb else "尚無FB數據"

    post_content = r.get("post_content", "")
    original_content = r.get("original_content", "")
    is_edited = bool(original_content) and original_content.strip() != post_content.strip()
    edit_marker = "✏️" if is_edited else ""

    with st.expander(f"{edit_marker} {date} | {title} | {post_type} | {stars} | {fb_summary}"):
        # 原版 / 編輯版 對照
        if is_edited:
            st.markdown("**📝 原版 vs 編輯版**")
            c_orig, c_edit = st.columns(2)
            with c_orig:
                st.caption("AI 原版")
                st.text_area(
                    "原版",
                    value=original_content,
                    height=220,
                    key=f"orig_{row}",
                    label_visibility="collapsed",
                    disabled=True,
                )
            with c_edit:
                st.caption("你的編輯版（可再修改）")
                edited_content = st.text_area(
                    "編輯版",
                    value=post_content,
                    height=220,
                    key=f"content_{row}",
                    label_visibility="collapsed",
                )
        else:
            st.markdown("**貼文內容：**（可直接修改，改好後點「更新貼文內容」）")
            edited_content = st.text_area(
                "貼文內容",
                value=post_content,
                height=220,
                key=f"content_{row}",
                label_visibility="collapsed",
            )

        # 儲存/退回/分析差異 按鈕列
        btn_col1, btn_col2, btn_col3 = st.columns(3)
        with btn_col1:
            if edited_content != post_content:
                if st.button("💾 更新貼文內容", key=f"update_content_{row}", type="primary"):
                    if update_post_content(row, edited_content):
                        st.success("✅ 已更新")
                        st.rerun()
                    else:
                        st.error("❌ 更新失敗")
        with btn_col2:
            if is_edited:
                if st.button("⟲ 退回原版", key=f"revert_{row}"):
                    if revert_post_to_original(row):
                        st.success("✅ 已退回原版")
                        st.rerun()
                    else:
                        st.error("❌ 退回失敗（原版為空）")
        with btn_col3:
            if is_edited:
                if st.button("🔍 分析差異並學習", key=f"analyze_{row}"):
                    with st.spinner("Gemini 分析中..."):
                        principle = analyze_edit_diff(
                            original=original_content,
                            edited=post_content,
                            reasons=r.get("edit_reasons", ""),
                        )
                        if principle and not principle.startswith("❌"):
                            update_edit_principle(row, principle)
                            st.success("✅ 已萃取原則")
                            st.rerun()
                        else:
                            st.error(principle or "❌ 分析失敗")

        # 修改原因標籤 + 已萃取原則
        if is_edited:
            existing_reasons = [
                x for x in (r.get("edit_reasons", "") or "").split("|") if x
            ]
            selected_reasons = st.multiselect(
                "修改原因（可選，幫助 AI 更精準學習；沒空就留空）",
                EDIT_REASON_OPTIONS,
                default=[x for x in existing_reasons if x in EDIT_REASON_OPTIONS],
                key=f"reasons_select_{row}",
            )
            new_reasons_str = "|".join(selected_reasons)
            if new_reasons_str != (r.get("edit_reasons", "") or ""):
                if st.button("💾 儲存修改原因", key=f"save_reasons_{row}"):
                    if update_edit_reasons(row, new_reasons_str):
                        st.success("✅ 原因已儲存")
                        st.rerun()

            principle = r.get("edit_principle", "")
            if principle:
                st.info(f"🧠 **已萃取原則：**\n\n{principle}")

        if r.get("notes"):
            st.markdown(f"**備註：** {r['notes']}")

        st.divider()

        # 更新評分 + FB 成效
        col1, col2 = st.columns(2)
        with col1:
            st.markdown("**更新評分**")
            new_rating = st.slider(
                "評分", 1, 5, int(rating) if rating else 3,
                key=f"rating_{row}"
            )
            new_notes = st.text_input(
                "備註", value=r.get("notes", ""),
                key=f"notes_{row}"
            )
            if st.button("更新評分", key=f"update_rating_{row}"):
                if update_post_rating(row, new_rating, new_notes):
                    st.success("✅ 評分已更新")
                    st.rerun()
                else:
                    st.error("❌ 更新失敗")

        with col2:
            st.markdown("**更新 FB 成效**")
            fb_post_id = st.text_input(
                "FB 貼文 ID 或 URL",
                value=r.get("fb_post_id", ""),
                key=f"fb_id_{row}",
                placeholder="貼上 FB 貼文網址",
            )
            c1, c2 = st.columns(2)
            with c1:
                new_likes = st.number_input("按讚", value=int(likes), min_value=0, key=f"likes_{row}")
                new_shares = st.number_input("分享", value=int(shares), min_value=0, key=f"shares_{row}")
            with c2:
                new_comments = st.number_input("留言", value=int(comments), min_value=0, key=f"comments_{row}")
                new_reach = st.number_input("觸及", value=int(r.get("reach", 0)), min_value=0, key=f"reach_{row}")

            if st.button("更新 FB 成效", key=f"update_fb_{row}"):
                if update_post_metrics(
                    row=row,
                    fb_post_id=fb_post_id,
                    likes=new_likes,
                    comments=new_comments,
                    shares=new_shares,
                    reach=new_reach,
                ):
                    st.success("✅ FB 成效已更新")
                    st.rerun()
                else:
                    st.error("❌ 更新失敗")
