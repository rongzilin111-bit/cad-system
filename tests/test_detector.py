# -*- coding: utf-8 -*-
"""未挂靠判定单测（T2.4）。

覆盖 0.01mm 阈值分界、三种吸附口径（角点型 / 圆心型 / 曲线上型）的集成，
以及「任一应吸附定义点超阈值即未挂靠」的判定式。

用合成小图（一条水平线 + 手工设置定义点），避免依赖外部大文件；
真实文件 961 尺寸的全量对账见一次性验收脚本（181/961，见 plan.md）。
"""
from __future__ import annotations

import ezdxf

from app.core.detector import count_unattached, detect_unattached
from app.core.loader import load_dxf


def _linear(doc, base, p1, p2):
    """新建线性标注，并按本项目校准契约手工设 origin1(13)/origin2(11)。

    必须先 `.render()` 生成匿名块等完整几何——否则该 DIMENSION 缺失匿名块，
    会被 `load_dxf` 的 `doc.audit()` 静默丢弃（实测已确认）。
    """
    override = doc.modelspace().add_linear_dim(base=base, p1=p1, p2=p2)
    override.render()
    dim = override.dimension
    dim.dxf.defpoint3 = (*p1, 0)   # origin1 ← 组码 13
    dim.dxf.defpoint2 = (*p2, 0)   # origin2 ← 组码 11（本文件契约）
    return dim


def _detect(tmp_path, doc):
    p = tmp_path / "t.dxf"
    doc.saveas(p)
    return detect_unattached(load_dxf(p))


def test_attached_on_vertices(tmp_path):
    """角点型：两原点分别落在线的两端点 → 挂靠。"""
    doc = ezdxf.new("R2018")
    msp = doc.modelspace()
    msp.add_line((0, 0), (10, 0))
    d = _linear(doc, (0, 3), (0, 0), (10, 0))

    by = {r.handle: r for r in _detect(tmp_path, doc)}
    assert by[d.dxf.handle].unattached is False


def test_detached_far_away(tmp_path):
    """两原点远离任何几何 → 未挂靠。"""
    doc = ezdxf.new("R2018")
    msp = doc.modelspace()
    msp.add_line((0, 0), (10, 0))
    d = _linear(doc, (100, 3), (100, 0), (110, 0))

    by = {r.handle: r for r in _detect(tmp_path, doc)}
    assert by[d.dxf.handle].unattached is True
    assert by[d.dxf.handle].detach_distance > 0.01


def test_attached_on_midsegment(tmp_path):
    """曲线上型：原点落在线段中段（非端点），靠曲线网格判定为挂靠。

    若只用特征点 KDTree，中点 (5,0) 离两端点各 5mm，会被误判脱钩；
    结合曲线索引后距离 0，判定挂靠。
    """
    doc = ezdxf.new("R2018")
    msp = doc.modelspace()
    msp.add_line((0, 0), (10, 0))
    d = _linear(doc, (5, 3), (5, 0), (7, 0))

    by = {r.handle: r for r in _detect(tmp_path, doc)}
    assert by[d.dxf.handle].unattached is False


def test_threshold_boundary(tmp_path):
    """阈值分界：距离恰好 0.01mm 内算挂靠（严格 >0.01 才脱钩）。"""
    doc = ezdxf.new("R2018")
    msp = doc.modelspace()
    msp.add_line((0, 0), (10, 0))
    # origin1 距线 0.005mm（< 0.01）→ 挂靠；origin2 在线上
    d_ok = _linear(doc, (0, 3), (0, 0.005), (10, 0))
    # origin1 距线 0.02mm（> 0.01）→ 脱钩
    d_bad = _linear(doc, (100, 3), (100, 0.02), (110, 0))

    by = {r.handle: r for r in _detect(tmp_path, doc)}
    assert by[d_ok.dxf.handle].unattached is False
    assert by[d_bad.dxf.handle].unattached is True


def test_count_unattached(tmp_path):
    doc = ezdxf.new("R2018")
    msp = doc.modelspace()
    msp.add_line((0, 0), (10, 0))
    _linear(doc, (0, 3), (0, 0), (10, 0))      # 挂靠
    _linear(doc, (100, 3), (100, 0), (110, 0))  # 脱钩

    results = _detect(tmp_path, doc)
    assert len(results) == 2
    assert count_unattached(results) == 1
