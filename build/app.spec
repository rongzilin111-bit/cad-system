# -*- mode: python ; coding: utf-8 -*-
# PyInstaller 打包配置（onedir 模式，见 ARCHITECTURE.md §2.4）
# 用法：pyinstaller build/app.spec

a = Analysis(
    ['../main.py'],
    pathex=['..'],
    hiddenimports=[
        'ezdxf',
        'ezdxf.addons',
        'PySide6.QtWidgets',
        'PySide6.QtCore',
    ],
    datas=[],
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    name='dimension-reconstruct',
    console=False,
)
coll = COLLECT(exe, a.binaries, a.datas, name='dimension-reconstruct')
