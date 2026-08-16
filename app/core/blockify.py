# -*- coding: utf-8 -*-
"""M4 图元标准化：DIMENSION → 块、归层。

TODO(T4.1/T4.2): 方案 A「复用重命名 *D 块」——改名→清匿名标志→建 INSERT→删原
DIMENSION；INSERT 到块 base_point 保证视觉不变；逐图元归层 Dim_Reconstruct_Layer。
孤儿 *D 块默认不删。见 ARCHITECTURE.md §4。
"""
from __future__ import annotations
