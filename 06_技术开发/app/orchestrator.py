# -*- coding: utf-8 -*-
"""
orchestrator.py —— 主控Agent（编排层）
=================================================
串起 内容生成 → 成品打包 → 情绪分析 → 音乐推荐 → 素材包富化 的完整流程。

对外两个入口：
  - enrich_package(plan, package_dir)：给素材包附加 analysis + bgm_candidates
    （纯数据层，不生成内容，可安全重复调用）
  - run_creation_flow(...)：完整创作流程（生成 → 打包 → 富化），
    GUI 和命令行都可调用

设计原则（遵循《产品整合设计方案》第八章）：
  - 不改 generator / publisher 引擎，只编排调用
  - 模块间只通过素材包（publish_package.json）通信
  - 任一子步骤失败不阻断整体（返回状态 + 可回退）

版本：V1.0 | 2026-07-31
"""
import os

import generator as G
import package as PKG
import analysis as ANA
from music_recommender import recommend_from_analysis


# ═══════════════════════════════════════════════════════════════
# 素材包富化：附加音乐模块输入/输出
# ═══════════════════════════════════════════════════════════════

def enrich_package(plan: dict, package_dir: str = "") -> dict:
    """给素材包附加 analysis（音乐输入）+ bgm_candidates（音乐输出）。

    Args:
        plan:        生成引擎 plan（含 package_dir / theme / caption 等）
        package_dir: 成品包目录（默认取 plan["package_dir"]）

    Returns:
        富化后的素材包 dict；失败时返回空 dict（不阻断主流程）。

    调用方可用素材包校验 / 摘要：
        pkg = PKG.PublishPackage(data=orchestrator.enrich_package(plan))
        errors = pkg.validate()
        summary = pkg.summary()
    """
    pkg_dir = package_dir or (plan or {}).get("package_dir", "")
    if not pkg_dir or not os.path.isdir(pkg_dir):
        return {}

    # ① 读取 generator 产出的素材包（契约模型）
    pkg_path = os.path.join(pkg_dir, PKG.PACKAGE_FILENAME)
    try:
        if os.path.exists(pkg_path):
            pkg = PKG.PublishPackage.load(pkg_path)
        else:
            return {}  # 素材包文件缺失，交给调用方决定（生成流程总会写出）
    except Exception:
        return {}

    # ② 派生 analysis（0 token，复用生成结果）
    analysis = ANA.build_analysis(plan, G.load_settings())

    # ③ 音乐推荐（标准接口，失败返回空候选）
    music = recommend_from_analysis(analysis, top_k=3)

    # ④ 写回素材包
    pkg.set_analysis(analysis)
    pkg.set_bgm_candidates(music.get("bgm_candidates", []), meta={
        "primary_mood": music.get("primary_mood", analysis.get("emotion", "")),
        "confidence": music.get("confidence", 0.0),
        "fallback_used": music.get("fallback_used", True),
        "recommended_at": __import__("datetime").datetime.now().isoformat(),
    })
    try:
        pkg.save()
    except Exception:
        pass  # 写回失败不影响已生成内容

    return pkg.data


# ═══════════════════════════════════════════════════════════════
# 完整创作流程（主控Agent 主入口）
# ═══════════════════════════════════════════════════════════════

