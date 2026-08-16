# -*- coding: utf-8 -*-
"""M2.1 定义点提取（分类型）。

TODO(T2.2): 按 `dimtype & 0x07` 判定类型，依类型提取「应吸附」定义点
（组码 13/14/10/15），OCS→WCS 变换。遵守两处纠正：
直径 10/15 是对端点（圆心=中点）；坐标标注只查 13。见 ARCHITECTURE.md §3.1。
"""
from __future__ import annotations
