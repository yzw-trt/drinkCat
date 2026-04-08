# -*- mode: python ; coding: utf-8 -*-
# 打包：python build.py  或  pyinstaller --clean --noconfirm drinkCat.spec
# 勿使用 collect_all('PyQt6')，否则会打进全部 Qt 模块，体积暴涨。
# 更换 logo.ico 后请带 --clean；若 dist 里已是新图标但资源管理器仍显示蓝色块，是 Windows 图标缓存，需刷新缓存或注销/重启。

import os

_icon = os.path.join(os.path.dirname(os.path.abspath(SPEC)), "logo.ico")
if not os.path.isfile(_icon):
    raise FileNotFoundError(
        f"缺少图标文件: {_icon}\n请将 logo.ico 放在与 drinkCat.spec 同一目录后重新打包。"
    )

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=["PyQt6.QtSvg"],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='drinkCat',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=_icon,
)
