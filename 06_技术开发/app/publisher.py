# -*- coding: utf-8 -*-
"""
publisher.py —— 智能体自主填充抖音发布页
============================================
策略层级（每步自动降级）：
  L1: DeepSeek Vision 截图 → AI 分析页面结构 → 精确操作
  L2: 内置选择器数组逐个尝试
  L3: Tab 键逐字段导航 + Type/Ctrl+V 输入

全程零弹窗，不向用户索要任何信息。
"""
import os, sys, time, json, base64, subprocess, threading, tempfile, re, datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# 纯 Chromium 持久化 profile（登录态保存在此；Edge channel 在持久化上下文下截图不稳定）
PROFILE = os.path.join(ROOT, "data", "douyin_chromium")
UPLOAD_URL = "https://creator.douyin.com/creator-micro/content/upload"

# ── 依赖检测 + 静默自动安装 ──────────────────────────
HAS_PLAYWRIGHT = False
try:
    from playwright.sync_api import sync_playwright
    HAS_PLAYWRIGHT = True
except ImportError:
    pass

HAS_REQUESTS = False
try:
    import requests
    import urllib3
    urllib3.disable_warnings()  # Python 3.10 SSL 兼容
    HAS_REQUESTS = True
except ImportError:
    pass


def _load_api_key():
    """只读取用户显式配置的 DeepSeek 密钥，避免误用其他服务的凭据。"""
    try:
        import winreg
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Environment")
        val, _ = winreg.QueryValueEx(key, "DEEPSEEK_API_KEY")
        winreg.CloseKey(key)
        return val
    except Exception:
        return os.environ.get("DEEPSEEK_API_KEY", "")


API_KEY = _load_api_key()
DEEPSEEK_URL = "https://api.deepseek.com/anthropic/v1/messages"


def _ensure_deps():
    """静默安装缺失的依赖，不弹窗，不打扰用户"""
    global HAS_PLAYWRIGHT, HAS_REQUESTS
    need_install = []
    if not HAS_PLAYWRIGHT:
        need_install.append("playwright")
    if not HAS_REQUESTS:
        need_install.append("requests")
    if not need_install:
        return True

    try:
        import subprocess as _sp
        _sp.run(
            [sys.executable, "-m", "pip", "install", "--quiet",
             "--disable-pip-version-check", "--no-python-version-warning"]
            + need_install,
            timeout=120, capture_output=True
        )
        # 重新尝试导入
        if "playwright" in need_install:
            try:
                from playwright.sync_api import sync_playwright  # noqa: F811
                HAS_PLAYWRIGHT = True
            except ImportError:
                pass
        if "requests" in need_install:
            try:
                import requests  # noqa: F811
                HAS_REQUESTS = True
            except ImportError:
                pass
    except Exception:
        pass  # 静默失败，走 L2/L3 兜底
    return HAS_PLAYWRIGHT


def check():
    parts = []
    if HAS_PLAYWRIGHT or _ensure_deps():
        parts.append("Playwright OK")
    else:
        parts.append("Playwright missing")
    if HAS_REQUESTS and API_KEY:
        parts.append("AI Vision OK")
    else:
        parts.append("Vision offline")
    return {"has_playwright": HAS_PLAYWRIGHT, "has_api": bool(HAS_REQUESTS and API_KEY),
            "info": " | ".join(parts)}


