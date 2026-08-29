# -*- coding: utf-8 -*-
"""
音乐推荐模块 · 情绪与场景推断
==============================
当输入 ContentContext 中未提供 mood / scene_type 时，
从正文文本中自动推断。

版本：V1.0 | 2026-07-31
"""
import re
from typing import Optional, Tuple


# ═══════════════════════════════════════════════════════════════
# 情绪推断规则
# ═══════════════════════════════════════════════════════════════

# 情绪标签定义
#   focus   — 专注/技术/代码
#   growth  — 成长/坚持/改变
#   life    — 生活/日常/松弛
#   tech    — 成果/展示/发布
#   warm    — 温暖/感动/陪伴

MOOD_RULES = {
    "focus": {
        "keywords": [
            "代码", "编程", "调试", "bug", "api", "模型", "训练",
            "python", "算法", "函数", "数据库", "部署"
        ],
        "patterns": [
            r"在写", r"在学", r"跑通", r"实现了", r"调试",
            r"报错", r"编译", r"运行", r"终端"
        ],
        "weight": 1.0,
    },
    "growth": {
        "keywords": [
            "成长", "坚持", "改变", "转行", "从零", "开始",
            "进步", "慢慢", "还在学", "普通人", "记录"
        ],
        "patterns": [
            r"第\d+周", r"卡了", r"终于", r"慢慢",
            r"还在学", r"不算", r"不是天才"
        ],
        "weight": 1.0,
    },
    "life": {
        "keywords": [
            "生活", "日常", "咖啡", "放松", "周末", "休息",
            "出门", "室友", "家里", "今天"
        ],
        "patterns": [
            r"出门", r"休息", r"暂停", r"喘口气",
            r"没出门", r"凉透了"
        ],
        "weight": 0.8,
    },
    "tech": {
        "keywords": [
            "项目", "demo", "部署", "上线", "发布", "开源",
            "成果", "展示", "做出来", "完成"
        ],
        "patterns": [
            r"做出来", r"完成了", r"实现了", r"跑通了",
            r"第一个", r"从零到"
        ],
        "weight": 0.9,
    },
    "warm": {
        "keywords": [
            "温暖", "感动", "感谢", "陪伴", "一起", "真好",
            "室友", "朋友", "支持"
        ],
        "patterns": [
            r"谢谢", r"真好", r"庆幸", r"感恩"
        ],
        "weight": 0.7,
    },
}


def infer_mood(body_text: str, difficulty: Optional[str] = None) -> Tuple[str, float]:
    """从正文+困难描述推断情绪类别。

    返回 (mood_label, confidence)

    优先级：
    1. 有困难描述 → growth（卡点=成长叙事）
    2. 关键词+模式匹配 → 取最高分
    3. 默认 → focus
    """
    # 规则0：有困难描述时，growth 是强信号
    if difficulty and difficulty.strip():
        return ("growth", 0.85)

    text = body_text.lower()

    # 计算每种情绪的得分
    scores = {}
    for mood, rules in MOOD_RULES.items():
        score = 0.0

        # 关键词命中
        for kw in rules["keywords"]:
            if kw.lower() in text:
                score += 2.0

        # 模式命中（正则）
        for pat in rules["patterns"]:
            if re.search(pat, text):
                score += 3.0

        # 乘以权重
        scores[mood] = score * rules["weight"]

    # 取最高分
    if not scores or max(scores.values()) == 0:
        # 无任何命中，默认 focus
        return ("focus", 0.30)

    best_mood = max(scores, key=scores.get)
    best_score = scores[best_mood]
    max_possible = max(sum(len(r["keywords"]) * 2 + len(r["patterns"]) * 3
                          for r in MOOD_RULES.values()), 1)

    # 归一化置信度
    confidence = min(best_score / (max_possible * 0.15), 1.0)
    confidence = max(confidence, 0.25)

    return (best_mood, round(confidence, 2))


# ═══════════════════════════════════════════════════════════════
# 场景推断规则
# ═══════════════════════════════════════════════════════════════

