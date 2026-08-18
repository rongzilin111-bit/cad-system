# -*- coding: utf-8 -*-
"""测量点位吸附重构单测（T3.3）。

覆盖三类吸附口径（角点型→特征点 / 曲线上型→曲线投影 / 圆心型→最近圆心）、
snap_radius 超限 unresolved、直径补 center、以及半径/直径一致性自检
（最近≠正确时标 low_confidence）。

用合成小图（线 / 圆 + 手工设定义点），避免依赖外部大文件。
"""
from __future__ import annotations

import math

import pytest

import ezdxf

from app.config import SNAP_RADIUS
from app.core.curve_index import CurveIndex
from app.core.detector import detect_unattached
from app.core.geometry_index import GeometryIndex
from app.core.loader import load_dxf
from app.core.reconstruct import LOW_CONFIDENCE, reconstruct


def _linear(doc, base, p1, p2):
    """线性标注：origin1(13)=p1、origin2(11)=p2（同 test_detector 契约）。"""
    d = doc.modelspace().add_linear_dim(base=base, p1=p1, p2=p2)
    d.render()
    dim = d.dimension
    dim.dxf.defpoint3 = (*p1, 0)
    dim.dxf.defpoint2 = (*p2, 0)
    return dim


def _radius(doc, center, arc_point):
    """半径标注：center(10)、arc_point(14)，dimtype=4。"""
    d = doc.modelspace().add_linear_dim(base=(0, 3), p1=center, p2=arc_point)
    d.render()
    dim = d.dimension
    dim.dxf.dimtype = 4
    dim.dxf.defpoint = (*center, 0)
    dim.dxf.defpoint4 = (*arc_point, 0)
    return dim


def _diameter(doc, e1, e2):
    """直径标注：endpoint1(10)、endpoint2(14)，dimtype=3。"""
    d = doc.modelspace().add_linear_dim(base=(0, 3), p1=e1, p2=e2)
    d.render()
    dim = d.dimension
    dim.dxf.dimtype = 3
    dim.dxf.defpoint = (*e1, 0)
    dim.dxf.defpoint4 = (*e2, 0)
    return dim


def _run(tmp_path, doc, snap_radius=SNAP_RADIUS):
    """完整走 load→detect→reconstruct，返回 handle → DimensionInfo。"""
    p = tmp_path / "t.dxf"
    doc.saveas(p)
    loaded = load_dxf(p)
    index = GeometryIndex(loaded.geometry)
    curve_index = CurveIndex(loaded.geometry)
    results = detect_unattached(loaded, index=index, curve_index=curve_index)
    reconstruct(results, index, curve_index, snap_radius=snap_radius)
    return {r.handle: r for r in results}


def test_corner_snap_to_feature_point(tmp_path):
    """角点型：脱钩延伸线原点吸附到最近特征点（线端点），挂靠点不动。"""
    doc = ezdxf.new("R2018")
    msp = doc.modelspace()
    msp.add_line((0, 0), (10, 0))
    d = _linear(doc, base=(5, 3), p1=(2, 4), p2=(10, 0))  # origin1 离线上 4mm

    info = _run(tmp_path, doc)[d.dxf.handle]
    o1 = info.points["origin1"]
    o2 = info.points["origin2"]
    assert o1.detached is True
    assert o1.corrected is True
    assert o1.corrected_x == pytest.approx(0.0)
    assert o1.corrected_y == pytest.approx(0.0)   # 吸附到 (0,0)
    assert o1.nearest_entity.startswith("LINE:")
    assert o2.detached is False and o2.corrected is False    # 挂靠点不动


def test_on_curve_snap_and_center_snap(tmp_path):
    """曲线上型 + 圆心型：半径标注 arc_point 投影到圆、center 吸附到圆心。"""
    doc = ezdxf.new("R2018")
    msp = doc.modelspace()
    msp.add_circle((0, 0), radius=5)
    d = _radius(doc, center=(2, 0), arc_point=(7, 3))

    info = _run(tmp_path, doc)[d.dxf.handle]
    center = info.points["center"]
    arc_point = info.points["arc_point"]
    # 圆心型：吸附到圆心 (0,0)
    assert center.corrected is True
    assert center.corrected_x == pytest.approx(0.0)
    assert center.corrected_y == pytest.approx(0.0)
    assert center.nearest_entity.startswith("CIRCLE:")
    # 曲线上型：投影到圆上（半径 5，方向 atan2(3,7)）
    assert arc_point.corrected is True
    ang = math.atan2(3, 7)
    assert arc_point.corrected_x == pytest.approx(5 * math.cos(ang))
    assert arc_point.corrected_y == pytest.approx(5 * math.sin(ang))
    # 一致性自检通过 → 高置信
    assert center.confidence == 1.0 and arc_point.confidence == 1.0


def test_diameter_adds_center_and_snaps(tmp_path):
    """直径：两端点吸附到圆对径点，补 center 为中点（≈圆心）。"""
    doc = ezdxf.new("R2018")
    msp = doc.modelspace()
    msp.add_circle((0, 0), radius=5)
    d = _diameter(doc, e1=(6, 0), e2=(-6, 0))

    info = _run(tmp_path, doc)[d.dxf.handle]
    e1 = info.points["endpoint1"]
    e2 = info.points["endpoint2"]
    center = info.points["center"]
    assert e1.corrected and e2.corrected
    assert e1.corrected_x == pytest.approx(5.0) and e1.corrected_y == pytest.approx(0.0)
    assert e2.corrected_x == pytest.approx(-5.0) and e2.corrected_y == pytest.approx(0.0)
    assert center is not None
    assert center.corrected_x == pytest.approx(0.0)
    assert center.corrected_y == pytest.approx(0.0)
    # 一致性自检通过 → 高置信
    assert e1.confidence == 1.0 and e2.confidence == 1.0 and center.confidence == 1.0


def test_snap_radius_exceeded_unresolved(tmp_path):
    """吸附目标超出 snap_radius → 保留原坐标，unresolved=true。"""
    doc = ezdxf.new("R2018")
    msp = doc.modelspace()
    msp.add_line((0, 0), (10, 0))
    # origin1 距最近特征点 (10,0) 约 90mm，远超默认 50mm
    d = _linear(doc, base=(100, 3), p1=(100, 0), p2=(110, 0))

    info = _run(tmp_path, doc)[d.dxf.handle]
    o1 = info.points["origin1"]
    assert o1.detached is True
    assert o1.corrected is False
    assert o1.unresolved is True
    assert o1.corrected_x is None


def test_radius_consistency_low_confidence_on_wrong_center(tmp_path):
    """最近≠正确：圆心吸附到更近的干扰圆 → 一致性自检标 low_confidence。"""
    doc = ezdxf.new("R2018")
    msp = doc.modelspace()
    msp.add_circle((0, 0), radius=5)      # arc_point 落在此圆上
    msp.add_circle((50, 0), radius=5)     # 干扰圆，圆心更靠近脱钩 center
    d = _radius(doc, center=(48, 0), arc_point=(5.5, 0))

    info = _run(tmp_path, doc)[d.dxf.handle]
    center = info.points["center"]
    arc_point = info.points["arc_point"]
    # center 吸附到干扰圆圆心 (50,0)，arc_point 投影到 (5,0)
    assert center.corrected_x == pytest.approx(50.0)
    assert arc_point.corrected_x == pytest.approx(5.0)
    # 重构半径 45 ≠ 真半径 5 → 低置信
    assert center.confidence == LOW_CONFIDENCE
    assert arc_point.confidence == LOW_CONFIDENCE
