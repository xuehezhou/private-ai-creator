# -*- coding: utf-8 -*-
"""
main.py —— AI 抖音创作智能体 · GUI 主程序  (v1.5 固定封面+两键版)
==================================================
照片固定版式（程序自动排版，账号统一）：
  ① 封面 = 固定模板（素材库「第一张图片模板照片」里那张黑底主题照），
           智能体按你填的期数+主题自动改字；你不用传、不用选
  ② 代码 = 你上传 1 张，程序自动打标签
  ③+ 生活/学习照 = 点「＋ 生活/学习照片」一次选多张，智能体按爆款模板自动排序

主界面只有两个添加键：＋代码 / ＋生活/学习照片（另含「📋 照片总览」入口）；
照片总览里包含全部照片：右上角 ✕ 删除、底部按钮添加，排序交给智能体。

命令行：
  python main.py                正常打开
  python main.py --selftest     无界面引擎自检
  python main.py --uitest       用真实照片实测 增/删/换/固定封面（无弹窗）
  python main.py --pubcheck     检查自动发布组件
  python main.py --screenshot X 截主界面 + 照片总览（带确定性布局自检）
"""
import os
import sys
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import generator as G
import publisher as P
import package as PKG          # 素材包契约模型（读/写/校验/摘要）
import orchestrator as ORCH    # 主控Agent（编排层）

try:
    from PIL import Image, ImageTk, ImageDraw
except ImportError:
    Image = ImageTk = ImageDraw = None

try:
    import ctypes
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass

# ── 设计系统令牌（2026-08 界面舒适化）──────────────────────────
# 基调：深夜学习台灯下的创作工作台 —— 柔和雾蓝白底 + 深蓝夜顶栏，
# 抖音红/青只作克制的强调色，让每周创作流程安静、专注、不刺眼。
ROOT_BG   = "#F4F6F8"   # 页面底色：柔和雾蓝白
CARD_BG   = "#FFFFFF"   # 卡片 / 面板
HEADER_BG = "#1B2333"   # 顶栏：深蓝夜
TEXT      = "#1F2430"   # 主文字
GRAY      = "#5C6773"   # 次级文字（比旧版加深，可读性提升）
SOFT      = "#9AA3B2"   # 提示 / 占位文字
LINE      = "#E7EAEF"   # 分隔线 / 发丝线
CYAN      = "#25F4EE"   # 抖音青：强调 / 输入聚焦
RED       = "#F03E57"   # 抖音红：主操作「生成」
GREEN     = "#2BA471"   # 通过 / 确认
TEAL      = "#12949F"   # 封面 / 信息提示
LEAF      = "#178A5C"   # 生活照 / 正向
FONT = "Microsoft YaHei UI"
APP_DIR = os.path.dirname(os.path.abspath(__file__))
ASSETS = os.path.join(APP_DIR, "assets")
LOGO_PATH = os.path.join(ASSETS, "logo.png"); ICON_PATH = os.path.join(ASSETS, "icon.ico")
MAT_DIR = G.MATERIAL_DIR  # 素材库（07_数据资产/图片素材）：固定封面模板/代码截图/生活学习照
OUT_DIR = os.path.join(os.path.dirname(APP_DIR), "output")
IMG_EXT = (".jpg", ".jpeg", ".png", ".bmp", ".webp")