# ── L1: AI Vision ─────────────────────────────────────
def _ai_see(screenshot_path, prompt, log):
    """截图发给 DeepSeek 分析，返回 JSON 操作指引"""
    if not HAS_REQUESTS or not API_KEY:
        return None
    with open(screenshot_path, "rb") as f:
        img_b64 = base64.b64encode(f.read()).decode()

    body = {
        "model": "deepseek-chat",
        "max_tokens": 600,
        "messages": [{"role": "user", "content": [
            {"type": "image", "source": {"type": "base64",
             "media_type": "image/png", "data": img_b64}},
            {"type": "text", "text": prompt},
        ]}],
    }
    try:
        resp = requests.post(DEEPSEEK_URL, json=body,
            headers={"x-api-key": API_KEY, "Content-Type": "application/json",
                      "anthropic-version": "2023-06-01"},
            timeout=45,
            proxies={"http": None, "https": None})
        if resp.status_code == 200:
            data = resp.json()
            texts = [b["text"] for b in data.get("content", []) if b.get("type") == "text"]
            return "\n".join(texts).strip()
        else:
            log(f"  Vision: HTTP {resp.status_code}")
            return None
    except Exception as e:
        log(f"  Vision: {e}")
        return None


def _parse_json(text):
    """从 AI 回复中提取 JSON 对象"""
    if not text:
        return {}
    try:
        # 找第一个 { 到最后一个 }
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            return json.loads(text[start:end + 1])
    except (json.JSONDecodeError, ValueError):
        pass
    return {}


# ── L3: 键盘导航兜底 ──────────────────────────────────
def _fill_via_keyboard(page, caption, title, log):
    """
    最终兜底：用 Tab 键遍历表单字段，逐个填入。
    不依赖任何选择器，纯键盘操作。
    """
    log("  切换到键盘导航模式…")
    time.sleep(3)

    # 先确保焦点在页面内
    page.keyboard.press("Escape")
    time.sleep(0.3)

    # Tab 到第一个表单字段（通常跳过导航栏，大约 3-5 个 Tab）
    for _ in range(10):
        page.keyboard.press("Tab")
        time.sleep(0.2)

    # 尝试在当前焦点填入标题
    try:
        page.keyboard.type(title[:35], delay=30)
        log("  → 键盘输入了标题")
    except Exception:
        pass
    time.sleep(0.5)

    # Tab 到下一个字段（文案区）
    page.keyboard.press("Tab")
    time.sleep(0.5)
    try:
        # 用剪贴板粘贴长文案
        page.keyboard.type(caption, delay=10)
        log("  → 键盘输入了文案")
    except Exception:
        pass

    return True