def run_creation_flow(week, theme, learned="", completed="", difficulty="",
                      code_paths=None, extra_paths=None,
                      template_path="", tagline="",
                      use_api=True) -> dict:
    """完整内容创作流程。

    步骤：
      1. generate_plan：离线模板生成方案（0 token）
      2. api_enhance：可选 API 润色（失败自动回退离线）
      3. build_package：封面/代码标签/生活照排版 + 素材包落盘
      4. enrich_package：附加 analysis + bgm_candidates

    Returns:
        {
            "ok": True|False,
            "plan": plan,            # 生成引擎完整方案
            "package": 素材包 dict,   # 富化后的 publish_package.json 内容
            "package_dir": 成品包目录,
            "error": 失败原因(可选),
        }

    说明：本函数只负责「生成」到「素材包就绪」，不负责发布。
    发布由执行发布引擎接管（审核通过后调用）。
    """
    result = {"ok": False, "plan": None, "package": {}, "package_dir": ""}

    # ── Step 1: 生成方案 ──
    try:
        plan = G.generate_plan(
            week, theme, learned, completed, difficulty,
            extra_count=len(extra_paths or []),
            code_count=len(code_paths or []),
        )
    except Exception as e:
        result["error"] = f"生成方案失败：{e}"
        return result

    # ── Step 2: API 润色（可选，失败自动回退离线） ──
    if use_api:
        enhanced = G.api_enhance(plan)
        if enhanced:
            plan["caption"] = enhanced
            plan["engine"] = "api"

    # ── Step 3: 成品打包（封面/标签/排版 + publish_package.json） ──
    try:
        G.build_package(plan, list(code_paths or []), list(extra_paths or []),
                        template_path or "", tagline or "")
    except Exception as e:
        result["error"] = f"成品打包失败：{e}"
        result["plan"] = plan
        return result

    # ── Step 4: 素材包富化（analysis + bgm_candidates） ──
    package = enrich_package(plan)

    result.update({
        "ok": True,
        "plan": plan,
        "package": package,
        "package_dir": plan.get("package_dir", ""),
    })
    return result


# ═══════════════════════════════════════════════════════════════
# 命令行自检：验证契约层可独立运行（无 GUI）
# ═══════════════════════════════════════════════════════════════

def selftest() -> int:
    """集成自检：跑通 生成→打包→分析→音乐→素材包 全流程，不发布。
    自检会创建测试成品包，运行结束后自动清理，不污染真实输出目录。"""
    import shutil
    from PIL import Image
    import tempfile

    tmp = tempfile.mkdtemp(prefix="orch_selftest_")
    def mk(name, color=(24, 26, 38)):
        p = os.path.join(tmp, name)
        Image.new("RGB", (720, 1280), color).save(p)
        return p

    code = [mk("code1.png"), mk("code2.png", (40, 40, 60))]
    extras = [mk("life1.jpg", (90, 60, 40))]

    print("== 编排层自检 (orchestrator.selftest) ==")
    r = run_creation_flow(
        6, "RAG检索增强", "调用DeepSeek API\n搭建向量数据库",
        "第一个AI聊天机器人", "RAG召回率不稳定",
        code_paths=code, extra_paths=extras,
        use_api=False,  # 离线自检
    )
    if not r["ok"]:
        print("FAIL:", r.get("error", "未知错误"))
        return 1

    plan = r["plan"]
    pkg = PKG.PublishPackage(data=r["package"])
    errors = pkg.validate()
    summary = pkg.summary()

    print(f"[1/4] 生成：标题={len(plan.get('titles', []))} 个 · 情绪={plan.get('mood')} · BGM={len(plan.get('bgm', []))} 首")
    print(f"[2/4] 打包：{r['package_dir']}")
    print(f"[3/4] 素材包校验：{'PASS' if not errors else 'FAIL ' + str(errors)}")
    print(f"     摘要：图片{summary['image_count']}张 标题{len(summary['title'])}字 "
          f"标签{summary['tags_count']}个 BGM={summary['bgm_name']}")
    print(f"[4/4] analysis={r['package'].get('analysis', {}).get('emotion')}/{r['package'].get('analysis', {}).get('scene')} "
          f"bgm_candidates={len(r['package'].get('bgm_candidates', []))} 首")

    a = r["package"].get("analysis", {})
    bc = r["package"].get("bgm_candidates", [])
    ok = (not errors and a.get("emotion") and bc and len(bc) >= 1)

    # ── 清理测试产物（成品包目录 + 临时测试图） ──
    pkg_dir = r.get("package_dir", "")
    if pkg_dir and os.path.isdir(pkg_dir) and "orch_selftest" in tmp:
        try:
            shutil.rmtree(pkg_dir)
        except Exception:
            pass
    try:
        shutil.rmtree(tmp)
    except Exception:
        pass

    print("== 编排层自检：", "PASS" if ok else "FAIL", "==")
    return 0 if ok else 1


if __name__ == "__main__":
    import sys
    sys.exit(selftest())