def _thumb_image(path=None, placeholder="", size=(74, 106)):
    """统一缩略图：有真图居中粘贴，否则灰底占位文字"""
    w, h = size
    if path and os.path.exists(path) and Image and ImageTk:
        try:
            im = Image.open(path).convert("RGB"); im.thumbnail((w, h))
            bg = Image.new("RGB", (w, h), (240, 241, 243))
            bg.paste(im, ((w - im.width) // 2, (h - im.height) // 2))
            return ImageTk.PhotoImage(bg)
        except Exception:
            placeholder = "（预览失败）"
    if not (Image and ImageTk):
        return None
    bg = Image.new("RGB", (w, h), (240, 241, 243))
    d = ImageDraw.Draw(bg)
    d.rectangle([0, 0, w - 1, h - 1], outline=(205, 208, 214))
    try:
        font = G._load_cn_font(max(11, h // 8))
    except Exception:
        font = None
    lines = (placeholder or "").split("\n"); lh = max(14, h // 6)
    y = (h - lh * len(lines)) // 2
    for ln in lines:
        d.text(((w - len(ln) * (h // 6)) // 2, y), ln, font=font, fill=(150, 155, 168)); y += lh
    return ImageTk.PhotoImage(bg)


def _latest_template():
    """取模板文件夹里最新改动的那张 ＝ 用户『换好的那个文件』"""
    d = os.path.join(MAT_DIR, "第一张图片模板照片")
    if not os.path.isdir(d):
        return ""
    files = [os.path.join(d, f) for f in os.listdir(d) if f.lower().endswith(IMG_EXT)]
    return max(files, key=os.path.getmtime) if files else ""


def _find_sample_photos():
    """定位用户素材库里的真实照片，供实测/截图使用。extras 为纯路径列表（排序交给智能体）"""
    def first(*subs):
        for sub in subs:
            d = os.path.join(MAT_DIR, sub)
            if os.path.isdir(d):
                for fn in os.listdir(d):
                    if fn.lower().endswith(IMG_EXT):
                        return os.path.join(d, fn)
        return ""
    tmpl = _latest_template()
    code = first("代码截图")
    extras = []
    for sub in ("生活照片", "学习照片"):
        d = os.path.join(MAT_DIR, sub)
        if os.path.isdir(d):
            for fn in sorted(os.listdir(d)):
                if fn.lower().endswith(IMG_EXT):
                    extras.append(os.path.join(d, fn))
    wk = os.path.join(OUT_DIR, "第05周_0728")
    if os.path.isdir(wk) and len(extras) < 2:
        for fn in sorted(os.listdir(wk)):
            if fn.lower().endswith(IMG_EXT) and ("学习" in fn or "生活" in fn):
                extras.append(os.path.join(wk, fn))
            if len(extras) >= 2:
                break
    return tmpl, code, extras[:4]


def _pkg_selfcheck(pkg_dir):
    """发布确认页的素材包自检清单。

    Returns: (checks, errors, summary, pkg)
      checks: [(项目名, 通过bool, 说明str), ...]   # 逐项清单
      errors: [错误描述, ...]                        # 空 = 全部通过
      summary: PublishPackage.summary() 摘要
      pkg:    PublishPackage 对象（无素材包时为 None）
    """
    path = os.path.join(pkg_dir, PKG.PACKAGE_FILENAME) if pkg_dir else ""
    if not path or not os.path.exists(path):
        return ([("素材包文件", False, "未找到 publish_package.json")],
                ["素材包文件缺失"], {}, None)
    try:
        pkg = PKG.PublishPackage.load(path)
    except Exception as e:
        return ([("素材包解析", False, str(e))], [f"素材包解析失败：{e}"], {}, None)

    s = pkg.summary()
    errors = pkg.validate()
    checks = [
        ("图片", len(pkg.images) >= 1, f"{s['image_count']}张"),
        ("标题", 1 <= len(s["title"]) <= 55, f"{len(s['title'])}字"),
        ("正文", s["body_len"] > 0, f"{s['body_len']}字"),
        ("标签", s["tags_count"] <= 5, f"{s['tags_count']}个"),
        ("情绪分析", bool(s["emotion"]), f"{s['emotion'] or '—'}"),
        ("BGM候选", len(pkg.bgm_candidates) >= 1, f"{len(pkg.bgm_candidates)}首"),
    ]
    return checks, errors, s, pkg


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self._app_title = "AI 抖音创作智能体"
        self.title(self._app_title)
        self.configure(bg=ROOT_BG)
        self.geometry("1120x800"); self.minsize(980, 660)
        self._center()
        if os.path.exists(ICON_PATH):
            try:
                self.iconbitmap(ICON_PATH)
            except Exception:
                pass
        self.plan = None
        self._saved = False  # 标记是否已保存，保存后关闭不再提示
        self.code = []  # 代码/项目截图（支持多张，列表）
        self.extras = []
        self._cover_preview = ""
        self._overview = None
        self._strip = None
        self._strip_cells = []
        self._ov_inner = None
        self._ov_canvas = None
        self._ov_cards = []
        self._scroll_canvas = None
        self._learned_entries = []     # 动态标签输入框的 StringVar 列表
        self._learned_container = None # 标签输入框的容器 Frame
        self._old_learned = ""         # 旧版草稿兼容
        self._history_win = None       # 历史记录窗口（M2-2）
        self._publish_log_win = None   # 发布执行日志窗口（M2-1）
        self._load_cover_settings()
        self._ov_tagline_var = tk.StringVar(value=self.tagline)
        self._photo_summary_var = tk.StringVar()
        self._setup_styles(); self._build_header(); self._build_step_strip()
        self._build_body(); self._build_statusbar()
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self._load_draft()
        # Ctrl+S 快捷键保存（和 Word 一样）
        self.bind("<Control-s>", lambda e: self._save_draft())
        self.bind("<Control-S>", lambda e: self._save_draft())
        # 首次运行（未设置输出目录）→ 自动弹出设置窗口
        _s = G.load_settings()
        if not _s.get("output_dir", "").strip():
            self.after(300, lambda: self._open_settings(first_run=True))

    def _load_cover_settings(self):
        # 封面=固定模板（素材库那张黑底主题照），不让用户选；这里只读副标题
        s = G.load_settings()
        self.tagline = s.get("cover_tagline", "转行ing")

    def _save_cover_settings(self):
        s = G.load_settings()
        s.pop("cover_template", None)   # 封面已改为固定模板，不再保存用户选择
        s["cover_tagline"] = self.tagline
        G.save_settings(s)

    # ---------- 草稿保存/加载/关闭 ----------
    def _draft_path(self):
        return os.path.join(G.DATA_DIR, "draft.json")

    def _mark_unsaved(self):
        """标记为未保存状态：标题加 * 号（和 Word 一样）"""
        self._saved = False
        self.title(f"{self._app_title} *")

    def _mark_saved(self):
        """标记为已保存状态：标题去掉 * 号"""
        self._saved = True
        self.title(self._app_title)

    def _save_draft(self, silent=False):
        """保存全部内容（表单 + 编辑后的文案 + BGM + 图片方案），和 Word 的 Ctrl+S 一样
        编辑内容后自动重新计算照片标记建议，使标签与文案保持一致。"""
        import json
        # 先把用户在文案区的编辑同步回 plan（防止编辑丢失）
        if self.plan:
            self._sync_edited_content()

            # ── 保存用户当前的标记面板设置（作为手动覆盖值） ──
            user_marks_snapshot = [
                dict(m) for m in self.plan.get("mark_suggestions", [])
            ]

            # ── 从输入框更新 tag_lines（用户可能改了代码标签） ──
            learned_tags = [v.get().strip() for v in self._learned_entries if v.get().strip()]
            if learned_tags:
                self.plan["tag_lines"] = [t[:12] for t in learned_tags]
                # 同步更新第二张图的标签文字（代码图 = photo_tags[1]）
                pts = self.plan.get("photo_tags", [])
                if len(pts) > 1:
                    pts[1] = learned_tags[0][:12]

            # ── 根据最新内容重新计算标记建议 ──
            code_n = len(self.code) if self.code else 1
            extra_n = len(self.extras)
            fresh_marks = G._suggest_marks(
                {"week": self.plan.get("week", ""),
                 "theme": self.plan.get("theme", ""),
                 "tag_lines": self.plan.get("tag_lines", []),
                 "photo_tags": self.plan.get("photo_tags", []),
                 "roles": self.plan.get("roles", [])},
                code_n, extra_n)

            # ── 合并：用户手动设置优先，AI 理由更新 ──
            merged = []
            for i, fresh in enumerate(fresh_marks):
                if i < len(user_marks_snapshot):
                    old = user_marks_snapshot[i]
                    merged.append({
                        "mark_enabled": old.get("mark_enabled", fresh["mark_enabled"]),
                        "tag_text": old.get("tag_text", "").strip() or fresh["tag_text"],
                        "reason": fresh["reason"],
                    })
                else:
                    merged.append(fresh)
            self.plan["mark_suggestions"] = merged

        data = {
            "week": self.week_var.get(),
            "theme": self.theme_var.get(),
            "learned_tags": [v.get().strip() for v in self._learned_entries],
            "completed": self._get(self.completed_txt),
            "difficulty": self._get(self.difficulty_txt),
            "code": list(self.code),
            "extras": list(self.extras),
            "tagline": self.tagline,
        }
        # 保存已生成的方案（文案、BGM、图片路径等）
        if self.plan:
            data["plan"] = self.plan
        try:
            os.makedirs(G.DATA_DIR, exist_ok=True)
            with open(self._draft_path(), "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            self._mark_saved()
            # 保存后刷新标记面板和图片Tab（文案Tab不刷新，用户正在编辑的可能）
            if self.plan:
                self._render_mark_panel()
                self._refresh_image_tab()
            if not silent:
                self.status_var.set("💾 已保存（含标记更新）")
        except Exception as e:
            if not silent:
                messagebox.showwarning("保存失败", str(e))

    def _load_draft(self):
        """启动时加载草稿（如果存在），含已生成的方案"""
        import json
        dp = self._draft_path()
        if not os.path.exists(dp):
            return
        try:
            with open(dp, "r", encoding="utf-8") as f:
                data = json.load(f)
            if data.get("week"):
                self.week_var.set(data["week"])
            if data.get("theme"):
                self.theme_var.set(data["theme"])
            if data.get("learned"):
                # 兼容旧版草稿：单行文本 → 存下来，等 code 恢复后拆分到各输入框
                self._old_learned = data["learned"]
            else:
                self._old_learned = ""
            if data.get("completed"):
                self.completed_txt.config(state="normal")
                self.completed_txt.delete("1.0", "end")
                self.completed_txt.insert("1.0", data["completed"])
            if data.get("difficulty"):
                self.difficulty_txt.config(state="normal")
                self.difficulty_txt.delete("1.0", "end")
                self.difficulty_txt.insert("1.0", data["difficulty"])
            if data.get("code"):
                self.code = [p for p in data["code"] if os.path.exists(p)]
            if data.get("extras"):
                self.extras = [p for p in data["extras"] if os.path.exists(p)]
            if data.get("tagline"):
                self.tagline = data["tagline"]
                self._ov_tagline_var.set(self.tagline)
            # 重建代码图标签输入框，并恢复已保存的内容
            self._rebuild_learned_fields()
            if data.get("learned_tags"):
                for i, val in enumerate(data["learned_tags"]):
                    if i < len(self._learned_entries):
                        self._learned_entries[i].set(val)
            elif getattr(self, '_old_learned', ''):
                # 兼容旧版草稿（单行文本 → 按行拆分到各输入框）
                old_lines = [ln.strip() for ln in self._old_learned.splitlines() if ln.strip()]
                for i, val in enumerate(old_lines):
                    if i < len(self._learned_entries):
                        self._learned_entries[i].set(val)
            self._refresh_photos()
            self._render_cover_preview()
            # 恢复已生成的方案（文案、BGM、图片）
            if data.get("plan"):
                self.plan = data["plan"]
                if self.plan.get("package_files"):
                    self._cover_preview = self.plan["package_files"][0]
                self._render_plan(self.plan)
                self.confirm_btn.config(state="normal")
                self.nb.select(0)
                self._set_step(2)  # 草稿含方案 → 处于「审核」阶段
            # 有草稿文件 = 已保存过，关闭时不再提示
            self._mark_saved()
        except Exception:
            pass  # 草稿损坏不影响启动

    def _on_close(self):
        """关闭窗口：已保存过则直接关闭，否则询问是否保存"""
        if not self._saved:
            ans = messagebox.askyesnocancel("关闭", "是否保存当前内容？\n\n是 = 保存后关闭\n否 = 不保存直接关闭\n取消 = 返回")
            if ans is None:  # 取消
                return
            if ans:  # 是 → 保存
                self._save_draft(silent=True)
        self._save_cover_settings()
        self.destroy()

    # ---------- 设置窗口：输出目录选择 ----------
    def _open_settings(self, first_run=False):
        """打开设置窗口，让用户选择成品包输出目录 — 大窗口、舒适布局、快捷选盘"""
        top = tk.Toplevel(self)
        top.title("⚙️ 设置")
        top.configure(bg="#F8F9FA"); top.transient(self)
        W, H = 640, 420
        top.geometry(f"{W}x{H}")
        top.resizable(False, False)
        self.update_idletasks()
        x = self.winfo_rootx() + max(0, (self.winfo_width() - W) // 2)
        y = self.winfo_rooty() + max(0, (self.winfo_height() - H) // 2)
        top.geometry(f"+{x}+{y}")
        if os.path.exists(ICON_PATH):
            try: top.iconbitmap(ICON_PATH)
            except Exception: pass

        # 加载设置
        s = G.load_settings()
        current_dir = s.get("output_dir", "").strip() or G.OUTPUT_DIR

        # ===== 底部按钮区（先 pack side=bottom 保证可见） =====
        bf = tk.Frame(top, bg="#F8F9FA")
        bf.pack(side="bottom", fill="x", padx=32, pady=(10, 24))

        def _save_settings():
            new_dir = dir_var.get().strip()
            if not new_dir:
                messagebox.showwarning("提示", "请选择或输入一个输出目录。", parent=top)
                return
            try:
                os.makedirs(new_dir, exist_ok=True)
            except Exception as e:
                messagebox.showerror("无法创建目录", f"{e}\n\n请换一个路径。", parent=top)
                return
            s["output_dir"] = new_dir
            G.save_settings(s)
            top.destroy()
            self.status_var.set(f"✅ 输出目录已设为：{new_dir}")

        def _cancel():
            if first_run:
                # 首次运行也允许跳过（用默认路径）
                if not messagebox.askyesno("跳过设置",
                        "未选择输出目录，将使用默认路径（C盘）。\n\n确定跳过？",
                        parent=top):
                    return
                s["output_dir"] = G.OUTPUT_DIR
                G.save_settings(s)
            top.destroy()

        top.protocol("WM_DELETE_WINDOW", _cancel)

        tk.Button(bf, text="  ✅  保存设置  ", bg=GREEN, fg="#FFFFFF",
                  activebackground="#259E63", relief="flat", font=(FONT, 12, "bold"),
                  pady=12, padx=32, cursor="hand2", command=_save_settings).pack(
                  side="right", padx=(0, 12))
        tk.Button(bf, text="  取消  ", bg="#E8EAED", fg=TEXT,
                  activebackground="#DADCE0", relief="flat", font=(FONT, 11),
                  pady=12, padx=24, cursor="hand2", command=_cancel).pack(
                  side="right")

        # ===== 顶部深色标题栏 =====
        tk.Label(top, text="⚙️  设置", bg=HEADER_BG, fg="#FFFFFF",
                 font=(FONT, 15, "bold")).pack(fill="x", ipady=12)

        # ===== 主内容区（pack top，填充剩余空间） =====
        content = tk.Frame(top, bg="#F8F9FA")
        content.pack(fill="both", expand=True, padx=32, pady=(20, 10))

        # --- 说明 ---
        tk.Label(content, text="📁 成品包输出目录", bg="#F8F9FA", fg=TEXT,
                 font=(FONT, 13, "bold")).pack(anchor="w")
        tk.Label(content, text="生成的封面、标签图、文案等成品文件会保存到此目录。\n建议选择非 C 盘位置，避免占用系统盘空间。",
                 bg="#F8F9FA", fg=GRAY, font=(FONT, 9), justify="left",
                 anchor="w").pack(anchor="w", pady=(6, 16))

        # --- 快捷选盘（检测可用驱动器） ---
        drives_frame = tk.Frame(content, bg="#F8F9FA")
        drives_frame.pack(anchor="w", pady=(0, 14))
        tk.Label(drives_frame, text="快速选择：", bg="#F8F9FA", fg=TEXT,
                 font=(FONT, 9)).pack(side="left")

        import string
        available_drives = []
        for letter in string.ascii_uppercase:
            drv = f"{letter}:\\"
            if os.path.isdir(drv) and letter != "C":
                available_drives.append(letter)

        dir_var = tk.StringVar(value=current_dir)
        path_status_var = tk.StringVar(value="")

        def _quick_select(letter):
            suggested = f"{letter}:\\AI-Douyin-Output"
            dir_var.set(suggested)

        for drv_letter in available_drives[:4]:
            tk.Button(drives_frame, text=f"  {drv_letter}: 盘  ",
                      bg="#E8F4FD", fg="#1976D2", activebackground="#BBDEFB",
                      relief="flat", font=(FONT, 9, "bold"), padx=12, pady=6,
                      cursor="hand2", bd=1,
                      command=lambda l=drv_letter: _quick_select(l)).pack(
                      side="left", padx=(8, 4))
        if not available_drives:
            tk.Label(drives_frame, text="（未检测到其他分区，请手动浏览）", bg="#F8F9FA",
                     fg=GRAY, font=(FONT, 8)).pack(side="left", padx=(8, 0))

        # --- 路径输入行（浏览按钮先 pack right，entry 再 pack left expand） ---
        input_frame = tk.Frame(content, bg="#FFFFFF", relief="solid", bd=1)
        input_frame.pack(fill="x", ipady=2)

        def _browse():
            d = filedialog.askdirectory(title="选择成品包输出目录", parent=top)
            if d:
                dir_var.set(d)

        # 浏览按钮先 pack（side=right），保证不被 entry 挤掉
        tk.Button(input_frame, text="  📁 浏览  ", bg="#F0F2F5", fg=TEXT,
                  activebackground="#E2E5EA", relief="flat", font=(FONT, 10, "bold"),
                  cursor="hand2", padx=16, pady=10, command=_browse).pack(
                  side="right", fill="y")
        # Entry 后 pack（side=left + expand 填充剩余宽度）
        tk.Entry(input_frame, textvariable=dir_var, font=(FONT, 11),
                 relief="flat", padx=12).pack(side="left", fill="x", expand=True, ipady=8)

        # --- 路径验证状态 ---
        path_status_lbl = tk.Label(content, textvariable=path_status_var,
                                   bg="#F8F9FA", fg=GRAY, font=(FONT, 9), anchor="w")
        path_status_lbl.pack(anchor="w", pady=(8, 0))

        def _validate_path(*args):
            p = dir_var.get().strip()
            if not p:
                path_status_var.set("")
                return
            if os.path.isdir(p):
                try:
                    test_f = os.path.join(p, ".write_test")
                    with open(test_f, "w") as f: f.write("ok")
                    os.remove(test_f)
                    path_status_var.set("✅ 路径有效，可写入")
                    path_status_lbl.config(fg=GREEN)
                except Exception:
                    path_status_var.set("⚠️ 路径存在但可能无写入权限")
                    path_status_lbl.config(fg="#E67E22")
            else:
                path_status_var.set("📝 保存时将自动创建此目录")
                path_status_lbl.config(fg="#1976D2")

        dir_var.trace_add("write", _validate_path)
        _validate_path()

        # --- C 盘警告 ---
        if current_dir and current_dir[0:1].upper() == "C":
            tk.Label(content, text="  ⚠️ 当前路径在 C 盘，建议点击上方快捷按钮或浏览更改到其他分区  ",
                     bg="#FFF3E0", fg="#E65100", font=(FONT, 9, "bold"),
                     padx=10, pady=8).pack(fill="x", pady=(14, 0))

    def _fixed_template(self):
        """固定封面模板 = 素材库「第一张图片模板照片」里最新的那张（黑底主题照）；
        没有则返回 ""，渲染时自动用内置设计稿兜底。"""
        tp = _latest_template()
        return tp if (tp and os.path.exists(tp)) else ""

    def _center(self):
        self.update_idletasks()
        w = 1120
        h = min(880, max(680, self.winfo_screenheight() - 40))
        x = (self.winfo_screenwidth() - w) // 2
        y = max(0, (self.winfo_screenheight() - h) // 2 - 20)
        self.geometry(f"{w}x{h}+{x}+{y}")

    def _setup_styles(self):
        st = ttk.Style(self)
        if "vista" in st.theme_names():
            st.theme_use("vista")
        st.configure("Card.TFrame", background=CARD_BG)
        st.configure("Root.TFrame", background=ROOT_BG)
        st.configure("Card.TCheckbutton", background=CARD_BG)
        st.configure("TNotebook", background=ROOT_BG, borderwidth=0)
        st.configure("TNotebook.Tab", font=(FONT, 10, "bold"), padding=[20, 9])
        st.map("TNotebook.Tab", background=[("selected", HEADER_BG)],
               foreground=[("selected", "#FFFFFF")])

    def _build_header(self):
        header = tk.Frame(self, bg=HEADER_BG, height=80)
        header.pack(fill="x"); header.pack_propagate(False)
        if Image and ImageTk and os.path.exists(LOGO_PATH):
            try:
                logo = Image.open(LOGO_PATH); logo.thumbnail((52, 52))
                self._logo_img = ImageTk.PhotoImage(logo)
                tk.Label(header, image=self._logo_img, bg=HEADER_BG).pack(
                    side="left", padx=(24, 12), pady=10)
            except Exception:
                pass
        tt = tk.Frame(header, bg=HEADER_BG); tt.pack(side="left", pady=14)
        tk.Label(tt, text="AI 抖音创作智能体", bg=HEADER_BG, fg="#FFFFFF",
                 font=(FONT, 16, "bold")).pack(anchor="w")
        tk.Label(tt, text="你给期数+主题+照片 · 封面/文案/排版我做 · 发布前你点头",
                 bg=HEADER_BG, fg="#9AA3B6", font=(FONT, 9)).pack(anchor="w")
        s = G.load_settings()
        mode = "离线引擎 · 0 token" if s.get("engine", "offline") == "offline" or not s.get("api_key") \
            else "API 模式 · ~800 token/次"
        tk.Label(header, text=mode, bg=HEADER_BG, fg=CYAN,
                 font=(FONT, 9, "bold")).pack(side="right", padx=24)
        tk.Button(header, text="💾 保存", bg="#2A3350", fg="#FFFFFF",
                  activebackground="#3A4570", relief="flat", font=(FONT, 9, "bold"),
                  padx=14, pady=5, cursor="hand2", command=self._save_draft).pack(
                  side="right", padx=(0, 8))
        tk.Button(header, text="📚 历史记录", bg="#2A3350", fg="#FFFFFF",
                  activebackground="#3A4570", relief="flat", font=(FONT, 9, "bold"),
                  padx=14, pady=5, cursor="hand2", command=self._open_history).pack(
                  side="right", padx=(0, 8))
        tk.Button(header, text="⚙️ 设置", bg="#2A3350", fg="#FFFFFF",
                  activebackground="#3A4570", relief="flat", font=(FONT, 9, "bold"),
                  padx=14, pady=5, cursor="hand2", command=self._open_settings).pack(
                  side="right", padx=(0, 8))
        # 底部品牌条：左红右青（抖音双色，克制点缀）——直接用 place 贴底，避免与 pack 冲突
        tk.Frame(header, bg=RED).place(relx=0.0, rely=1.0, anchor="sw",
                                       relwidth=0.6, height=3)
        tk.Frame(header, bg=CYAN).place(relx=1.0, rely=1.0, anchor="se",
                                        relwidth=0.4, height=3)

    def _build_step_strip(self):
        """四步引导条（创作旅程）：当前步骤高亮，已完成打 ✓ —— 用户永远知道自己在哪"""
        bar = tk.Frame(self, bg="#FFFFFF", height=44)
        bar.pack(fill="x"); bar.pack_propagate(False)
        tk.Frame(bar, bg=LINE, height=1).pack(fill="x", side="bottom")
        inner = tk.Frame(bar, bg="#FFFFFF"); inner.pack(expand=True, pady=(2, 0))
        self._step_widgets = []   # [(dot_label, text_label), ...]
        steps = [("①", "填内容传照片"), ("②", "生成方案"), ("③", "审核确认"), ("④", "发布完成")]
        for i, (num, label) in enumerate(steps):
            if i > 0:
                tk.Label(inner, text="→", bg="#FFFFFF", fg="#C6CBD4",
                         font=(FONT, 11)).pack(side="left", padx=16)
            cell = tk.Frame(inner, bg="#FFFFFF"); cell.pack(side="left")
            dot = tk.Label(cell, text="·", bg="#FFFFFF", fg="#C6CBD4",
                           font=(FONT, 14, "bold"))
            dot.pack(side="left", padx=(0, 5))
            txt = tk.Label(cell, text=f"{num} {label}", bg="#FFFFFF", fg=SOFT,
                           font=(FONT, 10))
            txt.pack(side="left")
            self._step_widgets.append((dot, txt))
        self._set_step(1)

    def _set_step(self, n):
        """更新四步引导：n=当前步骤（1填内容 2生成 3审核 4发布）。
        已完成步骤打绿色 ✓，当前步骤红色 ● 高亮。"""
        widgets = getattr(self, "_step_widgets", None)
        if not widgets:
            return
        for i, (dot, txt) in enumerate(widgets):
            if i + 1 < n:       # 已完成
                dot.config(text="✓", fg=GREEN)
                txt.config(fg=GRAY, font=(FONT, 10))
            elif i + 1 == n:    # 当前
                dot.config(text="●", fg=RED)
                txt.config(fg=TEXT, font=(FONT, 10, "bold"))
            else:               # 未到
                dot.config(text="·", fg="#C6CBD4")
                txt.config(fg=SOFT, font=(FONT, 10))

    def _build_body(self):
        body = ttk.Frame(self, style="Root.TFrame")
        body.pack(fill="both", expand=True, padx=16, pady=12)
        left = ttk.Frame(body, style="Card.TFrame", width=400)
        left.pack(side="left", fill="y"); left.pack_propagate(False)
        self._build_input(left)
        right = ttk.Frame(body, style="Root.TFrame")
        right.pack(side="left", fill="both", expand=True, padx=(12, 0))
        self._build_output(right)

    def _section_title(self, parent, text, color=RED, pad=(16, 10)):
        """分区标题：左侧色条 + 粗体文字，帮助眼睛快速分块"""
        row = tk.Frame(parent, bg=CARD_BG); row.pack(fill="x", padx=14, pady=pad)
        tk.Frame(row, bg=color, width=4, height=16).pack(side="left")
        tk.Label(row, text=text, bg=CARD_BG, fg=TEXT, font=(FONT, 12, "bold"),
                 anchor="w").pack(side="left", padx=(8, 0))

    def _build_input(self, parent):
        # 底部操作区（固定，不随滚动；① ② 永远看得见）
        bf = ttk.Frame(parent, style="Card.TFrame"); bf.pack(side="bottom", fill="x")
        self.gen_btn = tk.Button(bf, text="①  生成文案与方案", bg=RED, fg="#FFFFFF",
            activebackground="#E0264C", relief="flat", font=(FONT, 13, "bold"), pady=11,
            cursor="hand2", command=self.on_generate)
        self.gen_btn.pack(fill="x", padx=14, pady=(12, 6))
        self.confirm_btn = tk.Button(bf, text="②  审核通过 · 保存并确认   ", bg=GREEN, fg="#FFFFFF",
            activebackground="#259E63", relief="flat", font=(FONT, 13, "bold"), pady=12,
            cursor="hand2", state="disabled", command=self.on_confirm_publish)
        self.confirm_btn.pack(fill="x", padx=14, pady=(0, 12))

        # 照片展示带：固定在底部、始终可见（不随输入滚动）→ 上传的照片+总览入口永远显示在主界面
        band = tk.Frame(parent, bg=CARD_BG)
        band.pack(side="bottom", fill="x")
        self._photo_band = band

        # 顶部输入区（可滚动）
        canvas = tk.Canvas(parent, bg=CARD_BG, highlightthickness=0)
        sb = ttk.Scrollbar(parent, orient="vertical", command=canvas.yview)
        inner = ttk.Frame(canvas, style="Card.TFrame")
        self._scroll_canvas, self._scroll_inner = canvas, inner
        inner.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        win = canvas.create_window((0, 0), window=inner, anchor="nw")
        canvas.configure(yscrollcommand=sb.set)
        canvas.bind("<Configure>", lambda e: canvas.itemconfig(win, width=e.width))
        canvas.pack(side="left", fill="both", expand=True); sb.pack(side="right", fill="y")

        def _wheel(e):
            canvas.yview_scroll(int(-1 * (e.delta / 120)), "units")
        canvas.bind("<MouseWheel>", _wheel); inner.bind("<MouseWheel>", _wheel)
        c = inner

        self._section_title(c, "第一步：填内容", color=RED, pad=(16, 10))
        row1 = ttk.Frame(c, style="Card.TFrame"); row1.pack(fill="x", padx=14, pady=2)
        tk.Label(row1, text="周数", bg=CARD_BG, fg=TEXT, font=(FONT, 10)).pack(side="left")
        self.week_var = tk.StringVar(value="1")
        ttk.Entry(row1, textvariable=self.week_var, width=8,
                  font=(FONT, 10)).pack(side="left", padx=(8, 4))
        tk.Label(row1, text="(可填多周如6,7)", bg=CARD_BG, fg=GRAY, font=(FONT, 9)).pack(side="left")
        # 主题独占一行，输入框全宽，用户能看见全部文字
        row_theme = ttk.Frame(c, style="Card.TFrame"); row_theme.pack(fill="x", padx=14, pady=2)
        tk.Label(row_theme, text="主题", bg=CARD_BG, fg=TEXT, font=(FONT, 10)).pack(side="left")
        self.theme_var = tk.StringVar(value="RAG检索增强")
        ttk.Entry(row_theme, textvariable=self.theme_var, font=(FONT, 10)).pack(
            side="left", fill="x", expand=True, padx=(8, 0))

        # 代码图标签 —— 每张代码图一个输入框，选填
        tk.Label(c, text="代码图标签（选填 · 写在图上的简短说明）",
                 bg=CARD_BG, fg=GRAY, font=(FONT, 9)).pack(anchor="w", padx=14, pady=(8, 1))
        self._learned_container = tk.Frame(c, bg=CARD_BG)
        self._learned_container.pack(fill="x", padx=14)
        self._rebuild_learned_fields()

        self.completed_txt = self._field(c, "做成了什么（可选）", 1)
        self.difficulty_txt = self._field(c, "卡在哪（可选 · 影响BGM情绪）", 1)

        # 照片展示带：固定可见（不随输入滚动）→ 上传的照片始终显示在主界面
        b = self._photo_band
        ptitle = tk.Frame(b, bg=CARD_BG); ptitle.pack(fill="x", padx=12, pady=(10, 4))
        tk.Label(ptitle, text="🖼️ 我的照片", bg=CARD_BG, fg=TEXT,
                 font=(FONT, 11, "bold")).pack(side="left")
        tk.Label(ptitle, text="你只传照片，排序交给智能体", bg=CARD_BG, fg=SOFT,
                 font=(FONT, 8)).pack(side="left", padx=(8, 0))
        tk.Label(b, text="① 封面=固定模板，按期数+主题自动改，不用传", bg=CARD_BG, fg=TEAL,
                 font=(FONT, 9), anchor="w").pack(anchor="w", padx=14, pady=(0, 4))
        r1 = tk.Frame(b, bg=CARD_BG); r1.pack(fill="x", padx=12, pady=(0, 5))
        self._btn_code = tk.Button(r1, text="＋ 🖥 代码/项目截图",
                  bg="#FDECEF", fg=RED, activebackground="#FBDCE2", relief="flat",
                  padx=6, pady=8, font=(FONT, 9, "bold"), cursor="hand2", command=self.add_code)
        self._btn_code.pack(side="left", fill="x", expand=True)
        self._btn_extras = tk.Button(r1, text="＋ 🏡📚 生活/学习照片",
                  bg="#E8F7F0", fg=LEAF, activebackground="#D6F0E2", relief="flat",
                  padx=6, pady=8, font=(FONT, 9, "bold"), cursor="hand2", command=self.add_extras)
        self._btn_extras.pack(side="left", fill="x", expand=True, padx=(6, 0))
        self._btn_overview = tk.Button(b, text="📋 照片总览 · 删除 / 添加（含全部照片）",
                  bg="#EEF0F3", fg=TEXT, activebackground="#E2E5EA", relief="flat",
                  padx=6, pady=8, font=(FONT, 9, "bold"), cursor="hand2", command=self._open_overview)
        self._btn_overview.pack(fill="x", padx=12, pady=(0, 5))
        tk.Label(b, textvariable=self._photo_summary_var, bg=CARD_BG, fg=GRAY,
                 font=(FONT, 9), anchor="w", wraplength=360, justify="left").pack(
                 anchor="w", padx=12, pady=(0, 4))
        self._strip = tk.Frame(b, bg=CARD_BG)
        self._strip.pack(fill="x", padx=8, pady=(0, 10))

        self._render_cover_preview()
        self._refresh_photos()

    def _field(self, parent, label, lines):
        tk.Label(parent, text=label, bg=CARD_BG, fg=GRAY,
                 font=(FONT, 10)).pack(anchor="w", padx=14, pady=(8, 2))
        f = ttk.Frame(parent, style="Card.TFrame"); f.pack(fill="x", padx=14)
        txt = tk.Text(f, height=lines, font=(FONT, 10), relief="solid", bd=1,
                      highlightthickness=1, highlightcolor=CYAN, highlightbackground="#DADCE0")
        txt.pack(fill="x")
        if self._scroll_canvas is not None:
            txt.bind("<MouseWheel>", lambda e: self._scroll_canvas.yview_scroll(
                int(-1 * (e.delta / 120)), "units"))
        return txt

    def _rebuild_learned_fields(self):
        """根据当前代码图数量，重建标签输入框（每张图一个，选填）"""
        container = self._learned_container
        if container is None:
            return
        for w in container.winfo_children():
            w.destroy()
        self._learned_entries = []
        n = len(self.code)
        if n == 0:
            tk.Label(container, text="（上传代码截图后这里会自动出现对应的标签输入框）",
                     bg=CARD_BG, fg=GRAY, font=(FONT, 8)).pack(anchor="w")
            return
        for i in range(n):
            row = tk.Frame(container, bg=CARD_BG)
            row.pack(fill="x", pady=(3, 0))
            fname = os.path.basename(self.code[i]) if i < len(self.code) else ""
            tk.Label(row, text=f"第{i+1}张代码图标签", bg=CARD_BG, fg=TEXT,
                     font=(FONT, 9)).pack(side="left")
            var = tk.StringVar(value="")
            e = ttk.Entry(row, textvariable=var, font=(FONT, 10))
            e.pack(side="left", fill="x", expand=True, padx=(8, 0))
            if fname:
                tk.Label(row, text=fname[:24], bg=CARD_BG, fg=GRAY,
                         font=(FONT, 7)).pack(side="right")
            self._learned_entries.append(var)

    # ---------- 封面 / 缩略图条 / 总览 联动 ----------
    def _render_cover_preview(self):
        try:
            theme = self.theme_var.get().strip() or "本周学习"
            week = self.week_var.get()
        except Exception:
            theme, week = "本周学习", "1"
        s = G.load_settings()
        path = os.path.join(ASSETS, "_cover_preview.png")
        try:
            tpl = self._fixed_template()
            if tpl:
                G.make_cover_from_template(tpl, theme, week, path, self.tagline,
                                           s.get("account_name", "04年AI项目记录"))
            else:
                G.make_cover(theme, week, path, s.get("age", "04年"),
                             s.get("account_name", "04年AI项目记录"))
            self._cover_preview = path
        except Exception:
            self._cover_preview = ""

    def _rebuild_strip(self):
        f = self._strip
        if f is None:
            return
        for w in f.winfo_children():
            w.destroy()
        self._strip_cells = []
        items = [(self._cover_preview, "封面")] + \
                [(p, f"代码{i+1}" if len(self.code) > 1 else "代码") for i, p in enumerate(self.code)] + \
                [(p, f"#{i+1}") for i, p in enumerate(self.extras)]
        cols = 6
        for idx, (p, lbl) in enumerate(items):
            r, col = divmod(idx, cols)
            cell = tk.Frame(f, bg=CARD_BG)
            img = _thumb_image(p, lbl if not p else "", (50, 70))
            lab = tk.Label(cell, image=img, bg="#F0F1F3", relief="solid", bd=1)
            lab.image = img; lab.pack()
            tk.Label(cell, text=lbl, bg=CARD_BG, fg=GRAY, font=(FONT, 7)).pack()
            cell.grid(row=r, column=col, padx=2, pady=2); self._strip_cells.append(cell)
        for col in range(cols):
            f.columnconfigure(col, weight=1)

    def _update_summary(self):
        cov = "固定模板·自动改" if self._fixed_template() else "默认设计稿"
        code = f"✓{len(self.code)}张" if self.code else "✗未传"
        n = len(self.extras)
        self._photo_summary_var.set(
            f"封面：{cov}（不用传）　代码：{code}　生活/学习 {n} 张　（删除/添加点「照片总览」）")

    def _refresh_photos(self):
        self._rebuild_strip(); self._update_summary(); self._refresh_overview()

    def _on_tagline_change(self, *a):
        self.tagline = self._ov_tagline_var.get()
        self._save_cover_settings(); self._render_cover_preview(); self._refresh_photos()

    def add_extras(self):
        """唯一的「生活/学习照片」添加入口：一次选多张，排序交给智能体"""
        paths = filedialog.askopenfilenames(
            title="选择生活/学习照片（支持多选，智能体自动排序）",
            filetypes=[("图片", "*.jpg *.jpeg *.png *.bmp *.webp")])
        if paths:
            self.extras.extend(paths)
            self._refresh_photos()
            self.status_var.set(f"✅ 已添加 {len(paths)} 张生活/学习照｜删除/更换点「📋 照片总览」")

    def add_code(self):
        """代码/项目截图添加入口：支持多选（建议1-2张），跟生活照按钮一样"""
        paths = filedialog.askopenfilenames(
            title="选择代码/项目截图（可多选，建议1-2张，自动打标签）",
            filetypes=[("图片", "*.jpg *.jpeg *.png *.bmp *.webp")])
        if paths:
            self.code.extend(paths)
            self._rebuild_learned_fields()
            self._refresh_photos()
            self.status_var.set(f"✅ 已添加 {len(paths)} 张代码/项目截图｜删除/更换点「📋 照片总览」")

    def _clear_code(self):
        self.code = []; self._rebuild_learned_fields(); self._refresh_photos()

    def _remove_code(self, i):
        if 0 <= i < len(self.code):
            self.code.pop(i); self._rebuild_learned_fields(); self._refresh_photos()

    def _replace_code(self, i):
        p = filedialog.askopenfilename(
            title=f"更换第 {i+1} 张代码/项目截图",
            filetypes=[("图片", "*.jpg *.jpeg *.png *.bmp *.webp")])
        if p and 0 <= i < len(self.code):
            self.code[i] = p; self._refresh_photos()

    def _replace_extra(self, i):
        p = filedialog.askopenfilename(
            title=f"更换第 {i+1} 张生活/学习照",
            filetypes=[("图片", "*.jpg *.jpeg *.png *.bmp *.webp")])
        if p:
            self.extras[i] = p; self._refresh_photos()

    def _remove_extra(self, i):
        del self.extras[i]; self._refresh_photos()

    # ---------- 照片总览窗口（宽敞，放心点）----------
    def _open_overview(self):
        if self._overview is not None and self._overview.winfo_exists():
            try:
                self._overview.lift(); self._overview.focus_set()
            except Exception:
                pass
            return
        top = tk.Toplevel(self); top.title("照片总览 — 查看 / 更换 / 删除")
        top.configure(bg=ROOT_BG); top.transient(self)
        top.geometry("600x640")
        self.update_idletasks()
        x = self.winfo_rootx() + max(0, (self.winfo_width() - 600) // 2)
        y = self.winfo_rooty() + max(0, (self.winfo_height() - 640) // 2)
        top.geometry(f"+{x}+{y}")
        if os.path.exists(ICON_PATH):
            try:
                top.iconbitmap(ICON_PATH)
            except Exception:
                pass
        tk.Label(top, text="📋 照片总览", bg=HEADER_BG, fg="#FFFFFF",
                 font=(FONT, 13, "bold"), anchor="w").pack(fill="x", ipady=8, padx=16)
        tk.Label(top, text="封面=固定模板自动改（不用传）；代码=自动打标签；生活/学习照=智能体排序。\n每张右上角 ✕ 删除；下方两个按钮添加。",
                 bg=ROOT_BG, fg=GRAY, font=(FONT, 9), justify="left", anchor="w").pack(
                 fill="x", padx=16, pady=(8, 4))
        wrap = tk.Frame(top, bg=ROOT_BG); wrap.pack(fill="both", expand=True, padx=10, pady=4)
        cv = tk.Canvas(wrap, bg=ROOT_BG, highlightthickness=0)
        sb = ttk.Scrollbar(wrap, orient="vertical", command=cv.yview)
        self._ov_inner = tk.Frame(cv, bg=ROOT_BG)
        self._ov_inner.bind("<Configure>", lambda e: cv.configure(scrollregion=cv.bbox("all")))
        win = cv.create_window((0, 0), window=self._ov_inner, anchor="nw")
        cv.configure(yscrollcommand=sb.set)
        cv.bind("<Configure>", lambda e: cv.itemconfig(win, width=e.width))
        cv.pack(side="left", fill="both", expand=True); sb.pack(side="right", fill="y")
        self._ov_canvas = cv
        def _w(e):
            cv.yview_scroll(int(-1 * (e.delta / 120)), "units")
        cv.bind("<MouseWheel>", _w); self._ov_inner.bind("<MouseWheel>", _w)
        bf = tk.Frame(top, bg=ROOT_BG); bf.pack(fill="x", padx=12, pady=10)
        tk.Button(bf, text="＋ 🖥 代码/项目截图", bg="#FDECEF", fg=RED,
                  activebackground="#FBDCE2", relief="flat", font=(FONT, 11, "bold"), pady=10,
                  cursor="hand2", command=self.add_code).pack(side="left", fill="x", expand=True)
        tk.Button(bf, text="＋ 🏡📚 生活/学习照片", bg="#E8F7F0", fg=LEAF,
                  activebackground="#D6F0E2", relief="flat", font=(FONT, 11, "bold"), pady=10,
                  cursor="hand2", command=self.add_extras).pack(side="left", fill="x", expand=True, padx=(8, 0))
        self._overview = top
        top.protocol("WM_DELETE_WINDOW", self._close_overview)
        self._build_overview_cards()
        top.update_idletasks(); top.update()

    def _close_overview(self):
        try:
            if self._overview is not None:
                self._overview.destroy()
        except Exception:
            pass
        self._overview = None

    def _refresh_overview(self):
        if self._overview is not None and self._overview.winfo_exists():
            self._build_overview_cards()

    def _build_overview_cards(self):
        f = self._ov_inner
        for w in f.winfo_children():
            w.destroy()
        self._ov_cards = []

        def card(title, color, deletable=False, on_delete=None, note=""):
            """每张卡片：标题行（左标题 / 右上角 ✕ 删除），下面是内容区"""
            c = tk.Frame(f, bg=CARD_BG, relief="solid", bd=1)
            c.pack(fill="x", padx=6, pady=6)
            hdr = tk.Frame(c, bg=CARD_BG); hdr.pack(fill="x", padx=10, pady=(8, 2))
            tk.Label(hdr, text=title, bg=CARD_BG, fg=color,
                     font=(FONT, 10, "bold")).pack(side="left")
            if deletable:
                tk.Button(hdr, text="✕", fg="#C0392B", bg=CARD_BG, activebackground="#FBDCE2",
                          relief="flat", bd=0, font=(FONT, 11, "bold"), cursor="hand2",
                          command=on_delete).pack(side="right")
            elif note:
                tk.Label(hdr, text=note, bg=CARD_BG, fg=GRAY,
                         font=(FONT, 8)).pack(side="right")
            body = tk.Frame(c, bg=CARD_BG); body.pack(fill="x", padx=10, pady=(2, 10))
            self._ov_cards.append(c)
            return body

        def thumb(parent, path, ph):
            img = _thumb_image(path, ph, (120, 170))
            lab = tk.Label(parent, image=img, bg="#F0F1F3", relief="solid", bd=1)
            lab.image = img; lab.pack(side="left")

        def small(parent, text, cmd, fg):
            tk.Button(parent, text=text, fg=fg, bg="#EEF0F3", activebackground="#E2E5EA",
                      relief="flat", font=(FONT, 8), padx=8, pady=2, cursor="hand2",
                      command=cmd).pack(anchor="w", pady=(4, 0))

        # ① 封面：固定模板，不能删、不用传；只读信息 + 副标题可改
        tpl = self._fixed_template()
        body = card("① 封面", TEAL, note="固定模板 · 智能体自动改期数+主题")
        thumb(body, self._cover_preview, "封面")
        right = tk.Frame(body, bg=CARD_BG); right.pack(side="left", fill="both", expand=True, padx=(12, 0))
        tk.Label(right, text="模板：" + (os.path.basename(tpl) if tpl else "内置默认设计稿"),
                 bg=CARD_BG, fg=GRAY, font=(FONT, 8), anchor="w").pack(anchor="w", pady=(0, 4))
        tr = tk.Frame(right, bg=CARD_BG); tr.pack(anchor="w")
        tk.Label(tr, text="副标题", bg=CARD_BG, fg=TEXT, font=(FONT, 9)).pack(side="left")
        e = ttk.Entry(tr, textvariable=self._ov_tagline_var, width=14, font=(FONT, 9))
        e.pack(side="left", padx=(6, 0))
        e.bind("<FocusOut>", self._on_tagline_change); e.bind("<Return>", self._on_tagline_change)

        # ② 代码/项目截图：支持多张，每张右上角 ✕ 移除
        marks = self.plan.get("mark_suggestions", []) if self.plan else []
        if self.code:
            for ci, cpath in enumerate(self.code):
                clabel = f"② 代码/项目 {ci+1}" if len(self.code) > 1 else "② 代码/项目"
                body = card(clabel, RED, deletable=True,
                            on_delete=lambda i=ci: self._remove_code(i))
                thumb(body, cpath, f"代码{ci+1}")
                right = tk.Frame(body, bg=CARD_BG); right.pack(side="left", fill="both", expand=True, padx=(12, 0))
                tk.Label(right, text="文件：" + os.path.basename(cpath), bg=CARD_BG, fg=GRAY,
                         font=(FONT, 8), anchor="w").pack(anchor="w")
                mi = 1 + ci  # marks[0]=封面，marks[1+]=代码
                if mi < len(marks):
                    mk = marks[mi]
                    if mk.get("mark_enabled", True):
                        tk.Label(right, text=f"🏷️ 已标记：{mk.get('tag_text','')}", bg=CARD_BG, fg=GREEN,
                                 font=(FONT, 8), anchor="w").pack(anchor="w", pady=(2, 0))
                    else:
                        tk.Label(right, text="🏷️ 未标记", bg=CARD_BG, fg=GRAY,
                                 font=(FONT, 8), anchor="w").pack(anchor="w", pady=(2, 0))
                else:
                    tk.Label(right, text="程序会自动打上代码标签", bg=CARD_BG, fg=GRAY,
                             font=(FONT, 8), anchor="w").pack(anchor="w", pady=(2, 0))
                small(right, "更换", lambda i=ci: self._replace_code(i), "#6B7280")
        else:
            body = card("② 代码/项目", RED, note="未上传")
            tk.Label(body, text="还没传代码/项目截图——点下方「＋ 🖥 代码/项目截图」添加。",
                     bg=CARD_BG, fg=GRAY, font=(FONT, 9), anchor="w", justify="left").pack(anchor="w")

        # ③+ 生活/学习照：一个列表，智能体按爆款位排序；每张右上角 ✕ 删，保留小「更换」
        tk.Label(f, text=f"🖼️ 生活/学习照片（{len(self.extras)} 张）· 智能体自动排序",
                 bg=ROOT_BG, fg=TEXT, font=(FONT, 10, "bold"), anchor="w").pack(fill="x", padx=10, pady=(12, 2))
        if not self.extras:
            tk.Label(f, text="（暂无，点下方「＋ 🏡📚 生活/学习照片」添加，可多选）", bg=ROOT_BG, fg=GRAY,
                     font=(FONT, 8), anchor="w").pack(fill="x", padx=16)
        for i, p in enumerate(self.extras):
            rname = G.ROLES[i][0] if i < len(G.ROLES) else f"镜头{i+1}"
            body = card(f"第{i+1}张 · 爆款位：{rname}", LEAF, deletable=True,
                        on_delete=lambda i=i: self._remove_extra(i))
            thumb(body, p, f"#{i+1}")
            right = tk.Frame(body, bg=CARD_BG); right.pack(side="left", fill="both", expand=True, padx=(12, 0))
            tk.Label(right, text="文件：" + os.path.basename(p), bg=CARD_BG, fg=GRAY,
                     font=(FONT, 8), anchor="w").pack(anchor="w")
            # 标记状态
            code_cnt = len(self.code) if self.code else 0
            mi = 1 + code_cnt + i
            if mi < len(marks):
                mk = marks[mi]
                if mk.get("mark_enabled", False):
                    tk.Label(right, text=f"🏷️ 已标记：{mk.get('tag_text','')}", bg=CARD_BG, fg=GREEN,
                             font=(FONT, 8), anchor="w").pack(anchor="w", pady=(2, 0))
                else:
                    tk.Label(right, text="🏷️ 未标记", bg=CARD_BG, fg=GRAY,
                             font=(FONT, 8), anchor="w").pack(anchor="w", pady=(2, 0))
            small(right, "更换", lambda i=i: self._replace_extra(i), "#6B7280")

    # ---------- 输出区 ----------
    def _build_output(self, parent):
        hrow = tk.Frame(parent, bg=ROOT_BG); hrow.pack(anchor="w", pady=(0, 6))
        tk.Frame(hrow, bg=CYAN, width=4, height=14).pack(side="left")
        tk.Label(hrow, text="第二步：看结果 · 没问题点左下「② 审核通过」",
                 bg=ROOT_BG, fg=TEXT, font=(FONT, 10, "bold")).pack(side="left", padx=(8, 0))
        self.nb = ttk.Notebook(parent); self.nb.pack(fill="both", expand=True)
        self.tab_copy = ttk.Frame(self.nb); self.tab_image = ttk.Frame(self.nb)
        self.tab_pub = ttk.Frame(self.nb); self.tab_mark = ttk.Frame(self.nb)
        self.nb.add(self.tab_copy, text="  📝 文案  ")
        self.nb.add(self.tab_image, text="  🖼️ 图片  ")
        self.nb.add(self.tab_pub, text="  🎵 音乐 / 发布  ")
        self.nb.add(self.tab_mark, text="  🏷️ 标记  ")
        self.copy_out = self._out_page(self.tab_copy, with_copy_btn=True)
        # 用户编辑文案时标记为未保存（和 Word 一样，编辑后标题出现 *）
        self.copy_out.bind("<KeyRelease>", lambda e: self._mark_unsaved() if self._saved else None)
        self.image_out = self._out_page(self.tab_image)
        self.pub_out = self._out_page(self.tab_pub, with_tools=True)
        # 标记页：可滚动的照片标记面板
        self._build_mark_page(self.tab_mark)

    def _out_page(self, parent, with_copy_btn=False, with_tools=False):
        wrap = ttk.Frame(parent, style="Root.TFrame"); wrap.pack(fill="both", expand=True)
        txt = tk.Text(wrap, font=(FONT, 10), bg=CARD_BG, fg=TEXT, relief="flat",
                      padx=18, pady=14, spacing3=4, state="disabled", highlightthickness=0, wrap="word")
        sb = ttk.Scrollbar(wrap, command=txt.yview); txt.config(yscrollcommand=sb.set)
        txt.pack(side="left", fill="both", expand=True); sb.pack(side="right", fill="y")
        txt.bind("<MouseWheel>", lambda e: txt.yview_scroll(int(-1 * (e.delta / 120)), "units"))
        if with_copy_btn:
            bar = ttk.Frame(parent, style="Root.TFrame"); bar.pack(fill="x", pady=(8, 0))
            tk.Button(bar, text="📋 复制文案", bg="#E8EAED", fg=TEXT, relief="flat",
                      padx=16, pady=6, font=(FONT, 9), cursor="hand2",
                      command=self.copy_caption).pack(side="left")
        if with_tools:
            bar = ttk.Frame(parent, style="Root.TFrame"); bar.pack(fill="x", pady=(8, 0))
            tk.Button(bar, text="📂 打开成品包", bg="#E8EAED", fg=TEXT, relief="flat",
                      padx=14, pady=8, font=(FONT, 9), cursor="hand2",
                      command=self.open_package).pack(side="left")
            tk.Button(bar, text="📊 发布记录", bg="#E8EAED", fg=TEXT, relief="flat",
                      padx=14, pady=8, font=(FONT, 9), cursor="hand2",
                      command=self.open_record).pack(side="left", padx=(10, 0))
        return txt

    def _build_statusbar(self):
        bar = tk.Frame(self, bg=HEADER_BG, height=36)
        bar.pack(fill="x", side="bottom"); bar.pack_propagate(False)
        self.status_var = tk.StringVar(
            value="就绪｜填内容 → ①生成 → ②审核 → 发布；删除/添加点「照片总览」")
        tk.Label(bar, textvariable=self.status_var, bg=HEADER_BG, fg="#C6CBD8",
                 font=(FONT, 10), anchor="w").pack(side="left", padx=16)
        auto = "执行发布Agent 接管" if P.HAS_PLAYWRIGHT else "手动发布"
        tk.Label(bar, text=auto, bg=HEADER_BG, fg="#8A93A8",
                 font=(FONT, 9)).pack(side="right", padx=16)

    # ---------- 工具 ----------
    def _set_out(self, w, text):
        w.config(state="normal"); w.delete("1.0", "end"); w.insert("1.0", text); w.config(state="disabled")

    def _set_out_editable(self, w, text):
        """设置文本但保持可编辑状态（用户可修改文案后再确认）"""
        w.config(state="normal"); w.delete("1.0", "end"); w.insert("1.0", text)
        # 不 disable，让用户可以直接编辑

    def _get(self, txt):
        return txt.get("1.0", "end").strip()

    def _refresh_image_tab(self):
        """只刷新图片Tab的标记状态，不触碰文案Tab（用户可能正在编辑）"""
        p = self.plan
        if not p:
            return
        img = ["【图片版式（固定 · 程序已排版）】\n"]
        for it in p["image_plan"]:
            img += [f"  {it['photo']}（{it['role']}）\n     {it['points']}\n\n"]
        img += ["【代码图已打标签】\n"] + [f"  · {t}\n" for t in p.get("tag_lines", [])]
        img += ["\n【每张图的标记状态 · 已按最新内容更新】\n"]
        marks = p.get("mark_suggestions", [])
        for i, t in enumerate(p.get("photo_tags", [])):
            if i < len(marks):
                mi = marks[i]
                status = "[✓标记]" if mi.get("mark_enabled") else "[✗不标记]"
                tag_text = mi.get("tag_text", t)
                img += [f"  第{i+1}张：{status} {tag_text}  ({mi.get('reason','')})\n"]
            else:
                img += [f"  第{i+1}张：{t}\n"]
        if p.get("package_files") and p["package_files"][0]:
            img += [f"\n  封面：{p['package_files'][0]}\n"]
        if len(p.get("package_files", [])) > 1 and p["package_files"][1]:
            code_mark = marks[1] if len(marks) > 1 else {}
            code_status = "已打标签" if code_mark.get("mark_enabled", True) else "未打标签"
            img += [f"  代码（{code_status}）：{p['package_files'][1]}\n"]
        img += ["\n【AI绘图提示词（备用）】\n"]
        img += [f"  {i+1}. {t}\n\n" for i, t in enumerate(p.get("ai_prompts", []))]
        self._set_out(self.image_out, "".join(img))

    def on_generate(self):
        theme = self.theme_var.get().strip()
        if not theme:
            messagebox.showwarning("缺少输入", "请先填写「主题」"); return
        if not self.code:
            messagebox.showwarning("缺少代码照", "请先点「＋ 🖥 代码/项目截图」上传至少1张。"); return
        # 生活/学习照片为可选，不再强制要求
        self.status_var.set("正在生成（离线引擎·0 token）…"); self.update_idletasks()
        # 收集每张代码图的标签（选填，一行一个）
        learned = "\n".join(v.get().strip() for v in self._learned_entries)
        plan = G.generate_plan(self.week_var.get(), theme, learned,
                               self._get(self.completed_txt), self._get(self.difficulty_txt),
                               extra_count=len(self.extras), code_count=len(self.code))
        enhanced = G.api_enhance(plan)
        if enhanced:
            plan["caption"] = enhanced; plan["engine"] = "api"
        G.build_package(plan, self.code, list(self.extras), self._fixed_template(), self.tagline)
        ORCH.enrich_package(plan)  # 素材包富化：附加 analysis + bgm_candidates（音乐模块输入/输出）
        self.plan = plan
        self._mark_unsaved()  # 新生成的内容尚未保存，标题显示 *
        if plan.get("package_files"):
            self._cover_preview = plan["package_files"][0]
        self._refresh_photos(); self._render_plan(plan)
        self.confirm_btn.config(state="normal"); self.nb.select(0)
        self._set_step(2)  # 生成完成 → 进入「审核」
        _pkg_display = os.path.basename(os.path.dirname(plan['package_dir'])) + "/" + os.path.basename(plan['package_dir'])
        self.status_var.set(f"✅ 已生成｜成品包：{_pkg_display}｜检查后点左下「② 确定」")

    def _render_plan(self, p):
        lines = ["✏️ 以下文案可直接编辑修改，改完点「② 确定」\n\n"]
        lines += ["【标题 · 三选一】\n"] + [f"  {i+1}. {t}\n" for i, t in enumerate(p["titles"])]
        lines += [f"\n【3秒钩子】\n  {p['hook']}\n", "\n【视频文案（最生活化版）】\n"]
        lines += [f"  {ln}\n" if ln else "\n" for ln in p["caption"].splitlines()]
        lines += [f"\n【话题标签】\n  {p['hashtags']}\n"]
        self._set_out_editable(self.copy_out, "".join(lines))
        img = ["【图片版式（固定 · 程序已排版）】\n"]
        for it in p["image_plan"]:
            img += [f"  {it['photo']}（{it['role']}）\n     {it['points']}\n\n"]
        img += ["【第二张图已自动打的标签】\n"] + [f"  · {t}\n" for t in p["tag_lines"]]
        img += ["\n【每张图的抖音标签短句 · 标记状态】\n"]
        marks = p.get("mark_suggestions", [])
        for i, t in enumerate(p.get("photo_tags", [])):
            if i < len(marks):
                mi = marks[i]
                status = "[✓标记]" if mi.get("mark_enabled") else "[✗不标记]"
                reason = mi.get("reason", "")
                img += [f"  第{i+1}张：{status} {t}  ({reason})\n"]
            else:
                img += [f"  第{i+1}张：{t}\n"]
        img += [f"\n  封面（固定模板/默认）：{p['package_files'][0]}\n"]
        # 代码图状态
        if len(p.get("package_files", [])) > 1 and p["package_files"][1]:
            code_mark = marks[1] if len(marks) > 1 else {}
            code_status = "已打标签" if code_mark.get("mark_enabled", True) else "未打标签"
            img += [f"  代码（{code_status}）：{p['package_files'][1]}\n"]
        img += ["\n【AI绘图提示词（备用）】\n"]
        img += [f"  {i+1}. {t}\n\n" for i, t in enumerate(p["ai_prompts"])]
        self._set_out(self.image_out, "".join(img))
        pub = ["【🎵 推荐BGM（抖音热门·发布时直接搜索）】\n"]
        for i, item in enumerate(p["bgm"]):
            n, search, why = item[0], item[1], item[2]
            clip = item[3] if len(item) > 3 else ""
            pub.append(f"  {i+1}. {n}\n     理由：{why}\n")
            if clip:
                pub.append(f"     ⏱ {clip}\n")
            pub.append(f"     👉 {search}\n\n")
        pub += ["【📹 镜头顺序】\n"] + [f"  {s}\n" for s in p["shot_order"]]
        pub += [f"\n【⏰ 建议发布时间】\n  {p['publish_time']}\n", f"\n【📁 成品包】\n  {p['package_dir']}\n",
                "\n点左下「② 确定」后：智能体会自动去抖音上传图、填文案、发布。\n"]
        self._set_out(self.pub_out, "".join(pub))
        # 刷新标记面板
        self._render_mark_panel()

    # ---------- 🏷️ 标记面板 ----------
    def _build_mark_page(self, parent):
        """构建标记页：可滚动画布，内放每张照片的标记开关"""
        wrap = tk.Frame(parent, bg=ROOT_BG)
        wrap.pack(fill="both", expand=True)

        cv = tk.Canvas(wrap, bg=ROOT_BG, highlightthickness=0)
        sb = ttk.Scrollbar(wrap, orient="vertical", command=cv.yview)
        self._mark_inner = tk.Frame(cv, bg=ROOT_BG)
        self._mark_inner.bind("<Configure>",
            lambda e: cv.configure(scrollregion=cv.bbox("all")))
        win = cv.create_window((0, 0), window=self._mark_inner, anchor="nw")
        cv.configure(yscrollcommand=sb.set)
        cv.bind("<Configure>", lambda e: cv.itemconfig(win, width=e.width))
        cv.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")

        def _mw(e):
            cv.yview_scroll(int(-1 * (e.delta / 120)), "units")
        cv.bind("<MouseWheel>", _mw)
        self._mark_inner.bind("<MouseWheel>", _mw)
        self._mark_canvas = cv
        self._mark_rows = []  # [(enabled_var, entry_widget, mark_index), ...]

    def _render_mark_panel(self):
        """根据 plan 的 mark_suggestions 重建标记面板"""
        inner = getattr(self, '_mark_inner', None)
        if inner is None:
            return
        for w in inner.winfo_children():
            w.destroy()
        self._mark_rows = []

        if not self.plan:
            tk.Label(inner, text="请先生成内容", bg=ROOT_BG, fg=GRAY,
                     font=(FONT, 10)).pack(pady=30)
            return

        marks = self.plan.get("mark_suggestions", [])
        if not marks:
            tk.Label(inner, text="暂无标记建议", bg=ROOT_BG, fg=GRAY,
                     font=(FONT, 10)).pack(pady=30)
            return

        tk.Label(inner, text="🏷️ 每张照片的标记设置",
                 bg=ROOT_BG, fg=TEXT, font=(FONT, 12, "bold")).pack(
                 anchor="w", padx=12, pady=(10, 2))
        tk.Label(inner, text="智能体根据文案给出了建议，你可以自由调整——勾选/取消、修改文字都可以",
                 bg=ROOT_BG, fg=GRAY, font=(FONT, 9)).pack(
                 anchor="w", padx=12, pady=(0, 10))

        # 照片列表：封面 → 代码 → 生活照
        code_paths = self.code if isinstance(self.code, list) else ([self.code] if self.code else [])
        extra_paths = list(self.extras or [])

        # 构建所有照片路径（封面用预览图）
        all_photos = []
        # ① 封面
        all_photos.append(("① 封面（模板）", self._cover_preview, True))
        # ② 代码
        for ci, cp in enumerate(code_paths):
            label = f"② 代码{ci+1}" if len(code_paths) > 1 else "② 代码"
            all_photos.append((label, cp, False))
        # ③ 生活/学习照
        for i, ep in enumerate(extra_paths):
            roles = self.plan.get("roles", [])
            rname = roles[i][0] if i < len(roles) else f"照片{i+1}"
            all_photos.append((f"③ {rname}", ep, False))

        for idx, (label, path, is_cover) in enumerate(all_photos):
            mark = marks[idx] if idx < len(marks) else {"mark_enabled": True, "tag_text": "", "reason": ""}

            # 卡片行
            row = tk.Frame(inner, bg=CARD_BG, relief="solid", bd=1)
            row.pack(fill="x", padx=8, pady=4)

            # 缩略图
            img = _thumb_image(path if path and os.path.exists(path) else None,
                               label, (70, 95))
            if img:
                lab = tk.Label(row, image=img, bg="#F0F1F3", relief="solid", bd=1)
                lab.image = img
                lab.pack(side="left", padx=(8, 10), pady=8)

            # 右侧控制区
            ctrl = tk.Frame(row, bg=CARD_BG)
            ctrl.pack(side="left", fill="both", expand=True, padx=(0, 8), pady=6)

            # 照片标签
            tk.Label(ctrl, text=label, bg=CARD_BG, fg=TEXT,
                     font=(FONT, 10, "bold"), anchor="w").pack(anchor="w")

            # 封面始终标记（灰色说明，不让改）
            if is_cover:
                tk.Label(ctrl, text=f"🔒 封面固定标记：{mark.get('tag_text', '')}",
                         bg=CARD_BG, fg=GRAY, font=(FONT, 9), anchor="w").pack(anchor="w")
                tk.Label(ctrl, text=mark.get("reason", ""), bg=CARD_BG, fg="#ADB5BD",
                         font=(FONT, 8), anchor="w").pack(anchor="w")
                self._mark_rows.append((None, None, idx))
                continue

            # Checkbox + 标记文字行
            chk_row = tk.Frame(ctrl, bg=CARD_BG)
            chk_row.pack(fill="x", anchor="w", pady=(2, 0))

            enabled_var = tk.BooleanVar(value=bool(mark.get("mark_enabled", True)))
            cb = tk.Checkbutton(chk_row, text="加标记", variable=enabled_var,
                                bg=CARD_BG, fg=TEXT, font=(FONT, 10, "bold"),
                                activebackground=CARD_BG, selectcolor=CARD_BG)
            cb.pack(side="left")

            # 标记文字输入
            entry_var = tk.StringVar(value=mark.get("tag_text", "")[:12])
            e = ttk.Entry(chk_row, textvariable=entry_var, font=(FONT, 10), width=18)
            e.pack(side="left", padx=(8, 0))

            # AI 理由
            tk.Label(ctrl, text=f"💡 {mark.get('reason', '')}", bg=CARD_BG, fg="#ADB5BD",
                     font=(FONT, 8), anchor="w").pack(anchor="w", pady=(1, 0))

            # 用户修改时标记为未保存
            def _on_mark_change(*a, ev=enabled_var, ent=entry_var):
                self._mark_unsaved() if self._saved else None

            enabled_var.trace_add("write", _on_mark_change)
            entry_var.trace_add("write", _on_mark_change)

            self._mark_rows.append((enabled_var, entry_var, idx))

    def _sync_mark_settings(self):
        """从标记面板读取用户修改，同步回 plan"""
        if not self.plan:
            return
        marks = self.plan.get("mark_suggestions", [])
        for enabled_var, entry_var, idx in self._mark_rows:
            if idx < len(marks) and enabled_var is not None:
                marks[idx]["mark_enabled"] = enabled_var.get()
                marks[idx]["tag_text"] = entry_var.get()[:12] if entry_var else marks[idx].get("tag_text", "")

    def copy_caption(self):
        if not self.plan:
            messagebox.showinfo("提示", "请先点「① 生成」"); return
        self._sync_edited_content()  # 先同步用户编辑
        self.clipboard_clear()
        self.clipboard_append(f"{self.plan['titles'][0]}\n\n{self.plan['caption']}\n\n{self.plan['hashtags']}")
        self.update(); self.status_var.set("📋 文案已复制")

    def open_package(self):
        if self.plan and os.path.isdir(self.plan.get("package_dir", "")):
            os.startfile(self.plan["package_dir"])

    def open_record(self):
        """「📊 发布记录」按钮：打开只读历史记录窗口（查看/打开素材包）"""
        self._open_history()

    def _open_history(self):
        """历史记录页（M2-2）：只读表格展示 07_发布记录，双击/按钮查看某期素材包"""
        if self._history_win is not None and self._history_win.winfo_exists():
            try:
                self._history_win.lift(); self._history_win.focus_set()
            except Exception:
                pass
            return
        top = tk.Toplevel(self); top.title("📚 历史发布记录")
        top.configure(bg=ROOT_BG)
        top.geometry("940x540")
        self.update_idletasks()
        x = self.winfo_rootx() + max(0, (self.winfo_width() - 940) // 2)
        y = self.winfo_rooty() + max(0, (self.winfo_height() - 540) // 2)
        top.geometry(f"+{x}+{y}")
        if os.path.exists(ICON_PATH):
            try:
                top.iconbitmap(ICON_PATH)
            except Exception:
                pass

        tk.Label(top, text="📚 历史发布记录", bg=HEADER_BG, fg="#FFFFFF",
                 font=(FONT, 13, "bold"), anchor="w").pack(fill="x", ipady=8, padx=16)
        tk.Label(top, text="只读表格 · 双击某行或选中后点「查看素材包」，可打开该期成品包目录",
                 bg=ROOT_BG, fg=GRAY, font=(FONT, 9), anchor="w").pack(fill="x", padx=16, pady=(8, 4))

        # ── 读取发布记录（xlsx 优先，csv 兜底） ──
        rows, rec_path = [], ""
        if os.path.exists(G.RECORD_XLSX):
            rec_path = G.RECORD_XLSX
            try:
                from openpyxl import load_workbook
                ws = load_workbook(G.RECORD_XLSX).active
                rows = [list(r) for r in ws.iter_rows(values_only=True)
                        if any(v is not None for v in r)]
            except Exception:
                rows = []
        elif os.path.exists(G.RECORD_CSV):
            rec_path = G.RECORD_CSV
            try:
                import csv
                with open(G.RECORD_CSV, newline="", encoding="utf-8-sig") as f:
                    rows = list(csv.reader(f))
            except Exception:
                rows = []
        if rows and rows[0] and str(rows[0][0] or "") == "日期":
            header, data = rows[0], rows[1:]
        else:
            header, data = list(G.RECORD_COLS), rows

        # ── 表格 ──
        wrap = tk.Frame(top, bg=ROOT_BG); wrap.pack(fill="both", expand=True, padx=16, pady=(4, 8))
        tree = ttk.Treeview(wrap, columns=header, show="headings", height=14)
        widths = {"日期": 130, "周数": 70, "主题": 200, "采用标题": 280,
                  "BGM": 170, "状态": 150, "成品包路径": 240}
        for col in header:
            tree.heading(col, text=col)
            tree.column(col, width=widths.get(col, 140), anchor="w", stretch=(col in ("主题", "成品包路径")))
        vsb = ttk.Scrollbar(wrap, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=vsb.set)
        tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")
        for r in data:
            tree.insert("", "end", values=[str(v) if v is not None else "" for v in r])

        # 空记录提示
        if not data:
            tk.Label(wrap, text="（暂无发布记录，发布一条后自动生成）", bg=ROOT_BG, fg=GRAY,
                     font=(FONT, 10)).pack(pady=30)

        def _open_selected():
            sel = tree.selection()
            if not sel:
                messagebox.showinfo("提示", "请先在表格中选中一行。", parent=top)
                return
            vals = tree.item(sel[0], "values")
            pkg = vals[-1] if vals else ""
            if pkg and os.path.isdir(pkg):
                os.startfile(pkg)
                self.status_var.set(f"📁 已打开素材包：{os.path.basename(pkg)}")
            else:
                messagebox.showinfo("提示", "该期成品包目录不存在或为空。", parent=top)

        tree.bind("<Double-1>", lambda e: _open_selected())

        # ── 底部按钮 ──
        bf = tk.Frame(top, bg=ROOT_BG); bf.pack(fill="x", padx=16, pady=(0, 12))
        tk.Button(bf, text="📁 查看素材包", bg=GREEN, fg="#FFFFFF",
                  activebackground="#259E63", relief="flat", font=(FONT, 10, "bold"),
                  padx=16, pady=6, cursor="hand2", command=_open_selected).pack(side="left")
        if rec_path:
            tk.Button(bf, text="📄 打开Excel原件", bg="#E8EAED", fg=TEXT,
                      activebackground="#DADCE0", relief="flat", font=(FONT, 9),
                      padx=14, pady=6, cursor="hand2",
                      command=lambda: os.startfile(rec_path)).pack(side="left", padx=(10, 0))
        tk.Label(bf, text=f"共 {len(data)} 条记录", bg=ROOT_BG, fg=GRAY,
                 font=(FONT, 9)).pack(side="right")

        self._history_win = top
        top.protocol("WM_DELETE_WINDOW", lambda: (top.destroy(),
                                                  setattr(self, "_history_win", None)))
        top.update_idletasks(); top.update()

    # ---------- 确定 → 发布预览窗口（审核关卡）----------
    def _sync_edited_content(self):
        """从可编辑的文案标签页和标记面板读取用户修改，同步回 plan"""
        if not self.plan:
            return
        raw = self.copy_out.get("1.0", "end")
        # 解析标题：匹配 "  1. xxx" 格式行
        import re
        title_matches = re.findall(r'^\s*\d+\.\s*(.+)$', raw, re.MULTILINE)
        if title_matches:
            self.plan["titles"] = [t.strip() for t in title_matches[:3]]
        # 解析 3秒钩子：【3秒钩子】和【视频文案】之间的内容
        hook_match = re.search(r'【3秒钩子】\s*\n(.*?)(?=\n\s*\n【视频文案)', raw, re.DOTALL)
        if hook_match:
            hook_lines = hook_match.group(1).splitlines()
            hook_lines = [ln[2:] if ln.startswith("  ") else ln for ln in hook_lines]
            self.plan["hook"] = "\n".join(hook_lines).strip()
        # 解析文案：【视频文案】和【话题标签】之间的内容
        cap_match = re.search(r'【视频文案[^】]*】\n(.*?)(?=\n【话题标签】)', raw, re.DOTALL)
        if cap_match:
            cap_lines = cap_match.group(1).splitlines()
            # 去掉每行开头的两个空格缩进
            cap_lines = [ln[2:] if ln.startswith("  ") else ln for ln in cap_lines]
            self.plan["caption"] = "\n".join(cap_lines).strip()
        # 解析标签
        tag_match = re.search(r'【话题标签】\s*\n\s*(.+)', raw)
        if tag_match:
            self.plan["hashtags"] = tag_match.group(1).strip()
        # 同步标记面板
        self._sync_mark_settings()

    def on_confirm_publish(self):
        if not self.plan:
            messagebox.showinfo("提示", "请先点「① 生成」"); return
        self._sync_edited_content()  # 读取用户编辑的内容
        self._set_step(3)  # 进入审核环节
        self._show_publish_preview(self.plan)

    # ---------- Windows MCI 音频播放（无需额外依赖） ----------
    _bgm_alias = ""

    def _mci_play(self, path):
        """用 Windows MCI 播放音频文件（mp3/wav 均可）"""
        import ctypes
        winmm = ctypes.windll.winmm
        # 先关闭上一次
        self._mci_stop()
        alias = "douyin_bgm"
        self._bgm_alias = alias
        cmd_open = f'open "{path}" type mpegvideo alias {alias}'
        winmm.mciSendStringW(cmd_open, None, 0, 0)
        winmm.mciSendStringW(f"play {alias}", None, 0, 0)

    def _mci_stop(self):
        """停止并关闭 MCI 音频"""
        if not self._bgm_alias:
            return
        import ctypes
        winmm = ctypes.windll.winmm
        winmm.mciSendStringW(f"stop {self._bgm_alias}", None, 0, 0)
        winmm.mciSendStringW(f"close {self._bgm_alias}", None, 0, 0)
        self._bgm_alias = ""

    def _show_publish_preview(self, p):
        """发布预览窗口：抖音风格 — 图片轮播 + BGM试听 + 文案，审核通过才发"""
        top = tk.Toplevel(self)
        top.title("📱 发布预览 — 审核通过才发布")
        top.configure(bg="#000000"); top.transient(self)
        _H = min(860, max(720, self.winfo_screenheight() - 60))
        top.geometry(f"520x{_H}")
        self.update_idletasks()
        x = self.winfo_rootx() + max(0, (self.winfo_width() - 520) // 2)
        y = max(0, self.winfo_rooty())
        top.geometry(f"+{x}+{y}")
        if os.path.exists(ICON_PATH):
            try: top.iconbitmap(ICON_PATH)
            except Exception: pass

        # 窗口关闭时停止音频
        def _on_preview_close():
            self._mci_stop()
            top.destroy()
        top.protocol("WM_DELETE_WINDOW", _on_preview_close)

        # ===== 底部按钮（先 pack side=bottom 保证始终可见） =====
        bf = tk.Frame(top, bg="#000000"); bf.pack(side="bottom", fill="x", padx=16, pady=(8, 12))
        def _do_confirm():
            self._mci_stop()
            top.destroy()
            self._do_publish(p)
        tk.Button(bf, text="✅ 审核通过 · 确认", bg=GREEN, fg="#FFFFFF",
                  activebackground="#259E63", relief="flat", font=(FONT, 12, "bold"),
                  pady=10, cursor="hand2", command=_do_confirm).pack(side="left", fill="x", expand=True)
        tk.Button(bf, text="❌ 返回修改", bg="#333333", fg="#FFFFFF",
                  activebackground="#555555", relief="flat", font=(FONT, 11, "bold"),
                  pady=10, cursor="hand2", command=_on_preview_close).pack(side="left", fill="x", expand=True, padx=(8, 0))

        # ===== 顶部标题栏（抖音风格黑底白字） =====
        tk.Label(top, text="📱 作品预览", bg="#000000", fg="#FFFFFF",
                 font=(FONT, 13, "bold")).pack(fill="x", ipady=6)

        # ===== 素材包自检清单（发布前自动检查） =====
        pkg_dir = p.get("package_dir", "")
        if pkg_dir and os.path.isdir(pkg_dir):
            # 老草稿/旧素材包可能未富化 → 自动补上 analysis + bgm_candidates（幂等）
            ORCH.enrich_package(p)
        checks, errors, _summary, _pkg = _pkg_selfcheck(pkg_dir)
        pass_all = not errors
        check_frame = tk.Frame(top, bg="#E8F7F0" if pass_all else "#FDECEF")
        check_frame.pack(fill="x", padx=20, pady=(8, 0))
        chk_title = "✅ 素材包自检通过" if pass_all else "⚠️ 素材包自检未通过"
        tk.Label(check_frame, text=chk_title, bg=check_frame["bg"],
                 fg=LEAF if pass_all else RED, font=(FONT, 10, "bold"), anchor="w"
                 ).pack(anchor="w", padx=10, pady=(6, 0))
        chk_items = "   ".join(
            f"{'✓' if ok else '✗'} {name}{detail}" for name, ok, detail in checks)
        tk.Label(check_frame, text=chk_items, bg=check_frame["bg"],
                 fg=("#157A4B" if pass_all else "#C0392B"), font=(FONT, 8),
                 anchor="w", justify="left", wraplength=470).pack(
                 anchor="w", padx=10, pady=(2, 0))
        if errors:
            tk.Label(check_frame, text="  ".join(errors), bg=check_frame["bg"],
                     fg=RED, font=(FONT, 8, "bold"), anchor="w", wraplength=470,
                     justify="left").pack(anchor="w", padx=10, pady=(0, 6))
        else:
            tk.Label(check_frame, text=f"周{_summary.get('week','')} · {_summary.get('theme','')}",
                     bg=check_frame["bg"], fg="#6B7280", font=(FONT, 8), anchor="w"
                     ).pack(anchor="w", padx=10, pady=(0, 6))

        # ===== 图片轮播区（黑底，模拟抖音图文） =====
        photos = p.get("package_files", [])
        tags = p.get("photo_tags", [])
        IMG_W, IMG_H = 440, 420  # 轮播显示尺寸

        carousel_frame = tk.Frame(top, bg="#000000")
        carousel_frame.pack(fill="x", padx=20, pady=(4, 0))

        # 预加载所有轮播图片
        carousel_imgs = []
        for fpath in photos:
            img = _thumb_image(fpath if fpath and os.path.exists(fpath) else None,
                               "📷", (IMG_W, IMG_H))
            carousel_imgs.append(img)
        if not carousel_imgs:
            carousel_imgs.append(_thumb_image(None, "暂无图片", (IMG_W, IMG_H)))

        # 图片显示 Canvas
        img_canvas = tk.Canvas(carousel_frame, width=IMG_W, height=IMG_H,
                               bg="#1A1A1A", highlightthickness=0)
        img_canvas.pack()
        img_on_canvas = img_canvas.create_image(IMG_W // 2, IMG_H // 2,
                                                 image=carousel_imgs[0])

        # 当前索引 + 计数器
        cur_idx = [0]
        counter_var = tk.StringVar(value=f"1/{len(carousel_imgs)}")

        # 标签短句浮层（右下角小字）
        tag_var = tk.StringVar(value=tags[0][:12] if tags else "")
        tag_overlay = tk.Label(carousel_frame, textvariable=tag_var, bg="#000000",
                               fg="#FFFFFF", font=(FONT, 8), anchor="e")
        tag_overlay.place(relx=0.98, rely=0.02, anchor="ne")

        def _show_slide(idx):
            """切换轮播到第 idx 张"""
            cur_idx[0] = idx % len(carousel_imgs)
            img_canvas.itemconfig(img_on_canvas, image=carousel_imgs[cur_idx[0]])
            counter_var.set(f"{cur_idx[0]+1}/{len(carousel_imgs)}")
            t = tags[cur_idx[0]][:12] if cur_idx[0] < len(tags) else ""
            tag_var.set(t)

        # 导航按钮行：◀  1/6  ▶
        nav_row = tk.Frame(carousel_frame, bg="#000000")
        nav_row.pack(fill="x", pady=(4, 0))
        tk.Button(nav_row, text="◀", bg="#333333", fg="#FFFFFF", relief="flat",
                  font=(FONT, 12, "bold"), width=4, cursor="hand2",
                  command=lambda: _show_slide(cur_idx[0] - 1)).pack(side="left")
        tk.Label(nav_row, textvariable=counter_var, bg="#000000", fg="#FFFFFF",
                 font=(FONT, 10)).pack(side="left", expand=True)
        tk.Button(nav_row, text="▶", bg="#333333", fg="#FFFFFF", relief="flat",
                  font=(FONT, 12, "bold"), width=4, cursor="hand2",
                  command=lambda: _show_slide(cur_idx[0] + 1)).pack(side="right")

        # ===== 文案区（抖音风格：标题 + 正文 + 标签） =====
        text_frame = tk.Frame(top, bg="#000000")
        text_frame.pack(fill="x", padx=20, pady=(10, 0))

        # 标题
        tk.Label(text_frame, text=p["titles"][0], bg="#000000", fg="#FFFFFF",
                 font=(FONT, 11, "bold"), anchor="w", wraplength=430,
                 justify="left").pack(anchor="w")

        # 文案（可展开/收起，模拟抖音折叠效果）
        caption_lines = p["caption"].split("\n")
        caption_full = p["caption"]
        caption_short = "\n".join(caption_lines[:4])
        expanded = [False]
        cap_var = tk.StringVar(value=caption_short + ("  ...展开" if len(caption_lines) > 4 else ""))
        cap_label = tk.Label(text_frame, textvariable=cap_var, bg="#000000", fg="#E0E0E0",
                             font=(FONT, 9), anchor="w", wraplength=430,
                             justify="left", cursor="hand2")
        cap_label.pack(anchor="w", pady=(4, 0))
        if len(caption_lines) > 4:
            def _toggle_caption(event=None):
                if expanded[0]:
                    cap_var.set(caption_short + "  ...展开")
                    expanded[0] = False
                else:
                    cap_var.set(caption_full + "\n  收起▲")
                    expanded[0] = True
            cap_label.bind("<Button-1>", _toggle_caption)

        # 话题标签（青色，抖音风格）
        tk.Label(text_frame, text=p["hashtags"], bg="#000000", fg=CYAN,
                 font=(FONT, 9), anchor="w", wraplength=430).pack(anchor="w", pady=(6, 0))

        # ===== BGM 区（播放按钮 + 歌名） =====
        bgm_frame = tk.Frame(top, bg="#000000")
        bgm_frame.pack(fill="x", padx=20, pady=(10, 0))

        bgm_items = p.get("bgm", [])
        bgm_name = bgm_items[0][0] if bgm_items else "无"
        bgm_trimmed = p.get("bgm_trimmed", "")

        # 播放状态
        playing = [False]

        def _toggle_bgm():
            """切换 BGM 播放/停止"""
            if playing[0]:
                self._mci_stop()
                playing[0] = False
                play_btn.config(text="▶ 播放BGM")
            else:
                # 优先播放已截取文件，否则提示去抖音搜索
                if bgm_trimmed and os.path.exists(bgm_trimmed):
                    self._mci_play(bgm_trimmed)
                    playing[0] = True
                    play_btn.config(text="⏹ 停止")
                else:
                    messagebox.showinfo("BGM试听",
                                        f"本曲尚未截取音频文件。\n\n发布时请在抖音「选择音乐」搜索：\n{bgm_name}",
                                        parent=top)

        play_btn = tk.Button(bgm_frame, text="▶ 播放BGM", bg="#333333", fg="#FFFFFF",
                             activebackground="#555555", relief="flat", font=(FONT, 9, "bold"),
                             cursor="hand2", padx=12, pady=4, command=_toggle_bgm)
        play_btn.pack(side="left")
        tk.Label(bgm_frame, text=f"🎵 {bgm_name}", bg="#000000", fg="#CCCCCC",
                 font=(FONT, 9)).pack(side="left", padx=(10, 0))
        if bgm_trimmed and os.path.exists(bgm_trimmed):
            tk.Label(bgm_frame, text="(已截取·可试听)", bg="#000000", fg=GREEN,
                     font=(FONT, 8)).pack(side="left", padx=(6, 0))

        # 推荐第2首（小字）
        if len(bgm_items) > 1:
            tk.Label(bgm_frame, text=f"备选：{bgm_items[1][0]}", bg="#000000", fg="#888888",
                     font=(FONT, 8)).pack(anchor="w", pady=(4, 0))

        # ===== 发布时间建议 =====
        tk.Label(top, text=f"⏰ 建议发布：{p['publish_time']}", bg="#000000", fg="#888888",
                 font=(FONT, 9)).pack(anchor="w", padx=20, pady=(10, 0))

        # 保持引用防止 GC
        top._carousel_imgs = carousel_imgs
        top.update_idletasks(); top.update()

    def _do_publish(self, p):
        """审核通过：读取 publish_package.json，交执行发布Agent填入抖音。
        使用全部字段：标题/正文/标签/BGM推荐/图片路径。"""
        self.clipboard_clear()
        self.clipboard_append(f"{p['titles'][0]}\n\n{p['caption']}\n\n{p['hashtags']}"); self.update()

        # 保存发布记录
        try:
            G.save_record(p, p["titles"][0], p["bgm"][0][0], "🟢审核通过·执行Agent发布中")
        except Exception:
            pass

        self._set_busy(True)
        self._open_publish_log()  # 执行日志窗口：实时展示发布Agent进度
        pkg_dir = p.get("package_dir", "")
        pkg_json = os.path.join(pkg_dir, "publish_package.json") if pkg_dir else ""

        # 查找 publish_package.json
        if pkg_json and os.path.exists(pkg_json):
            self._publish_log(f"📦 素材包：{os.path.basename(pkg_dir)} / publish_package.json")
            self._publish_log("🚀 正在启动发布流程（执行发布Agent）…")
            self.update_idletasks()
            P.publish_from_package_async(
                pkg_json,
                on_done=lambda result: self._on_publish_done(result, pkg_dir),
                log=lambda msg: self._publish_log(msg))
        else:
            # 降级：用 plan 对象的裸数据调 publish_async
            self._publish_log("⚠️ 无 publish_package.json，用基础数据发布…")
            self.status_var.set(f"⚠️ 无 publish_package.json，用基础数据发布…")
            self.update_idletasks()
            img_paths = [f for f in (p.get("package_files") or []) if f and os.path.exists(f)]
            # 从 plan 提取 tags 和 bgm
            hashtag_str = p.get("hashtags", "")
            tags = [t.replace("#", "").strip() for t in hashtag_str.split() if t.strip()]
            bgm_info = [{
                "display": item[0] if len(item) > 0 else "",
                "search_keyword": (item[1] or "").replace("抖音搜索：", "").strip() if len(item) > 1 else "",
                "reason": item[2] if len(item) > 2 else "",
                "clip_suggestion": item[3] if len(item) > 3 else "",
            } for item in (p.get("bgm") or [])]
            P.publish_async(
                caption=p.get("caption", ""), title=p.get("titles", [""])[0] if p.get("titles") else "",
                image_paths=img_paths, on_done=lambda result: self._on_publish_done(result, pkg_dir),
                log=lambda msg: self._publish_log(msg),
                tags=tags, bgm_info=bgm_info,
                hook=p.get("hook", ""), cover_text=(p.get("photo_tags", [""]) or [""])[0])

    def _open_publish_log(self):
        """发布执行日志窗口（M2-1）：实时展示发布Agent每一步进度。"""
        if self._publish_log_win is not None and self._publish_log_win.winfo_exists():
            try:
                self._publish_log_win.lift(); self._publish_log_win.focus_set()
            except Exception:
                pass
            return
        top = tk.Toplevel(self); top.title("🚀 发布执行日志")
        top.configure(bg=ROOT_BG)
        top.geometry("680x420")
        self.update_idletasks()
        x = self.winfo_rootx() + max(0, (self.winfo_width() - 680) // 2)
        y = self.winfo_rooty() + max(0, (self.winfo_height() - 420) // 2)
        top.geometry(f"+{x}+{y}")
        if os.path.exists(ICON_PATH):
            try:
                top.iconbitmap(ICON_PATH)
            except Exception:
                pass
        tk.Label(top, text="🚀 发布执行日志", bg=HEADER_BG, fg="#FFFFFF",
                 font=(FONT, 13, "bold"), anchor="w").pack(fill="x", ipady=8, padx=16)
        tk.Label(top, text="正在按素材包逐项填入抖音发布页，本窗口实时显示进度，请稍候…",
                 bg=ROOT_BG, fg=GRAY, font=(FONT, 9), anchor="w").pack(fill="x", padx=16, pady=(6, 0))
        wrap = tk.Frame(top, bg=ROOT_BG); wrap.pack(fill="both", expand=True, padx=16, pady=10)
        txt = tk.Text(wrap, font=("Consolas", 10), bg="#111318", fg="#E8EAED",
                      relief="flat", padx=14, pady=12, state="disabled", wrap="word")
        sb = ttk.Scrollbar(wrap, command=txt.yview); txt.config(yscrollcommand=sb.set)
        txt.pack(side="left", fill="both", expand=True); sb.pack(side="right", fill="y")
        top._log_txt = txt
        top.protocol("WM_DELETE_WINDOW", lambda: (top.destroy(),
                                                  setattr(self, "_publish_log_win", None)))
        self._publish_log_win = top
        top.update_idletasks(); top.update()

    def _publish_log(self, msg):
        """发布日志：控制台 + GUI状态栏 + 发布执行日志窗口"""
        try:
            print(msg)
        except Exception:
            pass
        try:
            self.status_var.set(f"  {msg[:80]}")
            self.update_idletasks()
        except Exception:
            pass
        try:
            w = self._publish_log_win
            if w is not None and w.winfo_exists():
                t = w._log_txt
                t.config(state="normal")
                t.insert("end", msg + "\n")
                t.see("end")
                t.config(state="disabled")
                w.update_idletasks()
        except Exception:
            pass

    def _on_publish_done(self, result, pkg_dir):
        """发布流程完成回调"""
        self._set_busy(False)
        self.confirm_btn.config(state="normal")
        self._mark_saved()
        ok = result.get("ok", False) if isinstance(result, dict) else False
        msg = result.get("message", "") if isinstance(result, dict) else str(result)
        pkg_name = os.path.basename(pkg_dir) if pkg_dir else "?"
        if ok:
            self._publish_log(f"✅ 已完成｜{pkg_name}｜请在抖音发布页手动确认发布")
            self.status_var.set(f"✅ 已填入抖音发布页｜{pkg_name}｜请手动确认发布")
            self._set_step(4)  # 发布完成
        else:
            self._publish_log(f"⚠️ 发布遇到问题：{msg}｜素材包：{pkg_name}")
            self.status_var.set(f"⚠️ 发布遇到问题：{msg[:60]}｜素材包：{pkg_name}")

    def _set_busy(self, busy):
        st = "disabled" if busy else "normal"
        self.gen_btn.config(state=st); self.confirm_btn.config(state=st)


def _run_selftest_clean():
    """无界面引擎自检（隔离版）：把测试成品包/记录写进临时目录，跑完自动清理，
    不污染真实输出目录（D:/抖音发布全部zip）和 07_发布记录.xlsx。"""
    import shutil, tempfile
    s = G.load_settings()
    old_out = s.get("output_dir", "")
    tmp_out = tempfile.mkdtemp(prefix="selftest_")
    s["output_dir"] = tmp_out
    G.save_settings(s)
    old_rec = G.RECORD_XLSX
    G.RECORD_XLSX = os.path.join(tmp_out, "_selftest_rec.xlsx")
    try:
        rc = G.selftest()
    finally:
        G.RECORD_XLSX = old_rec
        s["output_dir"] = old_out
        G.save_settings(s)
        shutil.rmtree(tmp_out, ignore_errors=True)
        shutil.rmtree(os.path.join(G.OUTPUT_DIR, "_selftest"), ignore_errors=True)
    return rc


def main():
    if "--selftest" in sys.argv:
        sys.exit(_run_selftest_clean())
    if "--pubcheck" in sys.argv:
        print("自动发布组件：", P.check()); sys.exit(0)

    if "--uitest" in sys.argv:
        app = None
        try:
            app = App(); app.update_idletasks()
            tmpl, code, extras = _find_sample_photos()
            assert tmpl and code and extras, f"缺少测试照片 tmpl={tmpl} code={code} extras={extras}"
            app.code = [code]; app.extras = list(extras)          # code 为列表，extras 为纯路径列表
            app._ov_tagline_var.set("转行ing"); app.tagline = "转行ing"
            app._render_cover_preview()
            assert os.path.exists(app._cover_preview) and os.path.getsize(app._cover_preview) > 5000
            # 封面=固定模板（素材库那张黑底主题照），智能体按期数+主题自动改
            fixed = app._fixed_template()
            assert fixed == tmpl, f"固定模板不对 fixed={fixed} tmpl={tmpl}"
            n0 = len(app.extras)
            app._refresh_photos(); app.update_idletasks()
            assert "生活/学习" in app._photo_summary_var.get()
            strip0 = len(app._strip_cells)
            app._open_overview(); app.update_idletasks(); app.update()
            cards0 = len(app._ov_cards)                        # 封面+代码+N 张 = 2+N
            # ✕ 删除（总览卡片右上角）
            app._remove_extra(0); app.update_idletasks()
            n_del, cards_del, strip_del = len(app.extras), len(app._ov_cards), len(app._strip_cells)
            # 换（保留的小「更换」能力）
            old0 = app.extras[0]; app.extras[0] = tmpl; app._refresh_photos(); app.update_idletasks()
            replaced = (app.extras[0] == tmpl); app.extras[0] = old0; app._refresh_photos()
            # 加（唯一的生活/学习入口，一次可多张）
            app.extras.append(extras[0]); app._refresh_photos(); app.update_idletasks()
            n_add, cards_add = len(app.extras), len(app._ov_cards)
            # 端到端生成：封面宽度统一720px
            app.week_var.set(4); app.theme_var.set("Python三件套")
            app._rebuild_learned_fields()
            if app._learned_entries:
                app._learned_entries[0].set("RAG检索增强生成")
            app.completed_txt.insert("1.0", "第一个AI聊天机器人")
            app.on_generate(); app.update_idletasks()
            cover = app.plan["package_files"][0]
            from PIL import Image as _Im
            cw, ch = _Im.open(cover).size
            ok = (n_del == n0 - 1 and cards_del == cards0 - 1 and n_add == n_del + 1
                  and cards_add == cards_del + 1 and replaced and strip0 >= 3
                  and os.path.exists(cover) and cw == 720)
            print(f"UITEST 真实照片：固定模板={os.path.basename(tmpl)} 代码={os.path.basename(code)} 生活/学习{n0}张")
            print(f"UITEST extras {n0}->{n_del}(x删)->{n_add}(加) 换={replaced} | 总览卡片 {cards0}->{cards_del}->{cards_add} | 缩略图条 {strip0} | 封面 {cw}x{ch}")
            print("UITEST", "OK 固定封面/增/删/换/排序 全部正常" if ok else "FAIL")
            sys.exit(0 if ok else 1)
        finally:
            if app is not None:
                try:
                    app._close_overview()
                except Exception:
                    pass
                try:
                    app.destroy()
                except Exception:
                    pass

    if "--screenshot" in sys.argv:
        i = sys.argv.index("--screenshot")
        out = sys.argv[i + 1] if i + 1 < len(sys.argv) else os.path.join(ASSETS, "app_preview.png")
        overview_out = os.path.join(ASSETS, "app_preview_overview.png")
        app = App(); app.update_idletasks(); app.update()
        from PIL import ImageGrab
        tmpl, code, extras = _find_sample_photos()
        if code:
            app.code = [code]
        if extras:
            app.extras = list(extras)
        app._ov_tagline_var.set("转行ing"); app.tagline = "转行ing"
        app.week_var.set(4); app.theme_var.set("Python三件套")
        app._rebuild_learned_fields()
        if app._learned_entries:
            app._learned_entries[0].set("RAG检索增强生成")
        app.completed_txt.insert("1.0", "第一个AI聊天机器人")
        app.difficulty_txt.insert("1.0", "RAG召回率还不稳定")
        app._render_cover_preview(); app._refresh_photos()
        app.on_generate(); app.update_idletasks(); app.update()
        inner = app._scroll_inner; canvas = app._scroll_canvas
        strip_mapped = [c.winfo_ismapped() for c in app._strip_cells]
        btns_mapped = [app._btn_code.winfo_ismapped(), app._btn_extras.winfo_ismapped(),
                       app._btn_overview.winfo_ismapped()]
        print("LAYOUT strip_mapped=%s btns_mapped=%s confirm_mapped=%s inner_req_h=%d canvas_h=%d needs_scroll=%s"
              % (strip_mapped, btns_mapped, app.confirm_btn.winfo_ismapped(), inner.winfo_reqheight(),
                 canvas.winfo_height(), inner.winfo_reqheight() > canvas.winfo_height()))

        def _grab_main():
            try:
                app.update_idletasks()
                x, y = app.winfo_rootx(), app.winfo_rooty()
                w, h = app.winfo_width(), app.winfo_height()
                ImageGrab.grab(bbox=(x, y, x + w, y + h)).save(out)
                print("PREVIEW_SAVED", out)
            except Exception as e:
                print("SHOT_ERR", e)
            app._open_overview()
            try:
                app._overview.attributes("-topmost", True); app._overview.lift()
            except Exception:
                pass
            app._overview.update_idletasks()
            req = app._ov_inner.winfo_reqheight()
            nh = min(app.winfo_screenheight() - 40, req + 230)
            app._overview.geometry(f"620x{nh}+{app.winfo_rootx() + 30}+{max(0, app.winfo_rooty())}")
            app._overview.update(); app.after(450, _grab_overview)

        def _grab_overview():
            try:
                app._overview.update_idletasks()
                ox, oy = app._overview.winfo_rootx(), app._overview.winfo_rooty()
                ow, oh = app._overview.winfo_width(), app._overview.winfo_height()
                ImageGrab.grab(bbox=(ox, oy, ox + ow, oy + oh)).save(overview_out)
                print("OVERVIEW_SAVED", overview_out, "cards=", len(app._ov_cards), "h=", oh)
            except Exception as e:
                print("SHOT_ERR", e)
            app._close_overview(); app.destroy()

        def _shot():
            try:
                app.attributes("-topmost", True); app.lift(); app.focus_force()
            except Exception:
                pass
            app.update(); app.after(300, _grab_main)
        app.after(900, _shot); app.mainloop(); sys.exit(0)

    app = App(); app.mainloop()


if __name__ == "__main__":
    main()
