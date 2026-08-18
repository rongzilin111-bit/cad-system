# -*- coding: utf-8 -*-
"""标注外接矩单测（T3.1）。

覆盖「整个标注」轴对齐最小外接矩：首选几何块图元（方案 A），
缺块回退虚拟图元（方案 B）；无法计算时返回 None 且不抛异常。
"""
from __future__ import annotations

import pytest

import ezdxf

from app.core.bbox import compute_bbox


def test_bbox_rendered_linear():
    """已渲染线性标注：外接矩覆盖延伸线起点(10,0)→终点(38,0)，含尺寸线(高>3)。"""
    doc = ezdxf.new("R2018")
    dim = doc.modelspace().add_linear_dim(
        base=(10, 3), p1=(10, 0), p2=(38, 0)
    ).render().dimension

    b = compute_bbox(dim)
    assert b is not None
    assert b.minx == pytest.approx(10.0)
    assert b.maxx == pytest.approx(38.0)
    assert b.miny == pytest.approx(0.0)
    assert b.maxy > 3.0          # 尺寸线 y=3，文字/箭头往上扩展


def test_bbox_rendered_with_diameter_symbol():
    """带 %%C 直径前缀的覆盖文字不影响 bbox 计算。"""
    doc = ezdxf.new("R2018")
    dim = doc.modelspace().add_linear_dim(
        base=(0, 3), p1=(0, 0), p2=(20, 0)
    ).render().dimension
    dim.dxf.text = "%%C20"

    b = compute_bbox(dim)
    assert b is not None
    assert b.minx == pytest.approx(0.0)
    assert b.maxx == pytest.approx(20.0)


def test_bbox_missing_geometry_returns_none():
    """未渲染（无 *D 几何块）的标注：两种方案都取不到图元 → None，不抛异常。"""
    doc = ezdxf.new("R2018")
    dim = doc.modelspace().add_linear_dim(
        base=(0, 3), p1=(0, 0), p2=(28, 0)
    ).dimension  # 未 render，无匿名块

    assert compute_bbox(dim) is None
