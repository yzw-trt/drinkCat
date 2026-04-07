#!/usr/bin/env python3
"""在项目根目录执行: python build.py

等价于原 build.bat：带 --clean 调用 PyInstaller，避免更换 logo.ico 后仍嵌入旧图标。
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def main() -> int:
    root = Path(__file__).resolve().parent
    spec = root / "drinkCat.spec"
    if not spec.is_file():
        print(f"未找到 {spec}", file=sys.stderr)
        return 1

    # 与 bat 里 chcp 65001 类似，减轻控制台与 PyInstaller 日志乱码（Win10/11 通常有效）
    env = {**os.environ, "PYTHONUTF8": "1"} if sys.platform == "win32" else None

    r = subprocess.run(
        [sys.executable, "-m", "PyInstaller", "--clean", "--noconfirm", str(spec)],
        cwd=root,
        env=env,
    )
    if r.returncode != 0:
        return r.returncode

    print()
    print("完成: dist\\drinkCat.exe")
    print("若资源管理器里仍显示旧图标，请刷新 Windows 图标缓存或注销/重启。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
