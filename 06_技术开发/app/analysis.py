# -*- coding: utf-8 -*-
"""
analysis.py —— 情绪/场景推断 → 音乐模块输入
=================================================
将内容生成引擎产出的 plan 派生为音乐推荐模块的标准输入 `analysis`：

    {
      "emotion": "growth",               # 内容情绪（复用生成引擎判定，0 token）
      "scene": "code_learning",          # 图片场景（优先复用已有推断）
      "scene_tags": ["学习", "代码"],     # 场景标签（供音乐模块/页面展示）
      "content_type": "image_text",      # 内容类型（抖音图文）
      "theme": "用AI三小时学完Python基础", # 主题关键词
      "tags": ["AI学习", "Python入门"],   # 话题标签
      "account_positioning": "04年AI项目记录",  # 账号定位（来自个人知识库/设置）
      "body_text": "04年出生。…"              # 正文（音乐模块关键词匹配用）
    }

设计原则：
  - 0 token：完全复用生成结果，不新增一次 AI 调用
  - 低耦合：analysis 是纯数据，任何模块（音乐/页面）都能独立消费
  - 容错：缺失字段安全兜底，不影响主流程

版本：V1.0 | 2026-07-31
"""
import os
import re


def _parse_tags(hashtags: str) -> list:
    """将 "#AI学习 #自学编程" 解析为 ["AI学习", "自学编程"]"""
    if not hashtags:
        return []
    return [t.replace("#", "").strip() for t in str(hashtags).split() if t.strip()]


def _infer_scene(plan: dict, caption: str, theme: str) -> str:
    """推断场景类型。

    优先级：
      1. 图片方案里有明确代码图 → code_learning
      2. 有成果/展示关键词 → project_demo
      3. 有生活照关键词 → daily_life
      4. 复用音乐模块场景推断（若可用）
      5. 兜底 code_learning
    """
    text = f"{theme} {caption}".lower()

    # ① 有代码图（生成引擎固定版式里有「代码」条目）
    image_plan = plan.get("image_plan", [])
    if any("代码" in str(p.get("photo", "")) for p in image_plan):
        return "code_learning"

    # ② 成果/展示关键词
    if any(k in text for k in ("项目", "demo", "上线", "做出来", "完成", "成果")):
        return "project_demo"

    # ③ 生活/日常关键词
    if any(k in text for k in ("生活", "日常", "咖啡", "周末", "出门", "室友")):
        return "daily_life"

    # ④ 复用音乐模块场景推断（软依赖，失败则兜底）
    try:
        from music_recommender.mood_inference import infer_scene
        scene, _conf = infer_scene(caption, theme)
        return scene
    except Exception:
        pass

    return "code_learning"


def _scene_tags(plan: dict) -> list:
    """从图片方案/爆款角色中提取场景标签（供展示用）。"""
    tags = []
    image_plan = plan.get("image_plan", [])
    for p in image_plan:
        photo = str(p.get("photo", ""))
        if "封面" in photo:
            tags.append("封面")
        elif "代码" in photo:
            tags.append("代码")
        else:
            tags.append("学习")
    roles = plan.get("roles", [])
    for rname, _desc in roles[:2]:
        if rname and rname not in tags:
            tags.append(rname)
    # 去重保序，最多 5 个
    seen, out = set(), []
    for t in tags:
        if t not in seen:
            seen.add(t); out.append(t)
    return out[:5]


def build_analysis(plan: dict, settings: dict = None) -> dict:
    """从内容生成引擎的 plan 派生音乐模块输入（标准 analysis 契约）。

    Args:
        plan:      generator.generate_plan() / build_package() 产出的方案
        settings:  load_settings() 结果（提供 account_name），可省略

    Returns:
        analysis dict（见模块顶部注释）
    """
    settings = settings or {}
    plan = plan or {}
    theme = plan.get("theme", "")
    caption = plan.get("caption", "")
    hashtags = plan.get("hashtags", "")

    analysis = {
        "emotion": plan.get("mood", "focus"),
        "scene": _infer_scene(plan, caption, theme),
        "scene_tags": _scene_tags(plan),
        "content_type": "image_text",
        "theme": theme,
        "tags": _parse_tags(hashtags),
        "account_positioning": settings.get("account_name", "AI学习成长记录"),
        "body_text": caption,
    }
    return analysis
