"""貼文紀錄頁面 — 查看歷史貼文、更新回饋。"""

import sys
from pathlib import Path

import streamlit as st

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.sheets_api import get_post_records, update_post_metrics, update_post_rating
from pages.auth import require_auth

st.set_page_config(page_title="貼文紀錄", page_icon="📋", layout="wide")
require_auth()
st.title("📋 貼文紀錄")

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

    # FB 成效摘要
    likes = r.get("likes", 0)
    comments = r.get("comments", 0)
    shares = r.get("shares", 0)
    has_fb = likes or comments or shares
    fb_summary = f"👍{likes} 💬{comments} 🔄{shares}" if has_fb else "尚無FB數據"

    with st.expander(f"{date} | {title} | {post_type} | {stars} | {fb_summary}"):
        # 貼文內容
        st.markdown("**貼文內容：**")
        st.text(r.get("post_content", "（無內容）"))

        if r.get("notes"):
            st.markdown(f"**備註：** {r['notes']}")

        st.divider()

        # 更新評分
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

        # 更新 FB 成效
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
