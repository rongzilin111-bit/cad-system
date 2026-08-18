# -*- coding: utf-8 -*-
"""程序入口：启动 GUI（T6.1）。

导入 `app.gui.main_window.run()` 启动 PySide6 主窗口。PySide6 缺失时给出
清晰的安装提示，而非抛异常崩溃（`pip install -r requirements.txt`）。
"""
from __future__ import annotations


def main() -> None:
    try:
        from app.gui.main_window import run
    except ImportError as exc:
        if "PySide6" in str(exc):
            print("PySide6 未安装 —— 请先执行：pip install -r requirements.txt")
            raise SystemExit(1)
        raise
    raise SystemExit(run())


if __name__ == "__main__":
    main()
