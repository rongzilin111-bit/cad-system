# -*- coding: utf-8 -*-
"""T7.4 代码质量：注释率统计与核查。

验收口径（requirements §代码质量 / plan.md T7.4）：
    注释率 ≥25%，关键算法附原理说明；人工 / 脚本核查达标。

本模块提供可复现的「脚本核查」：`analyze_tree` 遍历源码统计注释率与模块 docstring
覆盖率，`QualityReport` 判定是否达标，`python -m app.quality` 一键出报告。
"""
