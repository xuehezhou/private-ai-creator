# -*- coding: utf-8 -*-
"""
音乐推荐模块 · 推荐引擎核心
============================
协调情绪推断 → 多维匹配 → 结果后处理 → 输出推荐结果。

模块唯一入口：recommend(request) → RecommendResult

版本：V1.0 | 2026-07-31
"""
import os
import json
import datetime
from typing import Optional, List

from .models import (
    RecommendRequest, RecommendResult,
    MusicRecommendation, MusicTrack, ContentContext,
    to_legacy_bgm, to_display_list,
)
from .mood_inference import infer_mood, infer_scene, extract_keywords
from .scorer import compute_all_scores, DEFAULT_WEIGHTS


# ═══════════════════════════════════════════════════════════════
# 曲库加载
# ═══════════════════════════════════════════════════════════════

def _load_music_db() -> dict:
    """加载音乐数据库。"""
    # 优先从模块目录加载
    db_path = os.path.join(os.path.dirname(__file__), "music_db.json")
    if os.path.exists(db_path):
        with open(db_path, "r", encoding="utf-8") as f:
            return json.load(f)

    # 回退：从项目 07_数据资产/音乐库/ 加载
    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    alt_path = os.path.join(root, "07_数据资产", "音乐库", "music_db.json")
    if os.path.exists(alt_path):
        with open(alt_path, "r", encoding="utf-8") as f:
            return json.load(f)

    # 终极兜底：返回空曲库，由硬编码兜底接管
    return {"tracks": [], "fallback_track_ids": [], "default_moods": {}}


# 模块加载时缓存曲库（避免每次推荐都读文件）
_MUSIC_DB_CACHE = None


def _get_db() -> dict:
    global _MUSIC_DB_CACHE
    if _MUSIC_DB_CACHE is None:
        _MUSIC_DB_CACHE = _load_music_db()
    return _MUSIC_DB_CACHE


def _reload_db():
    """强制重新加载曲库（用于热更新场景）。"""
    global _MUSIC_DB_CACHE
    _MUSIC_DB_CACHE = None
    return _get_db()


# ═══════════════════════════════════════════════════════════════
# 兜底推荐（当曲库为空或所有匹配分均为 0 时）
# ═══════════════════════════════════════════════════════════════

_HARDCODED_FALLBACK = [
    {
        "track_id": "fallback_001",
        "name": "起风了",
        "artist": "买辣椒也用券",
        "source": "hardcoded_fallback",
        "mood_tags": ["growth", "warm"],
        "scene_tags": ["成长记录", "回忆感慨"],
        "theme_keywords": ["成长", "时间", "回忆", "变化", "青春"],
        "music_features": {"tempo": "medium", "energy": "medium"},
        "usage": {"douyin_hot_count": "9300w+"},
        "clip_suggestion": {"start_sec": 50, "end_sec": 80},
        "recommendation_text": {
            "reason": "国民级抖音热歌，通用成长叙事百搭",
            "search_hint": "抖音搜索：起风了 买辣椒也用券",
        },
    },
    {
        "track_id": "fallback_002",
        "name": "少年",
        "artist": "梦然",
        "source": "hardcoded_fallback",
        "mood_tags": ["growth", "energetic"],
        "scene_tags": ["热血时刻", "青春宣言"],
        "theme_keywords": ["年轻", "热血", "不服输", "04年"],
        "music_features": {"tempo": "fast", "energy": "high"},
        "usage": {"douyin_hot_count": "2.5亿+"},
        "clip_suggestion": {"start_sec": 30, "end_sec": 60},
        "recommendation_text": {
            "reason": "年轻不服输，配合'还在学'的人设",
            "search_hint": "抖音搜索：少年 梦然",
        },
    },
    {
        "track_id": "fallback_003",
        "name": "夜空中最亮的星",
        "artist": "逃跑计划",
        "source": "hardcoded_fallback",
        "mood_tags": ["focus", "growth", "warm"],
        "scene_tags": ["深夜反思", "目标坚定"],
        "theme_keywords": ["坚持", "目标", "方向", "迷茫"],
        "music_features": {"tempo": "medium", "energy": "medium"},
        "usage": {"douyin_hot_count": "1.8亿+"},
        "clip_suggestion": {"start_sec": 35, "end_sec": 65},
        "recommendation_text": {
            "reason": "抖音常驻热门，辨识度极高",
            "search_hint": "抖音搜索：夜空中最亮的星 逃跑计划",
        },
    },
]


# ═══════════════════════════════════════════════════════════════
# Track dict → MusicTrack 对象转换
# ═══════════════════════════════════════════════════════════════