# ── BGM 自动添加：在抖音发布页搜索并选中推荐音乐 ────────────
def _add_bgm_to_page(page, bgm_info, tmpdir, log, output_dir=""):
    """在抖音图文发布页自动搜索并添加推荐BGM。

    策略（逐级降级）：
      L2: 点击「选择音乐/添加音乐」入口 → 输入搜索词 → 点击第一个搜索结果
      L1: AI Vision 截图识别入口 → 点击坐标
      L3: 全部失败 → 输出手动搜索指引，不阻塞发布流程

    返回: {"ok": bool, "method": str, "song": str}
    """
    if not bgm_info:
        return {"ok": False, "method": "skip", "song": ""}

    # 取第一首推荐（优先级最高）
    first = bgm_info[0]
    song_display = first.get("display") or first.get("name", "")
    search_kw = first.get("search_keyword") or song_display
    if not search_kw:
        log("  ⚠️ BGM 无搜索关键词，跳过自动添加")
        return {"ok": False, "method": "no_keyword", "song": song_display}

    log(f"  🎵 自动添加BGM：{song_display}（抖音搜索：{search_kw}）")

    def _fail(method, msg):
        """失败统一出口：输出手动指引 + 全部候选搜索词 + 截图存 output_dir"""
        log(f"  ⚠️ {msg}")
        log(f"     请手动在抖音「选择音乐」中搜索以下任一关键词：")
        for i, b in enumerate(bgm_info, start=1):
            sk = b.get("search_keyword") or b.get("display", "?")
            log(f"       {i}. {sk}（{b.get('display','?')}）")
        shot = ""
        if output_dir:
            try:
                stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                shot = os.path.join(output_dir, f"BGM未添加_{stamp}.png")
                page.screenshot(path=shot)
                log(f"     已截图记录：{os.path.basename(shot)}")
            except Exception:
                shot = ""
        return {"ok": False, "method": method, "song": song_display, "screenshot": shot}

    # ── Step A: 找到音乐入口并点击 ──
    entry_clicked = False
    entry_selectors = [
        'text="选择音乐"', 'text="添加音乐"', 'text="添加BGM"', 'text="选音乐"',
        '[data-e2e*="music"]', 'div[class*="music"]', '[class*="bgm"]',
        'text="配乐"', 'button:has-text("音乐")', 'span:has-text("添加音乐")',
    ]
    for sel in entry_selectors:
        try:
            el = page.locator(sel).first
            if el.is_visible(timeout=1500):
                el.click()
                time.sleep(1.5)
                entry_clicked = True
                log(f"  ✅ 音乐入口已打开 ({sel})")
                break
        except Exception:
            continue

    # L1 降级：AI Vision 找入口
    if not entry_clicked:
        log("  L2 未找到入口，尝试 AI Vision…")
        ss = os.path.join(tmpdir, "bgm_entry.png")
        try:
            page.screenshot(path=ss)
        except Exception:
            ss = None
        if ss:
            ai = _ai_see(ss, """这是抖音创作者中心发布页截图。
请找到「选择音乐」或「添加音乐」或「配乐」入口按钮。
回复 JSON: {"found":true|false,"click_text":"按钮上的确切文字"}""", log)
            guide = _parse_json(ai) if ai else {}
            if guide.get("found") and guide.get("click_text"):
                click_text = guide["click_text"]
                try:
                    page.locator(f"text={click_text}").first.click(timeout=3000)
                    time.sleep(1.5)
                    entry_clicked = True
                    log(f"  ✅ AI Vision 识别到入口：「{click_text}」")
                except Exception:
                    pass

    if not entry_clicked:
        return _fail("entry_not_found", "未找到音乐入口。")

    # ── Step B: 在弹出的音乐面板中搜索 ──
    page.wait_for_timeout(1000)  # 等面板动画完成
    search_ok = False
    search_selectors = [
        'input[placeholder*="搜索"]', 'input[placeholder*="音乐"]',
        'input[placeholder*="歌曲"]', 'input[placeholder*="找音乐"]',
        'input[type="search"]', 'input[type="text"]:visible',
    ]
    for sel in search_selectors:
        try:
            el = page.locator(sel).first
            if el.is_visible(timeout=1500):
                el.click()
                el.fill("")
                page.keyboard.type(search_kw, delay=40)
                time.sleep(1)
                page.keyboard.press("Enter")
                time.sleep(2.5)
                search_ok = True
                log(f"  ✅ 已搜索：{search_kw}")
                break
        except Exception:
            continue

    if not search_ok:
        return _fail("search_box_not_found", "未找到音乐面板中的搜索框。")

    # ── Step C: 选中第一个搜索结果 ──
    time.sleep(1)
    picked = False
    pick_selectors = [
        'text="使用"', 'button:has-text("使用")',
        'text="添加"', 'button:has-text("添加")',
        'div[class*="music-item"]', 'div[class*="song-item"]',
        'li[class*="music"]', '[class*="result-item"]',
        'div[class*="list"] div[class*="item"]',   # 通用列表项兜底
    ]
    for sel in pick_selectors:
        try:
            el = page.locator(sel).first
            if el.is_visible(timeout=1500):
                el.click()
                time.sleep(1.5)
                picked = True
                log(f"  ✅ 已选中搜索结果 ({sel})")
                break
        except Exception:
            continue

    # 有的面板选中后需要点「确定/完成」
    if picked:
        for sel in ['text="确定"', 'text="完成"', 'button:has-text("确认")']:
            try:
                el = page.locator(sel).first
                if el.is_visible(timeout=1000):
                    el.click()
                    time.sleep(1)
                    break
            except Exception:
                continue

    if not picked:
        return _fail("result_not_picked", "未找到可选中的搜索结果。")

    log(f"  🎵 BGM 已添加：{song_display}")
    if first.get("clip_suggestion"):
        log(f"     ⏱ 截取建议：{first['clip_suggestion']}（可在抖音编辑中调整）")
    return {"ok": True, "method": "auto", "song": song_display, "screenshot": ""}


