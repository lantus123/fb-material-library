"""原則庫頁面 — 管理從貼文修改累積出的修改原則。"""

import sys
from pathlib import Path

import streamlit as st

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.sheets_api import (
    get_all_principles,
    add_principle,
    update_principle,
    set_principle_status,
    delete_principle,
    apply_principle_decay,
    MIN_PRINCIPLES_FOR_INJECTION,
    MAX_PRINCIPLES_IN_PROMPT,
    PRINCIPLE_DECAY_DAYS,
)
from pages.auth import require_auth

st.set_page_config(page_title="原則庫", page_icon="🧠", layout="wide")
require_auth()
st.title("🧠 修改原則庫")

st.caption(
    f"從貼文修改累積的原則，會被自動注入下次生成的 prompt。"
    f"冷啟動門檻：啟用中原則 ≥ {MIN_PRINCIPLES_FOR_INJECTION} 條才注入；"
    f"每次最多注入 {MAX_PRINCIPLES_IN_PROMPT} 條；"
    f"超過 {PRINCIPLE_DECAY_DAYS} 天未使用的自動歸檔。"
)

tab_browse, tab_add, tab_maintain = st.tabs(["📖 瀏覽 / 管理", "➕ 手動新增", "🛠️ 維護"])

# ─── Tab 1：瀏覽 / 管理 ───────────────────────────────
with tab_browse:
    principles = get_all_principles()

    if not principles:
        st.info("📭 原則庫是空的。開始修改貼文並按「🔍 分析差異並學習」後，原則會自動累積到這裡。")
    else:
        # 篩選
        c1, c2, c3 = st.columns(3)
        with c1:
            status_filter = st.selectbox(
                "狀態", ["active", "全部", "disabled", "archived"], index=0,
                key="p_status_filter",
            )
        with c2:
            type_filter = st.selectbox(
                "類型", ["全部", "正向", "負向"], index=0,
                key="p_type_filter",
            )
        with c3:
            topics = sorted({p["topic"] for p in principles if p["topic"]})
            topic_options = ["全部"] + topics + ["(無主題)"]
            topic_filter = st.selectbox("主題", topic_options, index=0, key="p_topic_filter")

        filtered = []
        for p in principles:
            if status_filter != "全部" and p["status"] != status_filter:
                continue
            if type_filter != "全部" and type_filter not in p["type"]:
                continue
            if topic_filter == "(無主題)":
                if p["topic"]:
                    continue
            elif topic_filter != "全部" and p["topic"] != topic_filter:
                continue
            filtered.append(p)

        st.markdown(f"共 **{len(filtered)}** 條（原則庫總數 {len(principles)}）")

        active_count = sum(1 for p in principles if p["status"] == "active")
        can_inject = active_count >= MIN_PRINCIPLES_FOR_INJECTION
        inject_status = "✅ 已達注入門檻" if can_inject else f"⏳ 差 {MIN_PRINCIPLES_FOR_INJECTION - active_count} 條就開始注入"
        st.caption(f"目前啟用中：{active_count} 條 · {inject_status}")

        for p in filtered:
            row = p["row_number"]
            marker = "✅" if "正" in p["type"] else "❌"
            status_badge = {"active": "🟢", "disabled": "⏸️", "archived": "📦"}.get(p["status"], "")
            topic_tag = f"［{p['topic']}］" if p["topic"] else ""
            title = f"{status_badge} {marker} {topic_tag} {p['principle'][:60]}"

            with st.expander(title):
                st.caption(
                    f"建立：{p['created_at'][:10]} · "
                    f"使用次數：{p['usage_count']} · "
                    f"最後引用：{p['last_used_at'][:10] if p['last_used_at'] else '未使用'} · "
                    f"來源貼文：row {p['source_post_row'] or '手動'}"
                )

                new_type = st.selectbox(
                    "類型", ["正向", "負向"],
                    index=0 if "正" in p["type"] else 1,
                    key=f"type_{row}",
                )
                new_principle = st.text_area(
                    "原則", value=p["principle"], height=70, key=f"principle_{row}"
                )
                new_reason = st.text_area(
                    "理由", value=p["reason"], height=70, key=f"reason_{row}"
                )
                new_topic = st.text_input(
                    "主題", value=p["topic"], key=f"topic_{row}"
                )
                new_notes = st.text_input(
                    "備註", value=p["notes"], key=f"notes_{row}"
                )

                b1, b2, b3, b4 = st.columns(4)
                with b1:
                    if st.button("💾 儲存變更", key=f"save_{row}", type="primary"):
                        update_principle(
                            row=row,
                            principle_type=new_type,
                            principle=new_principle,
                            reason=new_reason,
                            topic=new_topic,
                            notes=new_notes,
                        )
                        st.success("✅ 已儲存")
                        st.rerun()
                with b2:
                    if p["status"] == "active":
                        if st.button("⏸️ 停用", key=f"disable_{row}"):
                            set_principle_status(row, "disabled")
                            st.rerun()
                    else:
                        if st.button("▶️ 啟用", key=f"enable_{row}"):
                            set_principle_status(row, "active")
                            st.rerun()
                with b3:
                    if st.button("📦 歸檔", key=f"archive_{row}"):
                        set_principle_status(row, "archived")
                        st.rerun()
                with b4:
                    if st.button("🗑️ 刪除", key=f"delete_{row}"):
                        delete_principle(row)
                        st.success("✅ 已刪除")
                        st.rerun()

