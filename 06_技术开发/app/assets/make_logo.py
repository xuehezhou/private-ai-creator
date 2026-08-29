# -*- coding: utf-8 -*-
"""
make_logo.py —— Logo 生成器
============================
设计理念：
- 深色圆角底（#171823）= 抖音暗色视觉基因
- 「AI」故障错位字：青色左移 / 红色右移 / 白色居中 = 经典故障风
- 底部青→红渐变声波条 = 视频/音乐内容属性
运行一次即可：python make_logo.py
产物：logo.png（程序头部用）、icon.ico（窗口+桌面快捷方式图标）
"""
import os
from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
SIZE = 512
BG = (23, 24, 35, 255)
CYAN = (37, 244, 238, 255)
RED = (254, 44, 133, 255)
WHITE = (255, 255, 255, 255)


def load_font(size):
    for fp in ("C:/Windows/Fonts/arialbd.ttf",
               "C:/Windows/Fonts/DejaVuSans-Bold.ttf",
               "C:/Windows/Fonts/arial.ttf"):
        if os.path.exists(fp):
            try:
                return ImageFont.truetype(fp, size)
            except Exception:
                continue
    return ImageFont.load_default()


def draw_glitch_text(draw, text, font, cx, cy):
    """青色(-dx) / 红色(+dx) / 白色居中 三层错位"""
    bbox = draw.textbbox((0, 0), text, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    x = cx - tw // 2 - bbox[0]
    y = cy - th // 2 - bbox[1]
    dx = max(6, SIZE // 48)
    draw.text((x - dx, y), text, font=font, fill=CYAN)
    draw.text((x + dx, y), text, font=font, fill=RED)
    draw.text((x, y), text, font=font, fill=WHITE)


def make():
    img = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    # 圆角底
    d.rounded_rectangle([8, 8, SIZE - 8, SIZE - 8], radius=118, fill=BG)
    # 内描边微光
    d.rounded_rectangle([14, 14, SIZE - 14, SIZE - 14], radius=112,
                        outline=(37, 244, 238, 40), width=2)

    # 主字 AI
    font = load_font(236)
    draw_glitch_text(d, "AI", font, SIZE // 2, SIZE // 2 - 42)

    # 底部声波条（青→红渐变感）
    bars = 9
    bw, gap = 20, 14
    total = bars * bw + (bars - 1) * gap
    x0 = (SIZE - total) // 2
    y_base = SIZE - 108
    heights = [22, 44, 66, 40, 78, 34, 60, 46, 24]
    for i in range(bars):
        t = i / (bars - 1)
        color = (int(37 + (254 - 37) * t), int(244 + (44 - 244) * t),
                 int(238 + (133 - 238) * t), 255)
        h = heights[i]
        x = x0 + i * (bw + gap)
        d.rounded_rectangle([x, y_base - h // 2, x + bw, y_base + h // 2],
                            radius=10, fill=color)

    # 导出
    logo_path = os.path.join(HERE, "logo.png")
    img.save(logo_path)

    ico_path = os.path.join(HERE, "icon.ico")
    img.save(ico_path, sizes=[(16, 16), (24, 24), (32, 32), (48, 48),
                              (64, 64), (128, 128), (256, 256)])

    print(f"logo.png 已生成：{logo_path}（{os.path.getsize(logo_path)} bytes）")
    print(f"icon.ico 已生成：{ico_path}（{os.path.getsize(ico_path)} bytes）")


if __name__ == "__main__":
    make()
