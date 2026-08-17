# -*- coding: utf-8 -*-
"""曲线空间索引单测（T2.3「曲线上型」吸附）。

覆盖点到线段 / 圆 / 圆弧的精确距离，以及 `CurveIndex` 网格最近曲线查询。
这些是 M2 判定「定义点是否落在曲线中段（非顶点）」的基础。
"""
from __future__ import annotations

import math

import ezdxf

from app.core.curve_index import (
    CurveIndex,
    CurvePrimitive,
    _point_segment_dist,
)


def test_point_segment_dist():
    """点到线段：段上→0；投影在段内→垂距；投影在段外→端点距离。"""
    assert _point_segment_dist(5, 0, 0, 0, 10, 0) == 0.0      # 段上
    assert _point_segment_dist(5, 3, 0, 0, 10, 0) == 3.0      # 垂直投影段内
    assert _point_segment_dist(-2, 0, 0, 0, 10, 0) == 2.0     # 左端点外
    assert _point_segment_dist(12, 0, 0, 0, 10, 0) == 2.0     # 右端点外


def test_circle_distance():
    p = CurvePrimitive("circle", "CIRCLE", "A", (0, 0, 5))
    assert abs(p.distance(5, 0)) < 1e-12           # 圆上
    assert abs(p.distance(0, 0) - 5) < 1e-12       # 圆心 → 距离 = r
    assert abs(p.distance(3, 0) - 2) < 1e-12       # 圆内点 → |r - dist|


def test_arc_distance():
    # 圆弧：90°（0→π/2），半径 5，圆心原点。
    p = CurvePrimitive("arc", "ARC", "A", (0, 0, 5, 0, math.pi / 2))
    assert abs(p.distance(5, 0)) < 1e-12           # 起点 (5,0) 在弧上
    # 弧外点 (0,-5)：不在弧角范围，取到最近端点 (5,0) 的距离 = 5√2
    assert abs(p.distance(0, -5) - 5 * math.sqrt(2)) < 1e-9
    # 弧上点 (5cos45°, 5sin45°) 在弧内 → 0
    x = 5 * math.cos(math.pi / 4)
    y = 5 * math.sin(math.pi / 4)
    assert abs(p.distance(x, y)) < 1e-12


def test_curve_index_nearest_midsegment_and_circle():
    """最近曲线：线段中段（非端点）与圆上非象限点都应命中距离 0。"""
    doc = ezdxf.new("R2018")
    msp = doc.modelspace()
    msp.add_line((0, 0), (100, 0))
    msp.add_circle((50, 50), radius=10)
    ci = CurveIndex(list(doc.modelspace()))

    # 线段中段 (50,0)：离两端点各 50，但离线段本身 0 → 曲线上型
    d, p = ci.nearest(50, 0)
    assert d < 1e-9
    assert p is not None and p.kind == "segment"

    # 圆上非象限点 (50,40)：圆心(50,50) r10 → |dist-r|=0
    d, p = ci.nearest(50, 40)
    assert d < 1e-9
    assert p is not None and p.kind == "circle"


def test_curve_index_empty():
    """空索引返回 (inf, None)，不崩。"""
    doc = ezdxf.new("R2018")
    ci = CurveIndex(list(doc.modelspace()))
    d, p = ci.nearest(0, 0)
    assert d == float("inf") and p is None