# ─── Tab 2：手動新增 ───────────────────────────────
with tab_add:
    st.subheader("➕ 手動新增原則")
    st.markdown("有些隱性規則 AI 抽不到，或你有特定偏好想強制注入，可以直接加進原則庫。")

    m_type = st.selectbox("類型", ["正向", "負向"], key="manual_type")
    m_principle = st.text_area(
        "原則（一句話，具體可執行）",
        placeholder="例：標題用問句開頭，並以 emoji 點綴情緒",
        height=80,
        key="manual_principle",
    )
    m_reason = st.text_area(
        "理由（一句話說明為什麼）",
        placeholder="例：家長通常邊滑 FB 邊看，問句能瞬間觸發停頓",
        height=80,
        key="manual_reason",
    )
    m_topic = st.text_input(
        "主題（選填）", placeholder="例：親子教養", key="manual_topic"
    )
    m_notes = st.text_input(
        "備註（選填）", placeholder="例：2026-04 新增", key="manual_notes"
    )

    if st.button("💾 新增到原則庫", type="primary"):
        if not m_principle.strip():
            st.error("請填寫原則內容")
        else:
            result = add_principle(
                principle_type=m_type,
                principle=m_principle.strip(),
                reason=m_reason.strip(),
                source_post_row="手動",
                topic=m_topic.strip(),
                notes=m_notes.strip(),
            )
            if result.get("success"):
                st.success(f"✅ 已新增（第 {result['row']} 列）")
                st.rerun()
            else:
                st.error("❌ 新增失敗")

# ─── Tab 3：維護 ───────────────────────────────
with tab_maintain:
    st.subheader("🛠️ 維護工具")
    st.markdown(
        "- **套用衰減**：把超過門檻天數未被引用的啟用原則標為 `archived`（歸檔），不會從 Sheet 刪除，需要時可手動重新啟用。\n"
        "- **月度合併**：由 cron 呼叫 `scripts/merge_principles.py`，用 Gemini 自動合併重複或相似的原則；合併前會先存快照到 `logs/principles_snapshots/`。"
    )

    if st.button("🕓 立即套用衰減"):
        count = apply_principle_decay()
        if count:
            st.success(f"✅ 已歸檔 {count} 條超過 {PRINCIPLE_DECAY_DAYS} 天未使用的原則")
        else:
            st.info("沒有需要歸檔的原則")
