# -*- coding: utf-8 -*-
"""程序入口：启动 GUI。

TODO(T6.1): 接入 app.gui.main_window，启动 PySide6 主窗口。
当前为骨架阶段，仅验证依赖环境。
"""
from __future__ import annotations


def _check_deps() -> None:
    """打印关键依赖版本，便于快速确认环境。"""
    import sys

    print(f"Python {sys.version.split()[0]}")

    try:
        import ezdxf
        print(f"ezdxf {ezdxf.__version__}")
    except ImportError:
        print("ezdxf 未安装 —— pip install -r requirements.txt")

    try:
        import numpy
        print(f"numpy {numpy.__version__}")
    except ImportError:
        print("numpy 未安装")

    try:
        import scipy
        print(f"scipy {scipy.__version__}")
    except ImportError:
        print("scipy 未安装")

    try:
        import PySide6
        print(f"PySide6 {PySide6.__version__}")
    except ImportError:
        print("PySide6 未安装")


def main() -> None:
    _check_deps()
    # TODO(T6.1): 启动 GUI
    # from app.gui.main_window import run
    # run()


if __name__ == "__main__":
    main()
