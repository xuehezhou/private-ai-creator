# -*- coding: utf-8 -*-
"""
package.py —— 素材包模型（模块间唯一数据契约）
=================================================
publish_package.json 是三个模块之间的标准数据接口：
  内容生成引擎 ──► 素材包 ◄── 音乐推荐模块 ──► 执行发布引擎

本模块提供：
  - PublishPackage：素材包数据模型（读 / 写 / 校验 / 富化）
  - load()：读取素材包
  - save()：写回素材包
  - validate()：发布前校验清单（与执行发布Agent一致）
  - set_analysis() / set_bgm_candidates()：附加音乐模块的输入输出
  - find_latest()：定位最新素材包

设计原则（遵循《产品整合设计方案》第六章）：
  - 不修改 generator.py 现有输出字段（向后兼容）
  - 新增 analysis / bgm_candidates 字段，对执行发布引擎透明（多余字段不读）
  - 本模块不 import generator / publisher，保持零依赖的纯数据契约

版本：V1.0 | 2026-07-31
"""
import os
import json
import datetime
from dataclasses import dataclass, field
from typing import Optional, List

PACKAGE_VERSION = "2.0"
PACKAGE_FILENAME = "publish_package.json"

# 素材包固定发布配置（抖音图文 · 人工确认模式）
DEFAULT_PUBLISH_CONFIG = {
    "platform": "douyin",
    "content_type": "image_text",
    "publish_mode": "manual_confirm",
    "enable_comment": True,
    "enable_download": False,
}


@dataclass
class PublishPackage:
    """素材包数据模型。

    data 是对 publish_package.json 的完整映射。
    访问器提供类型化读取，直接操作 data 亦可（字典与 JSON 一一对应）。
    """

    data: dict = field(default_factory=dict)

    # ── 类型化访问器 ──────────────────────────────────────────
    @property
    def content(self) -> dict:
        return self.data.get("content", {})

    @property
    def meta(self) -> dict:
        return self.data.get("meta", {})

    @property
    def images(self) -> List[dict]:
        return self.data.get("images", [])

    @property
    def analysis(self) -> dict:
        """音乐模块输入：情绪/场景/内容类型/账号定位"""
        return self.data.get("analysis", {})

    @property
    def bgm_candidates(self) -> List[dict]:
        """音乐模块输出：Top3 BGM 候选列表"""
        return self.data.get("bgm_candidates", [])

    @property
    def bgm_meta(self) -> dict:
        """音乐推荐元信息：primary_mood / confidence / fallback_used"""
        return self.data.get("bgm_meta", {})

    @property
    def publish_config(self) -> dict:
        return self.data.get("publish_config", {})

    @property
    def output_dir(self) -> str:
        return self.data.get("output_dir", "")

    # ── 读 / 写 / 校验 ─────────────────────────────────────────

    @classmethod
    def load(cls, path: str) -> "PublishPackage":
        """从磁盘读取素材包。"""
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return cls(data=data)

    def save(self, path: Optional[str] = None) -> str:
        """写回素材包（原子写入：先写临时文件再替换，避免中断损坏）。"""
        target = path or os.path.join(self.output_dir, PACKAGE_FILENAME)
        os.makedirs(os.path.dirname(target), exist_ok=True)
        tmp = target + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self.data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, target)
        return target

    def validate(self) -> List[str]:
        """发布前自检清单。返回错误列表，空 = 通过。

        规则与《执行发布Agent设计》步骤2一致：
          - 图片 ≥1 且文件存在
          - 标题 1-55 字（抖音图文限制）
          - 正文非空
          - 标签 ≤5 个，每个 ≤10 字
        """
        errors = []
        content = self.content

        title = (content.get("title") or "").strip()
        if not title:
            errors.append("标题为空")
        elif len(title) > 55:
            errors.append(f"标题超55字（当前{len(title)}字）")

        if not (content.get("body") or "").strip():
            errors.append("正文为空")

        tags = content.get("tags") or []
        if len(tags) > 5:
            errors.append(f"标签超过5个（当前{len(tags)}个）")
        for t in tags:
            if len(t) > 10:
                errors.append(f"标签超10字：{t}")

        if not self.images:
            errors.append("图片列表为空")
        else:
            for i, img in enumerate(self.images):
                fp = img.get("file", "")
                if not fp or not os.path.exists(fp):
                    errors.append(f"图片[{i}] 不存在：{fp}")

        return errors

    # ── 富化：附加音乐模块输入/输出 ─────────────────────────────

    def set_analysis(self, analysis: dict) -> "PublishPackage":
        """附加音乐模块输入（emotion/scene/content_type/theme/account_positioning）。"""
        self.data["analysis"] = analysis
        return self

    def set_bgm_candidates(self, candidates: List[dict], meta: Optional[dict] = None) -> "PublishPackage":
        """附加音乐模块输出（Top3 BGM 候选 + 推荐元信息）。"""
        self.data["bgm_candidates"] = candidates or []
        if meta:
            self.data["bgm_meta"] = meta
        return self

    # ── 便捷校验 + 摘要 ────────────────────────────────────────

    def is_valid(self) -> bool:
        return not self.validate()

    def summary(self) -> dict:
        """返回发布确认页可展示的摘要。"""
        content = self.content
        tags = content.get("tags") or []
        bgm_name = ""
        bgm_list = content.get("bgm") or []
        if bgm_list:
            bgm_name = bgm_list[0].get("display") or bgm_list[0].get("name", "")
        return {
            "week": self.meta.get("week", ""),
            "theme": self.meta.get("theme", ""),
            "title": content.get("title", ""),
            "body_len": len(content.get("body") or ""),
            "tags_count": len(tags),
            "image_count": len(self.images),
            "bgm_name": bgm_name,
            "emotion": self.analysis.get("emotion", self.meta.get("mood", "")),
            "scene": self.analysis.get("scene", ""),
            "publish_mode": self.publish_config.get("publish_mode", "manual_confirm"),
            "output_dir": self.output_dir,
        }


# ── 模块级工具函数 ─────────────────────────────────────────────


def find_latest(output_dir: str) -> Optional[str]:
    """在成品包目录中定位最新的 publish_package.json。

    规则：按文件修改时间取最新的一个素材包。
    用于「执行发布引擎」和「历史记录页」快速定位最近一期。
    """
    if not output_dir or not os.path.isdir(output_dir):
        return None
    hits = []
    for root, _dirs, files in os.walk(output_dir):
        if PACKAGE_FILENAME in files:
            p = os.path.join(root, PACKAGE_FILENAME)
            hits.append((os.path.getmtime(p), p))
    if not hits:
        return None
    hits.sort(key=lambda x: -x[0])
    return hits[0][1]


def make_package_id() -> str:
    """生成素材包 ID：时间戳（可读、可排序）。"""
    return datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
