"""FB素材庫 — 風格指紋

從「編輯版 + 評分 ≥ 4」的貼文抽取量化特徵，按 post_type 分桶，
作為生成時的風格參照。特徵純文字處理、不呼叫任何 API。
"""

from __future__ import annotations

import re
from collections import defaultdict
from statistics import mean

MIN_SAMPLES_PER_TOPIC = 3  # 少於 N 篇就不產生該主題的指紋
MIN_RATING_FOR_FINGERPRINT = 4  # 評分下限

_EMOJI_RE = re.compile(
    "["
    "\U0001F300-\U0001FAFF"
    "\U00002600-\U000027BF"
    "\U0001F900-\U0001F9FF"
    "]",
    flags=re.UNICODE,
)
_HASHTAG_RE = re.compile(r"#[\w\u4e00-\u9fa5]+")
_QUESTION_RE = re.compile(r"[？?]")
_SENTENCE_SPLIT_RE = re.compile(r"[。！!？?\n]+")


def _extract_features(text: str) -> dict:
    if not text:
        return {}
    length = len(text)
    emoji_count = len(_EMOJI_RE.findall(text))
    hashtag_count = len(_HASHTAG_RE.findall(text))
    question_count = len(_QUESTION_RE.findall(text))
    paragraphs = [p for p in text.split("\n\n") if p.strip()]
    sentences = [s for s in _SENTENCE_SPLIT_RE.split(text) if s.strip()]
    first_line = text.strip().split("\n", 1)[0] if text.strip() else ""
    opens_with_question = bool(first_line and first_line[-1] in "？?")
    opens_with_bracket = bool(re.match(r"^\s*[【「『]", text.strip()))

    return {
        "length": length,
        "emoji_density": round(emoji_count / max(length, 1) * 100, 2),  # 每 100 字
        "hashtag_count": hashtag_count,
        "paragraph_count": len(paragraphs),
        "sentence_count": len(sentences),
        "avg_sentence_length": round(length / max(len(sentences), 1), 1),
        "question_ratio": round(question_count / max(len(sentences), 1) * 100, 1),
        "opens_with_question": opens_with_question,
        "opens_with_bracket": opens_with_bracket,
    }


def _average_features(features_list: list[dict]) -> dict:
    if not features_list:
        return {}

    def avg(key: str) -> float:
        values = [f[key] for f in features_list if key in f]
        return round(mean(values), 1) if values else 0.0

    return {
        "sample_size": len(features_list),
        "avg_length": int(avg("length")),
        "emoji_density": avg("emoji_density"),
        "avg_hashtag_count": avg("hashtag_count"),
        "avg_paragraph_count": avg("paragraph_count"),
        "avg_sentence_length": avg("avg_sentence_length"),
        "avg_question_ratio": avg("question_ratio"),
        "opens_with_question_pct": round(
            sum(1 for f in features_list if f.get("opens_with_question")) / len(features_list) * 100, 1
        ),
        "opens_with_bracket_pct": round(
            sum(1 for f in features_list if f.get("opens_with_bracket")) / len(features_list) * 100, 1
        ),
    }


def compute_fingerprints(records: list[dict]) -> dict[str, dict]:
    """回傳 {post_type: fingerprint} 字典。只計算符合樣本門檻的主題。

    資料來源優先序：
    1. 編輯版（post_content）且評分 ≥ MIN_RATING_FOR_FINGERPRINT
    2. 若該主題編輯版樣本不足，退回「評分 ≥ 4」的所有貼文
    """
    buckets: dict[str, list[dict]] = defaultdict(list)
    for r in records:
        if r.get("rating", 0) < MIN_RATING_FOR_FINGERPRINT:
            continue
        pt = r.get("post_type") or "一般"
        content = r.get("post_content", "")
        if not content:
            continue
        buckets[pt].append(_extract_features(content))

    result = {}
    for pt, feats in buckets.items():
        if len(feats) >= MIN_SAMPLES_PER_TOPIC:
            result[pt] = _average_features(feats)
    return result


def format_fingerprint_for_prompt(fingerprint: dict, post_type: str) -> str:
    """把指紋格式化為 prompt 可讀的一段文字。"""
    if not fingerprint:
        return ""
    fp = fingerprint
    lines = [
        f"本類（{post_type}）過往高分貼文的量化風格（基於 {fp['sample_size']} 篇 ≥4 分樣本）：",
        f"- 平均字數約 {fp['avg_length']} 字（請控制在 ±20% 內）",
        f"- 平均段落數 {fp['avg_paragraph_count']} 段",
        f"- emoji 密度 {fp['emoji_density']} 個/百字",
        f"- hashtag 約 {fp['avg_hashtag_count']} 個",
        f"- 問句比例 {fp['avg_question_ratio']}%（每 100 句中約有這麼多問句）",
    ]
    if fp["opens_with_question_pct"] >= 50:
        lines.append(f"- {fp['opens_with_question_pct']}% 的貼文以問句開頭（請優先考慮）")
    if fp["opens_with_bracket_pct"] >= 50:
        lines.append(f"- {fp['opens_with_bracket_pct']}% 的貼文以【】開頭")
    return "\n".join(lines)