def _dict_to_track(d: dict) -> MusicTrack:
    """将曲库中的字典转换为 MusicTrack 对象。"""
    clip = d.get("clip_suggestion", {}) or {}
    rec = d.get("recommendation_text", {}) or {}
    usage = d.get("usage", {}) or {}
    features = d.get("music_features", {}) or {}

    return MusicTrack(
        track_id=d.get("track_id", ""),
        name=d.get("name", ""),
        artist=d.get("artist", ""),
        source=d.get("source", ""),
        mood_tags=d.get("mood_tags", []),
        scene_tags=d.get("scene_tags", []),
        tempo=features.get("tempo"),
        energy=features.get("energy"),
        duration_sec=usage.get("best_duration_sec"),
        clip_start_sec=clip.get("start_sec"),
        clip_end_sec=clip.get("end_sec"),
        popularity=usage.get("douyin_hot_count") or usage.get("douin_hot_count"),
    )


def _build_search_hint(track: MusicTrack) -> str:
    """生成抖音搜索提示。"""
    if track.artist == "纯音乐":
        return f"抖音搜索：{track.name}"
    return f"抖音搜索：{track.name} {track.artist}"


def _build_match_reasons(track_dict: dict, breakdown: dict,
                         target_mood: str, target_scene: str) -> List[str]:
    """根据评分 breakdown 生成人类可读的匹配理由。"""
    reasons = []

    # 情绪匹配
    if breakdown.get("mood", 0) > 0:
        mood_score = breakdown["mood"]
        if mood_score >= 0.35:
            reasons.append(f"情绪高度匹配：{target_mood} → {track_dict['name']}")
        elif mood_score > 0:
            reasons.append(f"情绪部分匹配：{target_mood}")

    # 场景匹配
    if breakdown.get("scene", 0) > 0:
        scene_score = breakdown["scene"]
        if scene_score >= 0.20:
            scene_tags = "、".join(track_dict.get("scene_tags", [])[:2])
            reasons.append(f"场景匹配：{target_scene} → {scene_tags}")

    # 关键词匹配
    if breakdown.get("keyword", 0) > 0.05:
        reasons.append("文案关键词匹配度较高")

    # 热度
    if breakdown.get("popularity", 0) > 0.02:
        hot = (
            track_dict.get("usage", {}).get("douyin_hot_count", "")
            or track_dict.get("usage", {}).get("douin_hot_count", "")
        )
        if hot:
            reasons.append(f"抖音热度：★★★★★ ({hot} 使用量)")

    # 推荐理由（曲库中的文案）
    rec_reason = track_dict.get("recommendation_text", {}).get("reason", "")
    if rec_reason and len(reasons) < 3:
        reasons.append(rec_reason)

    if not reasons:
        reasons.append("智能推荐")

    return reasons[:4]  # 最多 4 条理由


# ═══════════════════════════════════════════════════════════════
# 多样性保证
# ═══════════════════════════════════════════════════════════════

def _ensure_diversity(scored: list, top_k: int) -> list:
    """保证 TopK 推荐的情绪多样性。

    规则：Top3 中至少包含 2 种不同情绪。
    如果前 3 首情绪相同，用后面不同情绪的歌替换第 3 首。
    """
    if top_k < 3 or len(scored) < 3:
        return scored[:top_k]

    # 检查前 top_k 的情绪分布
    top_moods = set()
    for track_dict, _score, _bd in scored[:top_k]:
        top_moods.update(track_dict.get("mood_tags", [])[:1])

    if len(top_moods) >= 2:
        return scored[:top_k]  # 已有足够多样性

    # 从前 3 首之后找一个不同情绪的歌替换第 3 首
    for i in range(top_k, len(scored)):
        track_dict, _score, _bd = scored[i]
        track_first_mood = (
            track_dict.get("mood_tags", [None])[0]
        )
        if track_first_mood and track_first_mood not in top_moods:
            # 替换第 3 首
            result = list(scored[:top_k - 1]) + [scored[i]]
            return result

    return scored[:top_k]


# ═══════════════════════════════════════════════════════════════
# 主推荐函数
# ═══════════════════════════════════════════════════════════════

