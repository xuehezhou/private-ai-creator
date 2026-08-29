# -*- coding: utf-8 -*-
"""
工具调用流程图生成脚本
======================
生成标准 .excalidraw 场景文件（手绘风格流程图），
描述 Claude AI 工具调用的完整循环流程。

用法：python 工具调用流程图_生成脚本.py
输出：工具调用流程图.excalidraw（可直接拖入 excalidraw.com 编辑）
"""
import json
import random
from pathlib import Path

random.seed(20260804)  # 固定种子，重复生成结果一致

OUT_PATH = Path(__file__).parent / "工具调用流程图.excalidraw"

FONT = "'Segoe UI', 'Microsoft YaHei', sans-serif"
ARROW_FONT = "'Segoe UI', 'Microsoft YaHei', cursive"

INK = "#1e1e1e"
GRAY_TEXT = "#495057"
BLUE = ("#a5d8ff", "#1971c2", "#1971c2")     # (背景, 边框, 文字)
YELLOW = ("#ffec99", "#f08c00", "#e8590c")
GREEN = ("#b2f2bb", "#2f9e44", "#2f9e44")
GRAY = ("#e9ecef", "#868e96", "#495057")

UPDATED = 1754265600000  # 固定时间戳，保证可复现


def new_id():
    return "".join(random.choices("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789", k=12))


def seed():
    return random.randint(1, 2**31)


def base(el_type, x, y, w, h, stroke, bg="transparent", stroke_style="solid", stroke_width=2):
    return {
        "id": new_id(), "type": el_type,
        "x": x, "y": y, "width": w, "height": h, "angle": 0,
        "strokeColor": stroke, "backgroundColor": bg,
        "fillStyle": "solid", "strokeWidth": stroke_width, "strokeStyle": stroke_style,
        "roughness": 1, "opacity": 100,
        "groupIds": [], "frameId": None, "roundness": None,
        "seed": seed(), "version": 1, "versionNonce": seed(),
        "isDeleted": False, "boundElements": None,
        "updated": UPDATED, "link": None, "locked": False,
    }


def text_width(text, font_size):
    """估算文字像素宽度：CJK 按 1.0 倍字号，ASCII 按 0.62 倍"""
    return sum(font_size if ord(c) > 0x2E00 else font_size * 0.62 for c in text)


def make_rect(x, y, w, h, palette, dashed=False):
    bg, stroke, _ = palette
    r = base("rectangle", x, y, w, h, stroke, bg=bg,
             stroke_style="dashed" if dashed else "solid")
    r["roundness"] = {"type": 3}
    return r


def make_bound_text(rect, text, color, font_size=18):
    """生成绑定在矩形内的居中文本，并互相挂载 boundElements"""
    lines = text.split("\n")
    w = max(text_width(l, font_size) for l in lines)
    h = len(lines) * font_size * 1.25
    t = base("text",
             rect["x"] + (rect["width"] - w) / 2,
             rect["y"] + (rect["height"] - h) / 2,
             w, h, color)
    t.update({
        "text": text, "fontSize": font_size, "fontFamily": 1,
        "textAlign": "center", "verticalAlign": "middle",
        "containerId": rect["id"], "originalText": text,
        "autoResize": True, "lineHeight": 1.25,
    })
    rect["boundElements"] = (rect["boundElements"] or []) + [{"id": t["id"], "type": "text"}]
    return t


def make_label(x, y, text, font_size=15, color=GRAY_TEXT, font=ARROW_FONT, align="left"):
    """独立文本标签（无容器）；FONT=2 无衬线，ARROW_FONT=1 手写体"""
    lines = text.split("\n")
    w = max(text_width(l, font_size) for l in lines)
    h = len(lines) * font_size * 1.25
    t = base("text", x, y, w, h, color)
    t.update({
        "text": text, "fontSize": font_size, "fontFamily": 2 if font == FONT else 1,
        "textAlign": align, "verticalAlign": "top",
        "containerId": None, "originalText": text,
        "autoResize": True, "lineHeight": 1.25,
    })
    return t


def make_arrow(points_abs, label=None, label_offset=(12, 0), dashed=False,
               label_size=15, label_color=GRAY_TEXT):
    """points_abs 为绝对坐标点列，第一个点为起点"""
    x0, y0 = points_abs[0]
    pts = [[px - x0, py - y0] for px, py in points_abs]
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    a = base("arrow", x0, y0, max(xs) - min(xs), max(ys) - min(ys), INK,
             stroke_style="dashed" if dashed else "solid")
    a["points"] = pts
    a["lastCommittedPoint"] = None
    a["startBinding"] = None
    a["endBinding"] = None
    a["startArrowhead"] = None
    a["endArrowhead"] = "arrow"
    a["elbowed"] = False
    extras = []
    if len(points_abs) > 2:
        a["roundness"] = {"type": 3}  # 折角圆滑
    if label:
        lx = x0 + pts[1][0] / 2 + label_offset[0]
        ly = y0 + pts[1][1] / 2 + label_offset[1]
        extras.append(make_label(lx, ly, label, font_size=label_size, color=label_color))
    return [a] + extras