# 场景类型定义
#   code_learning — 代码学习/编程
#   project_demo  — 项目展示/成果
#   daily_life    — 日常生活/照片
#   reflection    — 反思/迷茫/感悟
#   achievement   — 完成/突破/里程碑

SCENE_RULES = {
    "code_learning": {
        "keywords": ["代码", "编程", "学习", "python", "api", "算法", "函数"],
        "patterns": [r"在学", r"写代码", r"调试", r"报错"],
        "weight": 1.0,
    },
    "project_demo": {
        "keywords": ["项目", "demo", "成果", "展示", "做出来", "部署"],
        "patterns": [r"运行成功", r"做出来", r"完成了"],
        "weight": 0.9,
    },
    "daily_life": {
        "keywords": ["生活", "日常", "咖啡", "照片", "出门", "室友"],
        "patterns": [r"今天", r"出门", r"家里"],
        "weight": 0.8,
    },
    "reflection": {
        "keywords": ["思考", "迷茫", "方向", "转行", "改变", "意义"],
        "patterns": [r"不知道", r"迷茫", r"在想", r"未来"],
        "weight": 0.85,
    },
    "achievement": {
        "keywords": ["完成", "跑通", "突破", "上线", "里程碑", "终于"],
        "patterns": [r"终于.*了", r"成功了", r"做到了"],
        "weight": 0.9,
    },
}


def infer_scene(body_text: str, theme: str = "") -> Tuple[str, float]:
    """从正文推断场景类型。

    返回 (scene_label, confidence)
    """
    text = f"{theme} {body_text}".lower()

    scores = {}
    for scene, rules in SCENE_RULES.items():
        score = 0.0
        for kw in rules["keywords"]:
            if kw.lower() in text:
                score += 2.0
        for pat in rules["patterns"]:
            if re.search(pat, text):
                score += 3.0
        scores[scene] = score * rules["weight"]

    if not scores or max(scores.values()) == 0:
        return ("code_learning", 0.30)

    best_scene = max(scores, key=scores.get)
    best_score = scores[best_scene]
    confidence = min(best_score / 15.0, 1.0)
    confidence = max(confidence, 0.25)

    return (best_scene, round(confidence, 2))


# ═══════════════════════════════════════════════════════════════
# 关键词提取（从正文中提取可用于匹配的关键词）
# ═══════════════════════════════════════════════════════════════

# 主题关键词黑名单：太通用、无区分度的词
_KEYWORD_BLACKLIST = {
    "我", "的", "了", "是", "在", "这", "那", "他", "她",
    "一个", "这个", "那个", "什么", "怎么", "为什么",
    "可以", "没有", "已经", "还是", "只是", "因为",
    "所以", "但是", "如果", "虽然", "而且", "然后",
    "一", "二", "三", "很多", "一些", "一下",
}


def extract_keywords(body_text: str, tags: list = None, max_kw: int = 15) -> list:
    """从正文提取可用于音乐匹配的关键词。

    策略：
    - 分词 → 去停用词 → 去重 → 取前 N 个
    - 合并用户提供的 tags
    - 中文按常见词长（2-4字）提取
    """
    import re as _re

    keywords = set()

    # 从 tags 中提取
    for tag in (tags or []):
        tag = tag.strip()
        if tag and tag not in _KEYWORD_BLACKLIST:
            keywords.add(tag.lower())

    # 从正文中提取 2-4 字中文词组
    # 简单策略：按标点/空格切片，取 2-4 字片段
    text = _re.sub(r'[^一-鿿\w]', ' ', body_text)
    for word in text.split():
        word = word.strip().lower()
        if (2 <= len(word) <= 6
                and word not in _KEYWORD_BLACKLIST
                and not word.isdigit()):
            keywords.add(word)

    # 按字数降序排列（长词更有意义），取前 max_kw
    sorted_kw = sorted(keywords, key=lambda w: -len(w))
    return sorted_kw[:max_kw]
