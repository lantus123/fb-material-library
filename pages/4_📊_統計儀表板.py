"""統計儀表板頁面 — 成效分析。"""

import sys
from pathlib import Path
from collections import defaultdict

import streamlit as st

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.sheets_api import get_stats, get_post_records, get_top_posts
from scripts.metrics import compute_monthly_diff
from scripts.style_fingerprint import compute_fingerprints, MIN_SAMPLES_PER_TOPIC
from pages.auth import require_auth

st.set_page_config(page_title="統計儀表板", page_icon="📊", layout="wide")
require_auth()
st.title("📊 統計儀表板")

# ─── 素材庫統計 ─────────────────────────────────────────
st.subheader("📚 素材庫概覽")

stats = get_stats()
if stats and not stats.get("error"):
    col1, col2, col3 = st.columns(3)
    col1.metric("素材總數", stats.get("total", 0))
    col2.metric("本週新增", stats.get("thisWeek", 0))
    col3.metric("高相關性 (≥8分)", stats.get("highRelevance", 0))

    by_topic = stats.get("byTopic", {})
    if by_topic:
        st.markdown("**各主題素材數量**")
        st.bar_chart(by_topic)
else:
    st.warning("無法取得素材庫統計")

st.divider()

# ─── 貼文成效統計 ───────────────────────────────────────
st.subheader("📱 貼文成效分析")

records = get_post_records(limit=100)

if not records:
    st.info("📭 還沒有貼文紀錄，貼文成效分析累積後會顯示。")

# 基本統計
total_posts = len(records)
rated_posts = [r for r in records if r.get("rating", 0) > 0]
fb_posts = [r for r in records if r.get("likes", 0) or r.get("comments", 0) or r.get("shares", 0)]

col1, col2, col3, col4 = st.columns(4)
col1.metric("貼文總數", total_posts)
col2.metric("已評分", len(rated_posts))
col3.metric("有FB數據", len(fb_posts))
avg_rating = sum(r["rating"] for r in rated_posts) / len(rated_posts) if rated_posts else 0
col4.metric("平均評分", f"{avg_rating:.1f}/5")

# 按類型分析
st.markdown("### 各貼文類型表現")
type_stats = defaultdict(lambda: {"count": 0, "total_rating": 0, "total_likes": 0, "total_comments": 0})
for r in records:
    pt = r.get("post_type", "一般")
    type_stats[pt]["count"] += 1
    type_stats[pt]["total_rating"] += r.get("rating", 0)
    type_stats[pt]["total_likes"] += r.get("likes", 0)
    type_stats[pt]["total_comments"] += r.get("comments", 0)

type_chart = {}
for pt, s in type_stats.items():
    avg = s["total_rating"] / s["count"] if s["count"] else 0
    type_chart[f"{pt} ({s['count']}篇)"] = round(avg, 1)

if type_chart:
    st.markdown("**平均評分（按類型）**")
    st.bar_chart(type_chart)

# 如果有 FB 數據，顯示互動分析
if fb_posts:
    st.markdown("### FB 互動數據")
    fb_type_engagement = defaultdict(lambda: {"count": 0, "likes": 0, "comments": 0, "shares": 0})
    for r in fb_posts:
        pt = r.get("post_type", "一般")
        fb_type_engagement[pt]["count"] += 1
        fb_type_engagement[pt]["likes"] += r.get("likes", 0)
        fb_type_engagement[pt]["comments"] += r.get("comments", 0)
        fb_type_engagement[pt]["shares"] += r.get("shares", 0)

    engagement_chart = {}
    for pt, s in fb_type_engagement.items():
        avg_engagement = (s["likes"] + s["comments"] + s["shares"]) / s["count"] if s["count"] else 0
        engagement_chart[pt] = round(avg_engagement, 1)

    st.markdown("**平均互動數（按類型）**")
    st.bar_chart(engagement_chart)

# ─── 學習指標 ─────────────────────────────────────────
st.divider()
st.subheader("🧠 學習指標")
st.caption("衡量 AI 初版 → 你最終版的貼近程度。學習迴路有效時，差異應隨月份下降。")

