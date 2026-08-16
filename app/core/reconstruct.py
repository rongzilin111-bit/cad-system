# -*- coding: utf-8 -*-
"""M3.3 测量点位吸附重构。

TODO(T3.3): 脱钩定义点按类别吸附：角点型→KDTree 最近特征点；
曲线上型→几何网格内投影；圆心型→最近圆心。吸附后记录纠偏坐标与最近实体，
直径/半径做一致性自检。见 ARCHITECTURE.md §3.3。
"""
from __future__ import annotations
