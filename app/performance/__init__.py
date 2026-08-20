# -*- coding: utf-8 -*-
"""T7.2 性能测试包：计时实测「小图 ≤1s」与「大图合理耗时」。

三个模块分工：
    - `bench.py`     计时器 + 确定性小图生成器 + 报告/阈值（可无 CLI 单测）；
    - `__main__.py`  命令行入口 `python -m app.performance`，一键计时出报告。
"""
