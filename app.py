"""
FB素材庫 — Streamlit Web UI 入口
優見補習班 Facebook 內容素材管理系統
"""

import streamlit as st

st.set_page_config(
    page_title="優見補習班 FB素材庫",
    page_icon="📚",
    layout="wide",
)


def check_password() -> bool:
    """密碼驗證。"""
    if st.session_state.get("authenticated"):
        return True

    st.title("🔒 優見補習班 FB素材庫")
    password = st.text_input("請輸入密碼", type="password")
    if st.button("登入", type="primary"):
        if password == st.secrets.get("password", ""):
            st.session_state["authenticated"] = True
            st.rerun()
        else:
            st.error("❌ 密碼錯誤")
    return False


if not check_password():
    st.stop()

st.title("📚 優見補習班 FB素材庫")
st.markdown("自動蒐集教育文章、AI 分析篩選、一鍵生成 FB 貼文。")

st.divider()

# 檢查 API 連線狀態
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.sheets_api import get_stats

try:
    stats = get_stats()
    if stats.get("error"):
        st.error(f"⚠ Google Sheets 連線異常：{stats['error']}")
    else:
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("素材總數", stats.get("total", 0))
        col2.metric("本週新增", stats.get("thisWeek", 0))
        col3.metric("高相關性", stats.get("highRelevance", 0))
        col4.metric("最後更新", str(stats.get("lastUpdated", "N/A"))[:10])

        by_topic = stats.get("byTopic", {})
        if by_topic:
            st.subheader("各主題分佈")
            st.bar_chart(by_topic)
except Exception as e:
    st.error(f"❌ 無法連線到 Google Sheets：{e}")

st.divider()
st.markdown(
    "👈 使用左側選單切換頁面：素材庫瀏覽、貼文生成、貼文紀錄、統計儀表板"
)