elements = []

# ── 标题 ─────────────────────────────────────────────
elements.append(make_label(40, -55, "工具调用流程图", font_size=28, color=INK, font=FONT))

# ── 主流程节点（左列 x=40 w=280 h=80） ────────────────
NODES = [
    ("用户输入请求",            40,   40, BLUE),
    ("Claude AI 理解任务",      40,  190, BLUE),
    ("制定工具调用计划",         40,  340, YELLOW),
    ("发出工具调用请求",         40,  490, YELLOW),
    ("执行权限检查",            40,  640, GRAY),
    ("执行工具操作",            40,  790, YELLOW),
    ("返回工具执行结果",         40,  940, GRAY),
    ("Claude 汇总并输出回答",    40, 1090, BLUE),
]
for name, x, y, palette in NODES:
    r = make_rect(x, y, 280, 80, palette)
    elements.append(r)
    elements.append(make_bound_text(r, name, palette[2], font_size=18))

# ── 工具列表（右列，绿色小框） ────────────────────────
TOOLS = [
    ("读写文件",         400, 470),
    ("运行命令",         400, 550),
    ("网络搜索",         400, 630),
    ("调用其他 MCP 工具", 400, 710),
]
for name, x, y in TOOLS:
    r = make_rect(x, y, 170, 60, GREEN)
    elements.append(r)
    elements.append(make_bound_text(r, name, GREEN[2], font_size=16))

# 工具区虚线框 + 标题
elements.append(make_rect(375, 445, 220, 340, GRAY, dashed=True))
elements.append(make_label(395, 415, "AI 可调用的工具", font_size=15, color=GRAY_TEXT, font=FONT))

# ── 主流程箭头（垂直串联） ────────────────────────────
MAIN_ARROWS = [
    (120, 190, "提交任务"),
    (270, 340, "理解后规划"),
    (420, 490, "按计划调用"),
    (570, 640, "发起调用"),
]
for y_start, y_end, label in MAIN_ARROWS:
    elements += make_arrow([(180, y_start), (180, y_end)], label=label)

# 权限检查 → 执行工具（允许 / 拒绝）
elements += make_arrow([(180, 720), (180, 790)], label="允许", label_offset=(14, 0))
elements.append(make_label(68, 738, "拒绝 / 修改", font_size=14))

elements += make_arrow([(180, 870), (180, 940)], label="得到结果")
elements += make_arrow([(180, 1020), (180, 1090)], label="继续推理")

# ── 调用请求 → 工具（虚线扇出） ───────────────────────
for name, x, y in TOOLS:
    elements += make_arrow([(320, 530), (x - 8, y + 30)], dashed=True)

# ── 循环回路：输出回答 → 制定计划（左侧绕行折线） ──────
elements += make_arrow(
    [(40, 1110), (-70, 1090), (-70, 400), (40, 380)],
)
elements.append(make_label(-178, 540, "循环执行\n直到任务完成", font_size=16))

# ── 补充说明文字 ─────────────────────────────────────
elements.append(make_label(350, 345, "判断需要哪些工具\n决定调用顺序", font_size=16))
elements.append(make_label(360, 800, "危险操作需人工确认\n用户授权后才放行", font_size=16))
elements.append(make_label(210, 1030, "读取结果 · 校验信息\n判断任务是否完成", font_size=15))

# ── 图例 ─────────────────────────────────────────────
elements.append(make_label(40, 1210, "蓝色节点 = 用户与 AI 交互", font_size=16, color=BLUE[2], font=FONT))
elements.append(make_label(40, 1242, "黄色节点 = AI 工具调用流程", font_size=16, color=YELLOW[2], font=FONT))
elements.append(make_label(40, 1274, "灰色节点 = 系统与结果处理", font_size=16, color=GRAY[1], font=FONT))
elements.append(make_label(40, 1306, "绿色节点 = 具体工具类型", font_size=16, color=GREEN[2], font=FONT))

scene = {
    "type": "excalidraw",
    "version": 2,
    "source": "https://excalidraw.com",
    "elements": elements,
    "appState": {"gridSize": None, "viewBackgroundColor": "#ffffff"},
    "files": {},
}

OUT_PATH.write_text(json.dumps(scene, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"已生成: {OUT_PATH}")
print(f"元素数量: {len(elements)}")
