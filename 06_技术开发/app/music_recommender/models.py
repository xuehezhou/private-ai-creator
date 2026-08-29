# -*- coding: utf-8 -*-
"""
音乐推荐模块 · 数据结构定义
=============================
所有对外暴露的输入/输出类型，保证模块接口清晰。

版本：V1.0 | 2026-07-31
"""
from dataclasses import dataclass, field
from typing import Optional, List


# ═══════════════════════════════════════════════════════════════
# 输入数据结构
# ═══════════════════════════════════════════════════════════════

@dataclass
class ContentContext:
    """内容生成Agent传递给音乐模块的上下文。

    必填字段：
        theme:     本期主题
        body_text: 完整文案正文

    可选字段（有则更准，无则模块自动推断）：
        mood:       内容情绪，None 时模块自动从正文推断
        scene_type: 场景类型，None 时模块自动从关键词推断
        difficulty: 遇到的困难，辅助情绪判断
        tags:       内容标签列表
    """
    theme: str
    body_text: str
    mood: Optional[str] = None
    scene_type: Optional[str] = None
    difficulty: Optional[str] = None
    tags: List[str] = field(default_factory=list)


@dataclass
class UserProfile:
    """用户个人定位信息（从创作者档案读取，未来扩展用）。

    当前版本不强制传入，作为未来用户偏好学习的预留接口。
    """
    account_type: str = "AI学习成长记录"
    content_pillars: List[str] = field(
        default_factory=lambda: ["学习记录", "代码实操", "生活成长"]
    )
    age: int = 20
    preferred_moods: List[str] = field(default_factory=list)


@dataclass
class RecommendRequest:
    """音乐推荐模块的完整输入。

    示例：
        request = RecommendRequest(
            content=ContentContext(
                theme="用AI三小时学完Python基础",
                body_text="04年出生。我开始认真做AI项目...",
                mood="growth",
                tags=["AI学习", "Python入门"]
            ),
            top_k=3
        )
    """
    content: ContentContext
    user: Optional[UserProfile] = None
    top_k: int = 3
    include_reasoning: bool = True


# ═══════════════════════════════════════════════════════════════
# 输出数据结构
# ═══════════════════════════════════════════════════════════════

@dataclass
class MusicTrack:
    """单首音乐的信息。"""
    track_id: str
    name: str
    artist: str
    source: str
    mood_tags: List[str] = field(default_factory=list)
    scene_tags: List[str] = field(default_factory=list)
    tempo: Optional[str] = None
    energy: Optional[str] = None
    duration_sec: Optional[int] = None
    clip_start_sec: Optional[int] = None
    clip_end_sec: Optional[int] = None
    popularity: Optional[str] = None           # 如 "8500w+"


@dataclass
class MusicRecommendation:
    """单条推荐结果。"""
    rank: int
    track: MusicTrack
    match_score: float
    match_reasons: List[str]
    search_hint: str


@dataclass
class RecommendResult:
    """音乐推荐模块的完整输出。

    - recommendations: TopK 推荐列表，按匹配得分降序
    - primary_mood:   最终判定的主要情绪
    - confidence:     推荐置信度 0.0~1.0
    - fallback_used:  是否使用了兜底策略
    - generated_at:   ISO 8601 生成时间
    """
    recommendations: List[MusicRecommendation]
    primary_mood: str
    confidence: float
    fallback_used: bool
    generated_at: str


# ═══════════════════════════════════════════════════════════════
# 兼容旧格式输出（用于 publish_package.json 的 content.bgm）
# ═══════════════════════════════════════════════════════════════

def to_legacy_bgm(result: RecommendResult) -> dict:
    """将推荐结果转换为 V1.5 兼容的 bgm 字典格式。

    取排名第一的推荐，展平为旧格式字段。
    如果无推荐结果，返回兜底默认。
    """
    if not result.recommendations:
        return _default_legacy_bgm()

    top = result.recommendations[0]
    t = top.track

    return {
        "name": t.name,
        "artist": t.artist,
        "search_keyword": top.search_hint.replace("抖音搜索：", ""),
        "reason": top.match_reasons[0] if top.match_reasons else "智能推荐",
        "clip_suggestion": (
            f"{t.clip_start_sec}s-{t.clip_end_sec}s"
            if t.clip_start_sec is not None and t.clip_end_sec is not None
            else "副歌部分约30-60秒"
        ),
        # 保留完整推荐列表供进阶使用
        "_recommendations": [
            {
                "rank": r.rank,
                "name": r.track.name,
                "artist": r.track.artist,
                "score": round(r.match_score, 2),
                "search_hint": r.search_hint,
            }
            for r in result.recommendations
        ],
    }


def _default_legacy_bgm():
    return {
        "name": "起风了",
        "artist": "买辣椒也用券",
        "search_keyword": "起风了 买辣椒也用券",
        "reason": "默认推荐：温暖励志，适合成长记录内容",
        "clip_suggestion": "副歌部分约50-80秒",
        "_recommendations": [],
    }


def to_display_list(result: RecommendResult) -> list:
    """转换为 generator.py 旧 BGM 返回格式的兼容列表。

    返回格式：[(display_name, search_hint, reason, clip), ...]
    用于 build_package() 中生成 文案与发布清单.md 的 BGM 推荐部分。
    """
    items = []
    for r in result.recommendations:
        t = r.track
        display = f"{t.name} - {t.artist}" if t.artist != "纯音乐" else t.name
        search = f"抖音搜索：{t.name} {t.artist}" if t.artist != "纯音乐" else f"抖音搜索：{t.name}"
        reason = r.match_reasons[0] if r.match_reasons else "智能推荐"
        clip = ""
        if t.clip_start_sec is not None and t.clip_end_sec is not None:
            clip = f"{t.clip_start_sec}s-{t.clip_end_sec}s"
        items.append((display, search, reason, clip))
    return items
