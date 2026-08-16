# -*- coding: utf-8 -*-
"""空间索引：几何特征点提取 + KDTree + 几何网格。

TODO(T2.3): 从模型空间几何（LINE/ARC/CIRCLE/SPLINE/POLYLINE/ELLIPSE/POINT）
提取特征点（37,829 量级），构建 scipy.cKDTree（回退 numpy 网格 / 暴力），
并构建几何网格供「曲线上型」吸附。见 ARCHITECTURE.md §3.2。
"""
from __future__ import annotations
