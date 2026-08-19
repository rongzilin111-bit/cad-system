# -*- coding: utf-8 -*-
"""GUI 纯展示层单测（T6.1/T6.2，无 PySide6 依赖）。

覆盖：数值/公差/外接矩/脱钩距格式化、类型中文名、JSON 路径派生、结果表格行
构建（含 summary 回退）、详情面板渲染、WorkerConfig 默认值。
"""
from __future__ import annotations

from app.config import DETACH_TOLERANCE, SNAP_RADIUS
from app.gui.presentation import (
    WorkerConfig,
    build_summary_rows,
    format_bbox,
    format_distance,
    format_tolerance,
    format_value,
    output_json_path,
    render_detail,
    type_label,
)
from app.models import (
    BBox,
    BlockInfo,
    DimensionInfo,
    MeasurementPoint,
    Result,
    SummaryEntry,
    Tolerance,
)


def _dim(handle="5EA", type_name="ordinate", unattached=True, **kw) -> DimensionInfo:
    """构造单个 DimensionInfo，常用字段给默认值，其余用 kw 覆盖。"""
    info = DimensionInfo(handle=handle, type=type_name)
    info.value = 28.0
    info.tolerance = Tolerance(mode="none", nominal=28.0)
    info.bbox = BBox(0.0, 0.0, 100.0, 50.0)
    info.unattached = unattached
    info.detach_distance = 3.25
    for k, v in kw.items():
        setattr(info, k, v)
    return info


# —— 格式化 ——
def test_format_value():
    assert format_value(None) == "—"
    assert format_value(28.0) == "28"
    assert format_value(28.5) == "28.5"


def test_format_tolerance_modes():
    assert format_tolerance(None) == "—"
    assert format_tolerance(Tolerance(mode="none")) == "—"
    assert format_tolerance(Tolerance(mode="symmetrical", upper=0.1, lower=0.1)) == "±0.1"
    assert format_tolerance(Tolerance(mode="deviation", upper=0.1, lower=-0.2)) == "+0.1/-0.2"
    assert format_tolerance(Tolerance(mode="limits", lower=27.8, upper=28.1)) == "27.8~28.1"
    assert format_tolerance(Tolerance(mode="basic")) == "□"


def test_format_bbox():
    assert format_bbox(None) == "—"
    assert format_bbox(BBox(0.0, 0.0, 100.0, 50.0)) == "(0, 0)–(100, 50)"


def test_format_distance():
    assert format_distance(_dim(unattached=True, detach_distance=3.25)) == "3.2500"
    assert format_distance(_dim(unattached=False)) == "—"


def test_type_label():
    assert type_label("ordinate") == "坐标"
    assert type_label("linear") == "线性"
    assert type_label("angular_3p") == "三点角度"
    assert type_label("unknown_9") == "unknown_9"  # 未知码原样返回


def test_output_json_path():
    from pathlib import Path
    assert Path(output_json_path("d:/a/图纸.dxf")) == Path("d:/a/图纸_result.json")
    assert output_json_path("d:/a/图纸.DXF").endswith("_result.json")


# —— 表格行构建 ——
def test_build_summary_rows_from_dimensions():
    result = Result(dimensions=[_dim("A", "linear", False), _dim("B", "ordinate", True)])
    result.summary = [
        SummaryEntry("A", "linear", 28.0, False),
        SummaryEntry("B", "ordinate", 28.0, True),
    ]
    rows = build_summary_rows(result)
    assert len(rows) == 2
    # 挂靠行：脱钩距占位、无高亮、无块
    assert rows[0]["handle"] == "A"
    assert rows[0]["type"] == "线性"
    assert rows[0]["detach_distance"] == "—"
    assert rows[0]["unattached"] is False
    # 未挂靠行：脱钩距数值、高亮、块名来自 info.block
    assert rows[1]["handle"] == "B"
    assert rows[1]["detach_distance"] == "3.2500"
    assert rows[1]["unattached"] is True
    assert rows[1]["block"] == ""


def test_build_summary_rows_block_name():
    dim = _dim("B", "ordinate", True, block=BlockInfo("Dim_Reconstruct_B", True, "Dim_Reconstruct_Layer", "DIMENSION"))
    rows = build_summary_rows(Result(dimensions=[dim]))
    assert rows[0]["block"] == "Dim_Reconstruct_B"


def test_build_summary_rows_fallback_summary():
    # dimensions 为空时回退 summary（summary 只有 handle/type/value/unattached）
    result = Result(summary=[SummaryEntry("C", "radius", 5.0, True)])
    rows = build_summary_rows(result)
    assert len(rows) == 1
    assert rows[0]["handle"] == "C"
    assert rows[0]["type"] == "半径"
    assert rows[0]["value"] == "5"
    assert rows[0]["tolerance"] == "—"
    assert rows[0]["unattached"] is True


# —— 详情渲染 ——
def test_render_detail_contains_fields():
    mp = MeasurementPoint(
        role="feature", group_code=13, x=0.0, y=0.0,
        detached=True, corrected=True, corrected_x=0.05, corrected_y=0.0,
        distance=3.25, nearest_entity="LINE:ABC1", confidence=1.0,
    )
    dim = _dim("5EA", "ordinate", True, points={"feature": mp})
    text = render_detail(dim)
    assert "句柄: 5EA" in text
    assert "类型: 坐标" in text
    assert "未挂靠: 是" in text
    assert "feature: 组码13 (0, 0)" in text
    assert "纠偏(0.05, 0)" in text
    assert "距3.2500mm" in text
    assert "近LINE:ABC1" in text


def test_render_detail_no_points():
    dim = _dim("A", "linear", False, points={})
    text = render_detail(dim)
    assert "测量点位:" in text
    assert "（无）" in text
    assert "未挂靠: 否" in text


# —— WorkerConfig 默认值 ——
def test_worker_config_defaults():
    cfg = WorkerConfig(path="a.dxf")
    assert cfg.tolerance == DETACH_TOLERANCE
    assert cfg.snap_radius == SNAP_RADIUS
    assert cfg.expand_insert is False
    assert cfg.do_blockify is True
    assert cfg.clean_orphan is False
