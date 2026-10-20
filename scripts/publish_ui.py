"""生成頁與紀錄頁共用的人工確認發布介面。"""

import hashlib
import tempfile
from datetime import datetime, time, timedelta
from pathlib import Path

import streamlit as st

from scripts.fb_api import TAIPEI, is_configured, publish_record, redact_token


def _show_result(result: dict) -> None:
    status = "已排程" if result["status"] == "scheduled" else "已發布"
    st.success(redact_token(
        f"{status}：[查看 FB 貼文](https://www.facebook.com/{result['post_id']})"
    ))
    if result.get("sheet_error"):
        st.warning(redact_token(
            f"已發布／排程但紀錄沒更新，貼文 ID 是 {result['post_id']}，"
            f"請人工補登，勿重複發布。{result['sheet_error']}"
        ))


def render_publish_panel(row: int, post_content: str, key_prefix: str) -> None:
    if not is_configured():
        st.info("尚未設定 FB_PAGE_ID／FB_PAGE_ACCESS_TOKEN，請到 Streamlit secrets 或 .env 設定")
        return
    # 同一 session 的兩個入口共用結果，Sheet 寫入失敗也不再顯示發布按鈕。
    result_key = f"publish_result_{row}"
    if result_key in st.session_state:
        _show_result(st.session_state[result_key])
        return
    mode = st.radio("發布方式", ["立即發布", "排程發布"], key=f"{key_prefix}_mode")
    scheduled_at = None
    if mode == "排程發布":
        day = st.date_input(
            "排程日期（台北）", value=(datetime.now(TAIPEI) + timedelta(days=1)).date(),
            key=f"{key_prefix}_date",
        )
        at = st.time_input("排程時間（台北）", value=time(20), key=f"{key_prefix}_time")
        scheduled_at = datetime.combine(day, at, tzinfo=TAIPEI)
    upload = st.file_uploader(
        "附一張圖（選填）", type=["jpg", "jpeg", "png"], key=f"{key_prefix}_image",
    )
    image_bytes = upload.getvalue() if upload is not None else b""
    # 內容、圖片或時間改變後，必須重新勾選確認。
    digest = hashlib.sha256(
        post_content.encode() + str(scheduled_at).encode() + image_bytes
    ).hexdigest()[:16]
    st.text_area(
        "發布內容預覽", value=redact_token(post_content), disabled=True,
        key=f"{key_prefix}_preview_{digest}",
    )
    checked = st.checkbox("我已看過內容，確認發布", key=f"{key_prefix}_confirm_{digest}")
    if st.button("📤 發布到粉專", disabled=not checked, key=f"{key_prefix}_publish") and checked:
        temp_path = None
        try:
            if upload is not None:
                suffix = Path(upload.name).suffix.lower()
                if suffix not in {".jpg", ".jpeg", ".png"}:
                    raise ValueError("圖片格式必須為 jpg、jpeg 或 png")
                with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as fh:
                    temp_path = fh.name
                    fh.write(image_bytes)
            result = publish_record(
                row, scheduled_at=scheduled_at, image_path=temp_path,
                expected_content=post_content,
            )
            st.session_state[result_key] = result
            # 清掉舊成效欄位 widget 值，下一次載入改用發布後的 ID。
            st.session_state.pop(f"fb_id_{row}", None)
            st.rerun()
        except Exception as exc:
            st.error(redact_token(str(exc)))
        finally:
            if temp_path:
                try:
                    Path(temp_path).unlink(missing_ok=True)
                except OSError as exc:
                    st.error(redact_token(f"暫存圖片清理失敗：{exc}"))