edited = [
    r for r in records
    if r.get("original_content")
    and r["original_content"].strip() != (r.get("post_content") or "").strip()
]
principled = [r for r in records if r.get("edit_principle")]

lc1, lc2, lc3 = st.columns(3)
lc1.metric("累積貼文", len(records))
lc2.metric("已編輯貼文", len(edited))
lc3.metric("已萃取原則", len(principled))

monthly = compute_monthly_diff(records=records)
if monthly:
    st.markdown("**每月 AI 初版 → 最終版 平均字數差異 %**")
    chart_data = {m: s["avg_diff_pct"] for m, s in monthly.items()}
    st.line_chart(chart_data)
    rows_table = [
        {"月份": m, "樣本數": s["count"], "平均差異 %": s["avg_diff_pct"]}
        for m, s in monthly.items()
    ]
    st.dataframe(rows_table, hide_index=True, use_container_width=True)
else:
    st.info(
        "📭 還沒累積到編輯資料。先生成幾篇貼文、實際做過修改後，"
        "這裡會出現逐月學習趨勢圖。"
    )

if principled:
    st.markdown("**🧩 最近萃取的修改原則**")
    for r in principled[:5]:
        title = (r.get("material_title") or "")[:40]
        date = str(r.get("generated_at", ""))[:10]
        st.markdown(f"**{date}** · {title}")
        st.code(r.get("edit_principle", ""), language=None)

# ─── 風格指紋（階段 3）─────────────────────────────────
st.divider()
st.subheader("🎨 各主題風格指紋")
st.caption(
    f"從每個主題「評分 ≥4」的貼文抽取量化特徵，作為生成時的風格參照。"
    f"每主題至少需要 {MIN_SAMPLES_PER_TOPIC} 個樣本才會顯示。"
)

fingerprints = compute_fingerprints(records)
if not fingerprints:
    st.info(
        f"📭 還沒有主題累積到足夠樣本（需要 ≥4 分、≥{MIN_SAMPLES_PER_TOPIC} 篇）。"
        f"累積後這裡會顯示各主題的字數、emoji 密度、問句比例等統計。"
    )
else:
    fp_cols = st.columns(min(len(fingerprints), 3))
    for i, (topic, fp) in enumerate(fingerprints.items()):
        with fp_cols[i % len(fp_cols)]:
            st.markdown(f"**{topic}** （{fp['sample_size']} 篇樣本）")
            st.metric("平均字數", f"{fp['avg_length']} 字")
            st.metric("emoji 密度", f"{fp['emoji_density']} / 百字")
            st.metric("問句比例", f"{fp['avg_question_ratio']}%")
            st.caption(
                f"段落 {fp['avg_paragraph_count']} · "
                f"hashtag {fp['avg_hashtag_count']} · "
                f"句長 {fp['avg_sentence_length']}"
            )
            if fp["opens_with_question_pct"] >= 50:
                st.caption(f"🙋 {fp['opens_with_question_pct']}% 以問句開頭")
            if fp["opens_with_bracket_pct"] >= 50:
                st.caption(f"【 {fp['opens_with_bracket_pct']}% 以【】開頭")

# 最佳貼文排行
st.divider()
st.subheader("🏆 最佳貼文排行")

top_posts = get_top_posts(limit=5)
if top_posts:
    for i, p in enumerate(top_posts, 1):
        content_preview = p.get("post_content", "")[:100]
        if len(p.get("post_content", "")) > 100:
            content_preview += "..."

        metrics = []
        if p.get("likes"):
            metrics.append(f"👍 {p['likes']}")
        if p.get("comments"):
            metrics.append(f"💬 {p['comments']}")
        if p.get("shares"):
            metrics.append(f"🔄 {p['shares']}")
        metrics_str = " | ".join(metrics) if metrics else "尚無FB數據"

        st.markdown(
            f"**#{i}** ⭐{p.get('rating', 0)}/5 | {p.get('post_type', '一般')} | {metrics_str}\n\n"
            f"> {content_preview}"
        )
        st.divider()
else:
    st.info("累積一些貼文評分後，這裡會顯示最佳貼文排行。")
