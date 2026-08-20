# -*- coding: utf-8 -*-
"""T7.3 兼容性与稳定性包：版本矩阵 + 损坏文件 + 无泄漏自测。

三个模块分工（对齐 `app/acceptance` / `app/performance` 的「核心可无 CLI 单测
+ 命令行一键出报告」结构）：
    - `matrix.py`  AutoCAD 2007–2025 版本兼容矩阵（抽样 20 文件，加载 + 检测）；
    - `corrupt.py`  损坏文件友好提示（任意损坏输入不崩溃，抛友好 LoadError）；
    - `stress.py`   内存稳定性（`tracemalloc` 稳态比较，验证无泄漏）；
    - `__main__.py` 命令行入口 `python -m app.compat`，一键跑三项出报告。
"""