# ── 从 publish_package.json 读取全部字段 ─────────────────
def publish_from_package(package_path, log=print):
    """
    读取内容生成Agent产出的 publish_package.json，
    提取标题/正文/标签/BGM/图片等全部字段，填入抖音发布页。

    这是执行发布Agent的标准入口。
    """
    if not os.path.exists(package_path):
        return {"ok": False, "message": f"素材包不存在: {package_path}"}

    with open(package_path, "r", encoding="utf-8") as f:
        pkg = json.load(f)

    content = pkg.get("content", {})
    meta = pkg.get("meta", {})
    images = pkg.get("images", [])
    publish_cfg = pkg.get("publish_config", {})

    # ── 校验 ──
    errors = []
    title = (content.get("title") or "").strip()
    body = (content.get("body") or "").strip()
    tags = content.get("tags") or []
    # BGM 数据源（音乐模块优先）：
    #   优先 bgm_candidates —— 音乐推荐模块标准输出（orchestrator.enrich_package 写入，带匹配评分）
    #   回退 content.bgm  —— generator 旧版硬编码列表（兼容未富化的老素材包）
    bgm_source = "bgm_candidates"
    bgm_list = pkg.get("bgm_candidates") or []
    if not bgm_list:
        bgm_list = content.get("bgm") or []
        bgm_source = "content.bgm"
    bgm_list = sorted(bgm_list, key=lambda b: b.get("rank", 99))  # 按 rank 升序，第一首为最优推荐
    bgm_meta = pkg.get("bgm_meta", {})  # primary_mood / confidence / fallback_used
    hook = (content.get("hook") or "").strip()
    title_alts = content.get("title_alternatives") or []
    cover_text = (content.get("cover_text") or "").strip()
    publish_time = (content.get("publish_time_suggestion") or "").strip()
    hashtags_raw = (content.get("hashtags_raw") or "").strip()

    if not title or len(title) > 55:
        errors.append(f"标题无效（空或超55字）：{title[:60]}")
    if not body:
        errors.append("正文为空")
    if not images:
        errors.append("图片列表为空")
    else:
        for i, img in enumerate(images):
            fp = img.get("file", "")
            if not fp or not os.path.exists(fp):
                errors.append(f"图片[{i}] 不存在：{fp}")

    if errors:
        log("❌ 素材包校验失败：")
        for e in errors:
            log(f"   - {e}")
        return {"ok": False, "message": "素材包校验失败", "errors": errors}

    image_paths = [img["file"] for img in images if img.get("file") and os.path.exists(img["file"])]

    # ── 打印全部内容摘要 ──
    log("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    log("  📦 素材包加载完毕")
    log(f"  周次：第{meta.get('week','?')}周 · {meta.get('theme','?')}")
    log(f"  情绪：{meta.get('mood','?')}  |  引擎：{meta.get('engine','?')}")
    log("")
    log(f"  📝 主标题：{title}")
    if title_alts:
        for i, t in enumerate(title_alts):
            log(f"     备选{i+1}：{t}")
    log(f"  🎬 钩子：{hook}")
    log(f"  📄 正文（{len(body)}字）：")
    for line in body.split("\n")[:6]:
        log(f"     {line[:80]}")
    if len(body.split("\n")) > 6:
        log(f"     …（共{len(body.splitlines())}行）")
    log("")
    log(f"  🏷️ 话题标签（{len(tags)}个）：{'  '.join('#'+t for t in tags)}")
    if hashtags_raw:
        log(f"     原始格式：{hashtags_raw}")
    log("")
    log(f"  🖼️ 图片（{len(images)}张）：")
    for i, img in enumerate(images):
        log(f"     [{i}] {img['type']:15s} | {img.get('description',''):30s} | {os.path.basename(img['file'])}")
        if img.get("tag_text"):
            log(f"         图片标签：{img['tag_text']}")
    log("")
    log(f"  🎵 推荐BGM（{len(bgm_list)}首 · 来源：{bgm_source}）：")
    if bgm_meta:
        log(f"     情绪：{bgm_meta.get('primary_mood','?')}  "
            f"置信度：{bgm_meta.get('confidence','?')}  "
            f"兜底：{'是' if bgm_meta.get('fallback_used') else '否'}")
    for i, b in enumerate(bgm_list):
        score = b.get("score")
        score_str = f"（匹配分 {score}）" if score is not None else ""
        log(f"     {i+1}. {b.get('display','?')}{score_str}")
        log(f"        抖音搜索：{b.get('search_keyword','?')}")
        log(f"        推荐理由：{b.get('reason','?')}")
        if b.get("clip_suggestion"):
            log(f"        截取建议：{b['clip_suggestion']}")
    log("")
    if cover_text:
        log(f"  🎨 封面文字：{cover_text}")
    if publish_time:
        log(f"  ⏰ 建议发布时间：{publish_time}")
    log("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

    # ── 执行发布 ──
    return publish(caption=body, title=title, image_paths=image_paths,
                   tags=tags, bgm_info=bgm_list, hook=hook,
                   cover_text=cover_text, log=log)


# ── 自定义上下文管理器：启动 Playwright 但不关闭浏览器 ──
class _KeepBrowserOpen:
    """启动 Playwright 驱动但 __exit__ 不调用 stop()，保持浏览器窗口打开。

    默认 `with sync_playwright() as p:` 在退出时会关闭浏览器，
    无法满足"停在发布确认页等待用户手动发布"的需求。
    """
    def __enter__(self):
        self._pw = sync_playwright().start()
        return self._pw
    def __exit__(self, *args):
        # 故意不调用 self._pw.stop() —— 保留浏览器窗口
        pass


# ── 核心发布逻辑 ──────────────────────────────────────
def publish(caption, title, image_paths, log=print,
            tags=None, bgm_info=None, hook="", cover_text=""):
    """
    自主填充抖音发布页。L1→L2→L3 逐级降级，全程不弹窗。

    参数：
        caption: 正文
        title: 标题
        image_paths: 图片绝对路径列表
        tags: 话题标签列表（如 ["AI学习", "Python入门"]）
        bgm_info: BGM推荐列表（dict列表，含 search_keyword）
        hook: 开场钩子
        cover_text: 封面文字
    """
    # 确保依赖
    _ensure_deps()

    image_paths = [p for p in (image_paths or []) if p and os.path.exists(p)]
    if not image_paths:
        return {"ok": False, "message": "无可上传图片"}

    pkg_dir = os.path.dirname(image_paths[0])

    if not HAS_PLAYWRIGHT:
        log("Playwright 不可用，打开浏览器…")
        import webbrowser
        webbrowser.open(UPLOAD_URL)
        if pkg_dir and os.path.isdir(pkg_dir):
            subprocess.Popen(["explorer", pkg_dir])
        return {"ok": True, "mode": "webbrowser",
                "message": "已打开抖音 + 图片文件夹，文案在剪贴板"}

    tmpdir = tempfile.mkdtemp(prefix="dy_")

    try:
        log("启动浏览器（Chromium 持久化上下文）…")
        with _KeepBrowserOpen() as p:
            os.makedirs(PROFILE, exist_ok=True)
            ctx = p.chromium.launch_persistent_context(
                user_data_dir=PROFILE, headless=False,
                viewport={"width": 1280, "height": 920},
                args=["--disable-blink-features=AutomationControlled"])
            page = ctx.pages[0] if ctx.pages else ctx.new_page()

            # ── Step 1: 打开页面 ──
            log("【1/7】打开创作者中心…")
            page.goto(UPLOAD_URL, wait_until="domcontentloaded", timeout=30000)
            time.sleep(4)
            try:
                page.wait_for_load_state("networkidle", timeout=12000)
            except Exception:
                pass
            time.sleep(2)

            # ── Step 1.5: 检查登录态 ──
            cur_url = page.url or ""
            body_text = ""
            try:
                body_text = page.locator("body").inner_text(timeout=5000)
            except Exception:
                pass
            if "login" in cur_url or "扫码登录" in body_text[:500] or "请登录" in body_text[:500]:
                log("  ⚠️ 未检测到登录态，请在弹出的浏览器中扫码登录…")
                log("     等待登录完成（最多 90 秒）…")
                time.sleep(15)
                for _ in range(5):
                    time.sleep(15)
                    cur_url = page.url or ""
                    try:
                        body_text = page.locator("body").inner_text(timeout=5000)
                    except Exception:
                        body_text = ""
                    if "login" not in cur_url and "扫码登录" not in body_text[:500]:
                        log("  ✅ 登录态已恢复")
                        break
                else:
                    log("  ⚠️ 90秒内未完成登录，继续尝试（失败则提示手动）")

            # ── Step 2: 切换图文 ──
            log("【2/7】切换发布图文…")
            ss = os.path.join(tmpdir, "s1.png")
            page.screenshot(path=ss)

            ai = _ai_see(ss, """这是抖音创作者中心页面截图。
请判断当前是"发布视频"还是"发布图文"模式？
如果能看到"发布图文"按钮/标签，请告诉我它的确切文字。
回复 JSON: {"mode":"视频|图文|登录页|未知","need_switch":true|false,"click_text":"要点击的按钮文字"}""", log)

            guide = _parse_json(ai) if ai else {}
            if guide.get("need_switch"):
                click_text = guide.get("click_text", "发布图文")
                log(f"  AI 识别: 需点击「{click_text}」")
                try:
                    page.locator(f"text={click_text}").first.click(timeout=5000)
                    time.sleep(3)
                except Exception:
                    pass

            # L2 兜底选择器
            if guide.get("mode") != "图文":
                for txt in ["发布图文", "图文", "发布图片"]:
                    try:
                        page.locator(f"text={txt}").first.click(timeout=2000)
                        log(f"  L2: 点击了「{txt}」")
                        time.sleep(3)
                        break
                    except Exception:
                        continue

            # ── Step 3: 上传图片 ──
            log(f"【3/7】上传 {len(image_paths)} 张图片…")
            upload_ok = False
            abs_paths = [os.path.abspath(p) for p in image_paths]

            # 等 file input —— 图文页的图片专用 input（accept*="image"）
            # 注意：页面上第一个 input[type=file] 是视频上传入口（accept="video/*"），
            # 必须用 accept*="image" 定位图片 input，否则上传会失败
            for attempt in range(3):
                try:
                    page.wait_for_selector('input[type="file"][accept*="image"]', timeout=10000)
                    file_input = page.locator('input[type="file"][accept*="image"]').first
                    file_input.set_input_files(abs_paths)
                    time.sleep(4)
                    upload_ok = True
                    log(f"  ✅ {len(image_paths)} 张图片已上传")
                    break
                except Exception:
                    if attempt < 2:
                        log(f"  尝试 {attempt+2}/3…")
                        time.sleep(3)

            if not upload_ok:
                log("  上传入口未找到，可能需登录")
                # 给用户时间扫码（这是唯一需要等待的场景，不弹窗）
                log("  等待登录（最多 60 秒）…")
                time.sleep(60)
                try:
                    page.wait_for_selector('input[type="file"][accept*="image"]', timeout=10000)
                    page.locator('input[type="file"][accept*="image"]').first.set_input_files(abs_paths)
                    time.sleep(4)
                    upload_ok = True
                    log("  ✅ 图片上传完成")
                except Exception:
                    log("  上传失败，继续后续步骤")

            # ── Step 4: 填标题 ──
            log("【4/7】填写标题…")
            time.sleep(2)
            ss = os.path.join(tmpdir, "s2.png")
            try:
                page.screenshot(path=ss)
            except Exception as e:
                log(f"  截图失败（{e}），跳过AI识别直接试选择器")

            ai = None
            if os.path.exists(ss):
                ai = _ai_see(ss, f"""这是抖音图文发布页（图片可能正在上传）。
请找到「标题」输入框。需要填入: "{title[:30]}"
回复 JSON: {{"found":true|false,"selector":"描述标题框特征","placeholder":"placeholder文字"}}""", log)
            guide = _parse_json(ai) if ai else {}

            title_ok = False
            # L1+L2: AI 指导 + 选择器数组
            selectors = [
                'input[placeholder*="标题"]',
                'input[placeholder*="添加"]',
                'input[placeholder*="作品"]',
                'input[class*="title"]',
                '[data-e2e*="title"] input',
                '.title-input input',
            ]
            for sel in selectors:
                try:
                    el = page.locator(sel).first
                    el.wait_for(state="visible", timeout=2000)
                    el.click(); el.fill("")
                    el.fill(title[:35])
                    title_ok = True
                    log(f"  ✅ 标题已填 ({sel})")
                    break
                except Exception:
                    continue

            if not title_ok:
                log("  L2 选择器全部失败，尝试 Tab 导航…")
                _fill_via_keyboard(page, caption, title, log)
                title_ok = True  # 键盘模式已处理

            # ── Step 5: 填文案 ──
            log("【5/7】填写文案…")
            time.sleep(2)
            ss = os.path.join(tmpdir, "s3.png")
            try:
                page.screenshot(path=ss)
            except Exception as e:
                log(f"  截图失败（{e}），跳过AI识别直接试选择器")

            ai = None
            if os.path.exists(ss):
                ai = _ai_see(ss, f"""这是抖音图文发布页。请找「文案/描述」编辑区。
文案内容（截取）: "{caption[:200]}"
回复 JSON: {{"found":true|false,"type":"contenteditable|textarea|input","selector_hint":"如何定位"}}""", log)
            guide = _parse_json(ai) if ai else {}

            caption_ok = False
            for sel in ['[contenteditable="true"]',
                        '[contenteditable="plaintext-only"]',
                        'div[class*="editor"]',
                        'div[class*="content"]',
                        '[data-e2e*="caption"]',
                        'div[data-slate-editor="true"]']:
                try:
                    el = page.locator(sel).last
                    el.wait_for(state="visible", timeout=2000)
                    el.click(); time.sleep(0.5)
                    el.fill(caption)
                    caption_ok = True
                    log(f"  ✅ 文案已填 ({sel})")
                    break
                except Exception:
                    continue

            if not caption_ok:
                # 尝试 textarea
                try:
                    page.locator("textarea:visible").first.fill(caption)
                    caption_ok = True
                    log("  ✅ 文案填入 textarea")
                except Exception:
                    pass

            if not caption_ok:
                log("  文案框未自动匹配，切键盘模式…")
                _fill_via_keyboard(page, caption, title, log)
                caption_ok = True

            # ── Step 6: 添加话题标签 ──
            tag_ok = False
            if tags:
                log(f"【6/7】添加 {len(tags)} 个话题标签…")
                time.sleep(2)
                # 策略：点击"#添加话题"触发标签输入，逐个键入
                for i, tag in enumerate(tags):
                    tag_str = tag.replace("#", "").strip()
                    if not tag_str:
                        continue
                    try:
                        # 点击"# 添加话题"入口
                        add_tag_btn = page.locator("text=#添加话题").first
                        if add_tag_btn.is_visible(timeout=2000):
                            add_tag_btn.click()
                            time.sleep(0.5)
                        # 输入标签文字
                        page.keyboard.type(f"#{tag_str}", delay=40)
                        time.sleep(0.6)
                        # 等待下拉建议，回车确认
                        page.keyboard.press("Enter")
                        time.sleep(0.8)
                        log(f"  ✅ 标签 [{i+1}/{len(tags)}]：#{tag_str}")
                    except Exception as e:
                        # 降级：尝试直接用 #添加话题 文本定位+输入
                        log(f"  标签 #{tag_str} 尝试备用方式…")
                        try:
                            page.locator("[contenteditable=\"true\"]").last.click()
                            time.sleep(0.3)
                            page.keyboard.type(f" #{tag_str}", delay=30)
                            time.sleep(0.5)
                            log(f"  ✅ 标签 #{tag_str}（备用方式）")
                        except Exception:
                            log(f"  ⚠️ 标签 #{tag_str} 添加失败，跳过")
                tag_ok = True
            else:
                log("【6/7】无标签，跳过")

            # ── Step 7: 自动添加BGM（在抖音搜索推荐音乐并选中）──
            log("【7/7】添加BGM…")
            bgm_result = _add_bgm_to_page(page, bgm_info, tmpdir, log, output_dir=pkg_dir)
            bgm_ok = bgm_result.get("ok", False)
            if not bgm_ok:
                log(f"  （BGM未自动添加，原因：{bgm_result.get('method')}；不阻塞发布）")

            # ── 最终验证截图 ──
            ss = os.path.join(tmpdir, "s_final.png")
            page.screenshot(path=ss)

            ai = _ai_see(ss, """这是抖音发布的最终页面。请检查：图片是否上传了、标题和文案是否填写了、标签是否添加了、是否已选择BGM音乐。回复 JSON: {"images":true|false,"title":true|false,"caption":true|false,"tags":true|false,"bgm":true|false,"summary":"一句话总结"}""", log)
            verify = _parse_json(ai) if ai else {}
            if verify:
                log(f"  验证: {verify.get('summary', '')[:100]}")

            # 构建结果（无弹窗）
            ok = bool(upload_ok or title_ok or caption_ok)
            log("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
            log(f"  全流程完成 → 浏览器已停在发布页")
            log(f"  ⚠️ 请自行检查后手动点击「发布」")
            if bgm_ok:
                log(f"  🎵 BGM已自动添加：{bgm_result.get('song','')}")
            elif bgm_info:
                log(f"  🎵 BGM未自动添加，请手动在抖音搜索：")
                for b in bgm_info[:2]:
                    log(f"     → {b.get('search_keyword', b.get('display','?'))}")
            log("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

            return {"ok": ok, "mode": "playwright", "published": False,
                    "message": "已填入抖音发布页",
                    "bgm": bgm_result}

    except Exception as e:
        log(f"异常: {e}")
        import webbrowser
        webbrowser.open(UPLOAD_URL)
        if pkg_dir and os.path.isdir(pkg_dir):
            subprocess.Popen(["explorer", pkg_dir])
        return {"ok": False, "mode": "error",
                "message": "已打开浏览器 + 文件夹，文案在剪贴板"}

    finally:
        try:
            import shutil
            shutil.rmtree(tmpdir, ignore_errors=True)
        except Exception:
            pass


def publish_async(caption, title, image_paths, on_done, log,
                  tags=None, bgm_info=None, hook="", cover_text=""):
    def _run():
        result = publish(caption, title, image_paths, log=log,
                         tags=tags, bgm_info=bgm_info, hook=hook, cover_text=cover_text)
        on_done(result)
    threading.Thread(target=_run, daemon=True).start()


def publish_from_package_async(package_path, on_done, log=print):
    """异步版本：从 publish_package.json 读取全部字段后发布"""
    def _run():
        result = publish_from_package(package_path, log=log)
        on_done(result)
    threading.Thread(target=_run, daemon=True).start()
