# -*- coding: utf-8 -*-
"""
Excalidraw 场景渲染脚本
======================
用 Playwright 打开 excalidraw.com（官方在线版），
导入 .excalidraw 场景文件，全选后导出为 PNG 图片。

用法：python 工具调用流程图_渲染PNG.py
输出：工具调用流程图.png
"""
import base64
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

HERE = Path(__file__).parent
SCENE_FILE = HERE / "工具调用流程图.excalidraw"
OUT_PNG = HERE / "工具调用流程图.png"


def main():
    scene = SCENE_FILE.read_text(encoding="utf-8")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={"width": 1600, "height": 1000},
            permissions=["clipboard-read", "clipboard-write"],
        )
        page = context.new_page()
        print("正在打开 excalidraw.com ...")
        page.goto("https://excalidraw.com", wait_until="domcontentloaded", timeout=90000)
        page.wait_for_timeout(5000)  # 等待应用初始化

        # 1) 把场景 JSON 写入浏览器剪贴板
        page.evaluate("async (s) => { await navigator.clipboard.writeText(s); }", scene)
        print("场景已写入剪贴板")

        # 2) 模拟粘贴事件导入场景
        page.evaluate(
            """(s) => {
                const evt = new ClipboardEvent('paste', {
                    bubbles: true, cancelable: true,
                    clipboardData: new DataTransfer(),
                });
                evt.clipboardData.setData('text/plain', s);
                document.dispatchEvent(evt);
            }""",
            scene,
        )
        page.wait_for_timeout(4000)

        # 3) 全选所有元素
        page.keyboard.press("Control+a")
        page.wait_for_timeout(1000)

        # 4) 触发导出为 PNG（导出结果会复制到剪贴板）
        print("正在导出 PNG ...")
        result = page.evaluate(
            """async () => {
                const items = await navigator.clipboard.read();
                const before = items.length;
                // 使用快捷键 Ctrl+Shift+E 打开导出对话框（新版本默认直接导出）
                document.dispatchEvent(new KeyboardEvent('keydown', {
                    key: 'e', code: 'KeyE',
                    ctrlKey: true, shiftKey: true,
                    bubbles: true, cancelable: true,
                }));
                return { itemsBefore: before };
            }"""
        )
        print("导出快捷键已触发:", result)
        page.wait_for_timeout(6000)

        # 5) 读取剪贴板中的 PNG
        png_b64 = page.evaluate(
            """async () => {
                const items = await navigator.clipboard.read();
                for (const item of items) {
                    for (const type of item.types) {
                        if (type.startsWith('image/')) {
                            const blob = await item.getType(type);
                            const buf = await blob.arrayBuffer();
                            let bin = '';
                            const bytes = new Uint8Array(buf);
                            for (let i = 0; i < bytes.length; i++) bin += String.fromCharCode(bytes[i]);
                            return btoa(bin);
                        }
                    }
                }
                return null;
            }"""
        )
        if not png_b64:
            print("错误：剪贴板中未找到图片，导出失败")
            browser.close()
            sys.exit(1)

        OUT_PNG.write_bytes(base64.b64decode(png_b64))
        print(f"已导出: {OUT_PNG}  ({OUT_PNG.stat().st_size / 1024:.0f} KB)")
        browser.close()


if __name__ == "__main__":
    main()
