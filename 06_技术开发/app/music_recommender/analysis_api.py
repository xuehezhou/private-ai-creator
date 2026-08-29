# -*- coding: utf-8 -*-
"""
音乐推荐模块 · 标准接口层（analysis 契约）
=============================================
对外暴露 `recommend_from_analysis()`：按产品整合方案定义的 `analysis`
数据契约推荐 BGM，返回 `bgm_candidates` 列表。

    from music_recommender import recommend_from_analysis

    candidates = recommend_from_analysis({
        "emotion": "growth",
        "scene": "code_learning",
        "content_type": "image_text",
        "theme": "用AI三小时学完Python基础",
        "tags": ["AI学习", "Python入门"],
        "account_positioning": "04年AI项目记录",
        "body_text": "04年出生。我开始认真做AI项目…",
    })

    # 输出：
    # {"bgm_candidates": [{rank, name, artist, search_keyword, reason,
    #                      clip_suggestion, score, mood_tags, scene_tags}, ...],
    #  "primary_mood": "growth", "confidence": 0.85, "fallback_used": False}

本层职责：
  - 把 analysis 契约 映射为 RecommendRequest（含 UserProfile）
  - 把 RecommendResult 映射为 bgm_candidates（模块输出契约）
  - 只调用模块唯一入口 recommend()，不触碰内部算法

版本：V1.0 | 2026-07-31
"""
from typing import List, Optional

from .models import (
    RecommendRequest, RecommendResult, ContentContext, UserProfile,
    MusicRecommendation,
)
from .recommender import recommend


# ═══════════════════════════════════════════════════════════════
# analysis 契约 → RecommendRequest
# ═══════════════════════════════════════════════════════════════

def analysis_to_request(analysis: dict, top_k: int = 3,
                        include_reasoning: bool = True) -> RecommendRequest:
    """将 analysis 数据契约映射为推荐模块的输入对象。

    analysis 字段 → ContentContext / UserProfile 映射：
        emotion             → mood
        scene               → scene_type
        theme               → theme
        body_text           → body_text
        tags                → tags
        account_positioning → user.account_type
    """
    analysis = analysis or {}
    content = ContentContext(
        theme=str(analysis.get("theme", "") or ""),
        body_text=str(analysis.get("body_text", "") or ""),
        mood=analysis.get("emotion") or None,
        scene_type=analysis.get("scene") or None,
        tags=list(analysis.get("tags") or []),
    )
    user = UserProfile(
        account_type=str(analysis.get("account_positioning", "") or "AI学习成长记录"),
        age=int(analysis.get("age") or 20),
    )
    return RecommendRequest(
        content=content,
        user=user,
        top_k=int(top_k),
        include_reasoning=include_reasoning,
    )


# ═══════════════════════════════════════════════════════════════
# RecommendResult → bgm_candidates 契约
# ═══════════════════════════════════════════════════════════════

def to_bgm_candidates(result: RecommendResult) -> List[dict]:
    """将推荐结果转换为模块输出契约 bgm_candidates。

    每项字段：
        rank           排名
        name / artist  歌名 / 歌手
        display        展示名（"歌名 - 歌手"）
        search_keyword 抖音搜索关键词
        reason         推荐理由
        clip_suggestion 截取建议
        score          匹配分 0.0~1.0
        mood_tags / scene_tags  情绪 / 场景标签
    """
    candidates = []
    for r in result.recommendations or []:
        t = r.track
        display = f"{t.name} - {t.artist}" if t.artist != "纯音乐" else t.name
        clip = ""
        if t.clip_start_sec is not None and t.clip_end_sec is not None:
            clip = f"{t.clip_start_sec}s-{t.clip_end_sec}s"
        candidates.append({
            "rank": r.rank,
            "name": t.name,
            "artist": t.artist,
            "display": display,
            "search_keyword": r.search_hint.replace("抖音搜索：", "").strip(),
            "reason": (r.match_reasons[0] if r.match_reasons else "智能推荐"),
            "clip_suggestion": clip,
            "score": round(float(r.match_score), 4),
            "mood_tags": list(t.mood_tags or []),
            "scene_tags": list(t.scene_tags or []),
        })
    return candidates


# ═══════════════════════════════════════════════════════════════
# 标准入口
# ═══════════════════════════════════════════════════════════════

def recommend_from_analysis(analysis: dict, top_k: int = 3,
                            include_reasoning: bool = True) -> dict:
    """按 analysis 数据契约推荐 BGM（音乐推荐模块标准接口）。

    Args:
        analysis: 素材包 analysis 字段（emotion/scene/content_type/
                  theme/tags/account_positioning/body_text）
        top_k:    推荐数量（默认 3）

    Returns:
        {
            "bgm_candidates": [...],   # to_bgm_candidates 契约
            "primary_mood": "growth",
            "confidence": 0.85,
            "fallback_used": False,
        }

    失败时返回空候选（调用方应安全处理）。
    """
    try:
        request = analysis_to_request(analysis, top_k=top_k,
                                      include_reasoning=include_reasoning)
        result = recommend(request)
        return {
            "bgm_candidates": to_bgm_candidates(result),
            "primary_mood": result.primary_mood,
            "confidence": result.confidence,
            "fallback_used": result.fallback_used,
        }
    except Exception:
        # 推荐失败不阻断主流程：返回空候选 + 兜底情绪
        return {
            "bgm_candidates": [],
            "primary_mood": (analysis or {}).get("emotion", "focus"),
            "confidence": 0.0,
            "fallback_used": True,
        }
