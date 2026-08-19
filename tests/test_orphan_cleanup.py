# -*- coding: utf-8 -*-
"""孤儿 *D 块清理单测（T6.1 配套的「清理孤儿 *D 块」复选框后端）。

覆盖：`clean_orphan_blocks` 删除无引用孤儿 *D、保留被 INSERT / DIMENSION /
嵌套 INSERT 引用的 *D 与命名块；`run_pipeline(clean_orphan=…)` 集成行为。
"""
from __future__ import annotations

import ezdxf

from app.core.blockify import clean_orphan_blocks
from app.core.pipeline import run_pipeline


def test_clean_orphan_removes_only_unreferenced():
    doc = ezdxf.new("R2018")
    msp = doc.modelspace()

    # 命名块：绝不删
    doc.blocks.new("MyBlock").add_line((0, 0), (1, 0))
    # 被 INSERT 引用：保留
    doc.blocks.new("*D100").add_line((0, 0), (2, 0))
    msp.add_blockref("*D100", (0, 0))
    # 被 DIMENSION 组码 2 引用：保留（真实渲染产生 *D 几何块）
    dim = msp.add_linear_dim(base=(5, 5), p1=(0, 0), p2=(10, 0))
    dim.render()
    geo_name = dim.dimension.dxf.geometry
    # 孤儿：删除
    doc.blocks.new("*D200").add_line((0, 0), (3, 0))

    deleted = clean_orphan_blocks(doc)

    assert "*D200" in deleted
    assert "*D100" not in deleted
    assert geo_name not in deleted
    assert "*D200" not in doc.blocks
    assert "MyBlock" in doc.blocks
    assert "*D100" in doc.blocks
    assert geo_name in doc.blocks


def test_clean_orphan_keeps_nested_reference():
    """块套块：被外层块内 INSERT 引用的 *D 块也视为被引用，不删。"""
    doc = ezdxf.new("R2018")
    doc.blocks.new("*D300").add_line((0, 0), (4, 0))
    doc.blocks.new("Outer").add_blockref("*D300", (0, 0))

    deleted = clean_orphan_blocks(doc)

    assert "*D300" not in deleted
    assert "*D300" in doc.blocks


def _build_with_orphan(tmp_path) -> str:
    """构造含「一条线段 + 一个未挂靠线性标注 + 一个孤儿 *D 块」的 DXF。"""
    doc = ezdxf.new("R2018")
    msp = doc.modelspace()
    msp.add_line((0, 0), (10, 0))
    d = msp.add_linear_dim(base=(5, 3), p1=(2, 4), p2=(10, 0))  # origin1 离线段 4mm → 未挂靠
    d.render()
    dim = d.dimension
    dim.dxf.defpoint3 = (2, 4, 0)
    dim.dxf.defpoint2 = (10, 0, 0)
    doc.blocks.new("*D900").add_line((0, 0), (5, 5))
    p = tmp_path / "in.dxf"
    doc.saveas(str(p))
    return str(p)


def test_run_pipeline_clean_orphan_true(tmp_path):
    p = _build_with_orphan(tmp_path)
    out = run_pipeline(p, clean_orphan=True)

    assert "*D900" not in out.doc.blocks
    assert any("已清理孤儿 *D 块" in w for w in out.result.warnings)


def test_run_pipeline_clean_orphan_default_false(tmp_path):
    """默认不清理：孤儿 *D 块保留（严格满足「保留块定义」，§4.6）。"""
    p = _build_with_orphan(tmp_path)
    out = run_pipeline(p)

    assert "*D900" in out.doc.blocks
    assert not any("已清理孤儿" in w for w in out.result.warnings)
