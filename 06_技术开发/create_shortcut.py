# -*- coding: utf-8 -*-
"""
create_shortcut.py —— 在桌面创建快捷方式（带自定义图标）
========================================================
双击桌面「AI抖音创作智能体」即可无黑窗启动程序。
路径全部相对本脚本所在目录自动计算；移动项目文件夹后重跑一次即可修复快捷方式。

实现要点：
- 通过 PowerShell 的 WScript.Shell COM 创建真正的 .lnk 快捷方式
- 用 -EncodedCommand(UTF-16LE) 规避 Windows 中文代码页导致的乱码
- 目标程序用 pythonw.exe（不弹黑色控制台窗口）
"""
import os
import sys
import base64
import subprocess

ROOT = os.path.dirname(os.path.abspath(__file__))
ICON = os.path.join(ROOT, "app", "assets", "icon.ico")
MAIN = os.path.join(ROOT, "app", "main.py")
PYW = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
if not os.path.exists(PYW):
    PYW = "pythonw.exe"
NAME = "AI抖音创作智能体"

PS = r"""
$root   = '{root}'
$icon   = '{icon}'
$main   = '{main}'
$pyw    = '{pyw}'
$name   = '{name}'
$desktop = [Environment]::GetFolderPath('Desktop')
if (-not (Test-Path $pyw)) {{ $pyw = (Get-Command pythonw -ErrorAction SilentlyContinue).Source }}
$ws = New-Object -ComObject WScript.Shell
$sc = $ws.CreateShortcut("$desktop\$name.lnk")
$sc.TargetPath       = $pyw
$sc.Arguments        = "`"$main`""
$sc.WorkingDirectory = $root
$sc.IconLocation     = "$icon,0"
$sc.Description      = $name
$sc.Save()
Write-Output ("OK -> " + "$desktop\$name.lnk")
""".format(
    root=ROOT.replace("\\", "\\\\"),
    icon=ICON.replace("\\", "\\\\"),
    main=MAIN.replace("\\", "\\\\"),
    pyw=PYW.replace("\\", "\\\\"),
    name=NAME,
)


def main():
    if not os.path.exists(MAIN):
        print("[错误] 找不到主程序：", MAIN)
        return 1
    encoded = base64.b64encode(PS.encode("utf-16-le")).decode("ascii")
    # 中文 Windows 下 PowerShell 标准输出是 GBK，不能用 utf-8 解码
    r = subprocess.run(["powershell", "-NoProfile", "-EncodedCommand", encoded],
                       capture_output=True)
    out = (r.stdout or b"").decode("gbk", errors="replace").strip()
    err = (r.stderr or b"").decode("gbk", errors="replace").strip()
    print(out)
    if r.returncode != 0:
        print("[PowerShell 错误]", err)
        return r.returncode
    print("桌面快捷方式创建完成：双击「%s」即可打开智能体。" % NAME)
    return 0


if __name__ == "__main__":
    sys.exit(main())
