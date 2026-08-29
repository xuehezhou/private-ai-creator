# -*- coding: utf-8 -*-
"""
音乐推荐模块（Music Recommendation Module）
=============================================
独立模块，根据内容上下文自动推荐适合的抖音热门BGM。

使用方式：
    from music_recommender import recommend, RecommendRequest, ContentContext

    result = recommend(RecommendRequest(
        content=ContentContext(
            theme="用AI三小时学完Python基础",
            body_text="04年出生。我开始认真做AI项目...",
            mood="growth",
        ),
        top_k=3,
    ))

    # 遍历推荐
    for rec in result.recommendations:
        print(f"{rec.rank}. {rec.track.name} (得分: {rec.match_score})")
        print(f"   {rec.search_hint}")

模块边界：
    - 只暴露 recommend() 函数
    - 内部实现（匹配算法、数据库）对外不可见
    - 调用方不需要理解音乐模块内部细节

版本：V1.0 | 2026-07-31
"""
from .models import (
    RecommendRequest, RecommendResult,
    MusicRecommendation, MusicTrack,
    ContentContext, UserProfile,
    to_legacy_bgm, to_display_list,
)
from .recommender import recommend, recommend_simple, _reload_db
from .analysis_api import (
    recommend_from_analysis, to_bgm_candidates, analysis_to_request,
)

__all__ = [
    "recommend",
    "recommend_simple",
    "recommend_from_analysis",
    "to_bgm_candidates",
    "analysis_to_request",
    "RecommendRequest",
    "RecommendResult",
    "MusicRecommendation",
    "MusicTrack",
    "ContentContext",
    "UserProfile",
    "to_legacy_bgm",
    "to_display_list",
    "_reload_db",
]

__version__ = "1.0"