def recommend(request: RecommendRequest) -> RecommendResult:
    """音乐推荐模块唯一入口。

    输入 RecommendRequest → 返回 RecommendResult

    流程：
    1. 推断情绪/场景（输入未指定时）
    2. 加载曲库，逐首计算匹配得分
    3. 按得分排序 + 多样性保证
    4. 取 TopK，构建返回结果
    5. 低置信度时启用兜底

    Args:
        request: 推荐请求，包含内容上下文和可选参数

    Returns:
        RecommendResult: 推荐结果，含 TopK 歌曲 + 置信度 + 匹配理由
    """
    content = request.content
    top_k = min(request.top_k, 10)  # 最多 10 首
    include_reasoning = request.include_reasoning

    # ── Step 1: 情绪/场景推断 ──
    mood = content.mood
    mood_confidence = 1.0
    if not mood:
        mood, mood_confidence = infer_mood(content.body_text, content.difficulty)

    scene = content.scene_type
    if not scene:
        scene, _ = infer_scene(content.body_text, content.theme)

    # ── Step 2: 提取关键词 ──
    keywords = extract_keywords(content.body_text, content.tags)

    # ── Step 3: 加载曲库 ──
    db = _get_db()
    tracks = db.get("tracks", [])

    # 用户画像（dict 形式，方便透传）
    user_profile = None
    if request.user:
        user_profile = {
            "account_type": request.user.account_type,
            "content_pillars": request.user.content_pillars,
            "age": request.user.age,
            "preferred_moods": request.user.preferred_moods,
        }

    # ── Step 4: 多维匹配 ──
    if tracks:
        scored = compute_all_scores(
            tracks, mood, scene,
            content.body_text, keywords, user_profile
        )
    else:
        scored = []  # 曲库为空

    # ── Step 5: 多样性 + TopK ──
    fallback_used = False
    if scored and scored[0][1] > 0:
        top_scored = _ensure_diversity(scored, top_k)
    else:
        # 无匹配结果，使用兜底
        fallback_used = True
        top_scored = _apply_fallback(db, mood, top_k)

    # ── Step 6: 构建输出 ──
    recommendations = []
    for rank, (track_dict, score, breakdown) in enumerate(top_scored, 1):
        track = _dict_to_track(track_dict)
        reasons = _build_match_reasons(track_dict, breakdown, mood, scene) \
            if include_reasoning else []
        search_hint = _build_search_hint(track)

        recommendations.append(MusicRecommendation(
            rank=rank,
            track=track,
            match_score=round(score, 4),
            match_reasons=reasons,
            search_hint=search_hint,
        ))

    # 置信度：取 mood_confidence 和 最高匹配分的调和
    if recommendations:
        raw_confidence = (mood_confidence + recommendations[0].match_score) / 2
    else:
        raw_confidence = 0.0
    if fallback_used:
        raw_confidence = min(raw_confidence, 0.35)

    result = RecommendResult(
        recommendations=recommendations,
        primary_mood=mood,
        confidence=round(raw_confidence, 2),
        fallback_used=fallback_used,
        generated_at=datetime.datetime.now().isoformat(),
    )

    return result


def _apply_fallback(db: dict, mood: str, top_k: int) -> list:
    """应用兜底策略。

    优先级：
    1. 按 mood 查找 db.default_moods → 匹配对应 track_id
    2. 按 fallback_track_ids 查找
    3. 硬编码兜底
    """
    # 1. 按 mood 的默认推荐
    default_moods = db.get("default_moods", {})
    mood_ids = default_moods.get(mood, [])
    if mood_ids:
        tracks = db.get("tracks", [])
        id_map = {t.get("track_id"): t for t in tracks}
        result = []
        for tid in mood_ids:
            if tid in id_map:
                result.append((id_map[tid], 0.30, {"mood": 0.12, "fallback": True}))
                if len(result) >= top_k:
                    return result
        if result:
            return result

    # 2. 按全局 fallback_track_ids
    fallback_ids = db.get("fallback_track_ids", [])
    if fallback_ids:
        tracks = db.get("tracks", [])
        id_map = {t.get("track_id"): t for t in tracks}
        result = []
        for tid in fallback_ids[:top_k]:
            if tid in id_map:
                result.append((id_map[tid], 0.25, {"mood": 0.10, "fallback": True}))
        if result:
            return result

    # 3. 曲库中有歌但没配置 fallback，直接取前几首
    tracks = db.get("tracks", [])
    if tracks:
        return [(t, 0.20, {"mood": 0.08, "fallback": True})
                for t in tracks[:top_k]]

    # 4. 终极硬编码兜底
    return [(t, 0.10, {"mood": 0.04, "fallback": True, "hardcoded": True})
            for t in _HARDCODED_FALLBACK[:top_k]]


# ═══════════════════════════════════════════════════════════════
# 便捷函数（兼容旧代码）
# ═══════════════════════════════════════════════════════════════

def recommend_simple(theme: str, body: str, mood: str = None,
                     difficulty: str = "", tags: list = None,
                     top_k: int = 3) -> RecommendResult:
    """简化调用接口：只传必要字段，返回 RecommendResult。

    用于最快速的集成场景。
    """
    return recommend(RecommendRequest(
        content=ContentContext(
            theme=theme,
            body_text=body,
            mood=mood,
            difficulty=difficulty,
            tags=tags or [],
        ),
        top_k=top_k,
    ))
