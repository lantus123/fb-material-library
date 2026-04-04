"""共用密碼驗證模組。"""

import streamlit as st


def require_auth():
    """檢查是否已驗證，未驗證則停止頁面。"""
    if not st.session_state.get("authenticated"):
        st.warning("🔒 請先從首頁登入")
        st.stop()
