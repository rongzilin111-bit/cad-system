# -*- coding: utf-8 -*-
"""JSON 结构化输出单测（T3.4）。

覆盖 §5.1 schema 的关键约定：dimensions 仅含未挂靠、summary 含全部、
tolerance 恒为对象（None 才 null）、measurement_points 以 role 为键、
中文 ensure_ascii=False 无损、计数由 dimensions 派生，以及一条
「detect→reconstruct→序列化→json.loads」的端到端回环。
"""
from __future__ import annotations

import json

import pytest

import ezdxf

from app.core.detector import detect_unattached
from app.core.geometry_index import GeometryIndex
from app.core.curve_index import CurveIndex
from app.core.loader import load_dxf
from app.core.reconstruct import reconstruct
from app.io.json_export import dump, dumps, result_to_dict
from app.models import (
    BBox,
    BlockInfo,
    DimensionInfo,
    MeasurementPoint,
    Result,
    SummaryEntry,
    Tolerance,
)


def _linear(doc, base, p1, p2):
    """线性标注：origin1(13)=p1、origin2(11)=p2（同 test_detector 契约）。"""
    d = doc.modelspace().add_linear_dim(base=base, p1=p1, p2=p2)
    d.render()
    dim = d.dimension
    dim.dxf.defpoint3 = (*p1, 0)
    dim.dxf.defpoint2 = (*p2, 0)
    return dim


def _info(handle="A1", unattached=True, value=28.0, text="28", points=None, **kw) -> DimensionInfo:
    """构造单个 DimensionInfo，默认未挂靠 + 一个角点定义点。"""
    if points is None:
        points = {"feature": MeasurementPoint(role="feature", group_code=11, x=0.0, y=0.0)}
    return DimensionInfo(
        handle=handle,
        type="ordinate",
        dxf_type_code=6,
        value=value,
        text=text,
        unattached=unattached,
        points=points,
        **kw,
    )


def test_result_to_dict_metadata_and_counts():
    """顶层字段齐全，计数由 dimensions 派生。"""
    result = Result(
        file="测试文件.dxf",
        output_dxf="测试文件_reconstructed.dxf",
        unit="mm",
        dxf_version="AC1032",
        detach_tolerance=0.01,
        snap_radius=50.0,
        dimensions=[_info("A1", unattached=True), _info("A2", unattached=False)],
    )
    data = result_to_dict(result)
    assert data["file"] == "测试文件.dxf"
    assert data["unit"] == "mm"
    assert data["total_dimensions"] == 2
    assert data["unattached_count"] == 1
    assert data["processed_at"]  # 兜底填充非空
    assert data["warnings"] == []


def test_dimensions_only_unattached_summary_all():
    """dimensions 仅含未挂靠，summary 含全部（§5.1 附注）。"""
    result = Result(
        dimensions=[_info("A1", unattached=True), _info("A2", unattached=False)]
    )
    data = result_to_dict(result)
    assert [d["handle"] for d in data["dimensions"]] == ["A1"]
    assert [s["handle"] for s in data["summary"]] == ["A1", "A2"]
    assert data["summary"][0] == {"handle": "A1", "type": "ordinate",
                                  "value": 28.0, "unattached": True}


def test_point_and_tolerance_serialization():
    """measurement_points 以 role 为键；tolerance 恒为对象（含 mode=none）。"""
    tol = Tolerance(raw="28%%P0.1", mode="symmetrical", nominal=28.0, upper=0.1, lower=0.1)
    info = _info(
        tolerance=tol,
        bbox=BBox(0.0, 0.0, 10.0, 3.0),
        points={
            "feature": MeasurementPoint(
                role="feature", group_code=11, x=0.0, y=0.0,
                detached=True, corrected=True, corrected_x=0.05, corrected_y=0.0,
                distance=3.25, nearest_entity="LINE:ABC1", confidence=1.0,
            )
        },
    )
    d = _dimension_dict(info)
    assert d["tolerance"]["mode"] == "symmetrical"
    assert d["tolerance"]["upper"] == pytest.approx(0.1)
    assert d["bbox"] == {"minx": 0.0, "miny": 0.0, "maxx": 10.0, "maxy": 3.0}
    pt = d["measurement_points"]["feature"]
    assert pt["group_code"] == 11
    assert pt["corrected"] is True
    assert pt["corrected_x"] == pytest.approx(0.05)
    assert pt["nearest_entity"] == "LINE:ABC1"
    assert pt["unresolved"] is False


def test_none_fields_serialize_to_null():
    """tolerance/bbox/block 为 None → null；value 为 None → null。"""
    info = _info(value=None, tolerance=None, bbox=None, block=None)
    d = _dimension_dict(info)
    assert d["value"] is None
    assert d["tolerance"] is None
    assert d["bbox"] is None
    assert d["block"] is None


def _dimension_dict(info: DimensionInfo) -> dict:
    return result_to_dict(Result(dimensions=[info]))["dimensions"][0]


def test_dump_utf8_no_ascii_escape():
    """dump 写文件：中文原样（非 \\u 转义），json.loads 可回读。"""
    result = Result(file="测试文件.dxf", dimensions=[_info()])
    data = result_to_dict(result)
    s = dumps(result)
    assert "测试文件" in s          # ensure_ascii=False，中文未转义
    assert json.loads(s)["file"] == "测试文件.dxf"


def test_dump_writes_file(tmp_path):
    """dump 落盘，路径父目录自动创建，json.loads 回读字段一致。"""
    p = tmp_path / "out" / "result.json"
    result = Result(file="a.dxf", dimensions=[_info("A1"), _info("A2", unattached=False)])
    dump(result, p)
    loaded = json.loads(p.read_text(encoding="utf-8"))
    assert loaded["total_dimensions"] == 2
    assert loaded["unattached_count"] == 1
    assert len(loaded["dimensions"]) == 1


def test_end_to_end_roundtrip(tmp_path):
    """端到端：detect → reconstruct → Result → json.loads 回读吸附结果。"""
    doc = ezdxf.new("R2018")
    msp = doc.modelspace()
    msp.add_line((0, 0), (10, 0))
    d = _linear(doc, base=(5, 3), p1=(2, 4), p2=(10, 0))  # origin1 离线上 4mm

    p = tmp_path / "t.dxf"
    doc.saveas(p)
    loaded = load_dxf(p)
    index = GeometryIndex(loaded.geometry)
    curve_index = CurveIndex(loaded.geometry)
    results = detect_unattached(loaded, index=index, curve_index=curve_index)
    reconstruct(results, index, curve_index)

    result = Result(
        file=p.name, dxf_version="AC1032", dimensions=results
    )
    data = json.loads(dumps(result))
    dim = next(d for d in data["dimensions"] if d["type"] == "linear")
    o1 = dim["measurement_points"]["origin1"]
    assert o1["detached"] is True
    assert o1["corrected"] is True
    assert o1["corrected_y"] == pytest.approx(0.0)  # 吸附到 (0,0)
    assert dim["detach_distance"] == pytest.approx(4.0)
