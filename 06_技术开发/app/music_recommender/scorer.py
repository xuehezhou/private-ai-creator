# -*- coding: utf-8 -*-
"""
音乐推荐模块 · 多维评分引擎
============================
对每首歌计算综合匹配得分，支持权重可配置。

维度：
  ① 情绪匹配 (40%)
  ② 场景匹配 (25%)
  ③ 关键词匹配 (20%)
  ④ 用户偏好 (10%)
  ⑤ 热度加权 (5%)

版本：V1.0 | 2026-07-31
"""
import re
from typing import Dict, Optional, List, Tuple


# ═══════════════════════════════════════════════════════════════
# 可配置权重（未来可通过配置文件调整）
# ═══════════════════════════════════════════════════════════════

DEFAULT_WEIGHTS = {
    "mood":       0.40,   # 情绪匹配
    "scene":      0.25,   # 场景匹配
    "keyword":    0.20,   # 关键词匹配
    "preference": 0.10,   # 用户偏好
    "popularity": 0.05,   # 热度加权
}

# 热度字符串 → 数值映射（用于归一化）
_POPULARITY_MAP = {
    r"(\d+)亿\+": 100_000_000,
    r"(\d+)w\+":  10_000,
}


def _parse_popularity(hot_str: str) -> float:
    """将热度字符串（如 "2.5亿+"）转为数值。"""
    if not hot_str:
        return 0.0
    for pat, multiplier in _POPULARITY_MAP.items():
        m = re.search(pat, hot_str)
        if m:
            return float(m.group(1)) * multiplier
    try:
        return float(hot_str)
    except (ValueError, TypeError):
        return 0.0


def _normalize_popularity(pop_value: float, max_pop: float = 300_000_000) -> float:
    """将热度值归一化到 0~1 范围。

    max_pop 设为 3亿（抖音最高热度水平）
    """
    if pop_value <= 0:
        return 0.0
    return min(pop_value / max_pop, 1.0)


def _score_mood(track_moods: List[str], target_mood: str) -> float:
    """情绪匹配得分。

    完全匹配 = 1.0
    部分重叠 = 0.5
    无重叠 = 0.0
    """
    if not target_mood:
        return 1.0  # 无情绪信息时不给负分
    if target_mood in track_moods:
        return 1.0
    return 0.0


def _score_scene(track_scenes: List[str], target_scene: str) -> float:
    """场景匹配得分。

    完全匹配 = 1.0
    部分重叠 = 0.5
    无重叠 = 0.0
    """
    if not target_scene:
        return 0.5
    if target_scene in track_scenes:
        return 1.0
    return 0.0


def _score_keyword(track_keywords: List[str], body_text: str,
                   extracted_keywords: List[str]) -> float:
    """关键词匹配得分。

    统计命中数，归一化到 0~1。
    """
    text_lower = body_text.lower()
    hit_count = 0

    # 方式1：曲库关键词在正文中出现
    for kw in track_keywords:
        if kw.lower() in text_lower:
            hit_count += 1

    # 方式2：提取的关键词与曲库关键词交叉（取交集）
    track_kw_set = {k.lower() for k in track_keywords}
    extracted_set = {k.lower() for k in (extracted_keywords or [])}
    cross_hits = len(track_kw_set & extracted_set)
    hit_count += cross_hits

    # 归一化：假设命中 5 个关键词即为满分
    return min(hit_count / 5.0, 1.0)


def _score_preference(track, user_profile: Optional[dict] = None) -> float:
    """用户偏好得分。

    当前版本：无偏好数据时返回中性值（0.5），后续可学习。
    """
    if user_profile is None:
        return 0.5  # 中性

    preferred_moods = user_profile.get("preferred_moods", [])
    if not preferred_moods:
        return 0.5

    # 有偏好数据：歌曲情绪是否匹配用户偏好
    track_moods = track.get("mood_tags", [])
    overlap = len(set(track_moods) & set(preferred_moods))
    if overlap > 0:
        return 0.8
    return 0.3


def _score_popularity(track) -> float:
    """热度加权得分。"""
    hot_str = (
        track.get("usage", {}).get("douyin_hot_count", "")
        or track.get("usage", {}).get("douin_hot_count", "")
    )
    pop_value = _parse_popularity(hot_str)
    return _normalize_popularity(pop_value)


def _check_restrictions(track, target_mood: str, target_scene: str) -> Tuple[bool, str]:
    """检查歌曲使用限制。

    返回 (is_allowed, reason)
    """
    restrictions = track.get("restrictions", {})

    # 检查排除情绪
    avoid_moods = restrictions.get("avoid_moods", [])
    if target_mood and target_mood in avoid_moods:
        return (False, f"排除情绪：{target_mood}")

    # 检查排除场景
    avoid_scenes = restrictions.get("avoid_scenes", [])
    if target_scene and target_scene in avoid_scenes:
        return (False, f"排除场景：{target_scene}")

    return (True, "")


def compute_score(track: dict,
                  target_mood: str,
                  target_scene: str,
                  body_text: str,
                  extracted_keywords: List[str],
                  user_profile: Optional[dict] = None,
                  weights: Optional[Dict[str, float]] = None) -> Tuple[float, dict]:
    """计算单首歌的综合匹配得分。

    Args:
        track:              曲库中的歌曲记录
        target_mood:        目标情绪
        target_scene:       目标场景
        body_text:          文案正文
        extracted_keywords: 从正文提取的关键词
        user_profile:       用户画像（可选）
        weights:            维度权重（可选，默认 DEFAULT_WEIGHTS）

    Returns:
        (total_score, score_breakdown)
        - total_score: 0.0 ~ 1.0
        - score_breakdown: {"mood": 0.xx, "scene": 0.xx, ...}
    """
    w = weights or DEFAULT_WEIGHTS

    # 检查使用限制
    allowed, reason = _check_restrictions(track, target_mood, target_scene)
    if not allowed:
        return (0.0, {"restricted": True, "reason": reason})

    track_moods = track.get("mood_tags", [])
    track_scenes = track.get("scene_tags", [])
    track_keywords = track.get("theme_keywords", [])

    # 分维度计算
    breakdown = {}

    # ① 情绪匹配
    mood_raw = _score_mood(track_moods, target_mood)
    breakdown["mood"] = mood_raw * w["mood"]

    # ② 场景匹配
    scene_raw = _score_scene(track_scenes, target_scene)
    breakdown["scene"] = scene_raw * w["scene"]

    # ③ 关键词匹配
    kw_raw = _score_keyword(track_keywords, body_text, extracted_keywords)
    breakdown["keyword"] = kw_raw * w["keyword"]

    # ④ 用户偏好
    pref_raw = _score_preference(track, user_profile)
    breakdown["preference"] = pref_raw * w["preference"]

    # ⑤ 热度加权
    pop_raw = _score_popularity(track)
    breakdown["popularity"] = pop_raw * w["popularity"]

    total = sum(breakdown.values())
    return (round(total, 4), breakdown)


def compute_all_scores(tracks: List[dict],
                       target_mood: str,
                       target_scene: str,
                       body_text: str,
                       extracted_keywords: List[str],
                       user_profile: Optional[dict] = None) -> List[Tuple[dict, float, dict]]:
    """批量计算所有歌曲的匹配得分。

    返回 [(track, total_score, breakdown), ...]，按得分降序。
    """
    results = []
    for track in tracks:
        score, breakdown = compute_score(
            track, target_mood, target_scene,
            body_text, extracted_keywords, user_profile
        )
        results.append((track, score, breakdown))
    results.sort(key=lambda x: -x[1])
    return results
