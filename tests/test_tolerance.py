# -*- coding: utf-8 -*-
"""尺寸值与公差解析单测（T3.2）。

覆盖 `%%C/%%D/%%P/%%%` 转义、`\\S上^下` 栈式、DIMSTYLE 公差变量，
以及 `parse_dimension` 的名义值（组码 42 / 文字覆盖）主入口。
"""
from __future__ import annotations

import pytest

import ezdxf

from app.core.dimension_text import decode_text, parse_dimension, parse_tolerance


def _dim(doc, text="<>", style="Standard"):
    """新建已渲染的线性标注（保证组码 42 测量值可算），返回 DIMENSION 实体。"""
    dim = doc.modelspace().add_linear_dim(
        base=(0, 3), p1=(0, 0), p2=(28, 0)
    ).render().dimension
    dim.dxf.text = text
    dim.dxf.dimstyle = style
    return dim


# —— 文本解码 ——

def test_decode_text_escapes():
    assert decode_text("%%C28") == "⌀28"
    assert decode_text("28%%D") == "28°"
    assert decode_text("28%%P0.1") == "28±0.1"
    assert decode_text("100%%%") == "100%"
    assert decode_text("%%c28%%d") == "⌀28°"  # 小写同样解码


def test_decode_text_stack():
    assert decode_text("\\S+0.1^-0.2;") == "+0.1/-0.2"
    assert decode_text("\\S28.1^27.8;") == "28.1/27.8"


def test_decode_text_ctrl_and_empty():
    assert decode_text("\\A1;28") == "28"   # \A1; 控制标记被丢弃
    assert decode_text("") == ""


# —— 名义值 ——

def test_value_from_measurement():
    doc = ezdxf.new("R2018")
    d = _dim(doc, text="<>")
    value, text, tol = parse_dimension(d, doc)
    assert value == pytest.approx(28.0)
    assert text == "28"            # 占位符 <> → 格式化名义值
    assert tol.mode == "none"


def test_value_from_override_text():
    doc = ezdxf.new("R2018")
    d = _dim(doc, text="35.5")
    value, text, tol = parse_dimension(d, doc)
    assert value == pytest.approx(35.5)
    assert text == "35.5"


def test_value_override_diameter_prefix():
    doc = ezdxf.new("R2018")
    d = _dim(doc, text="%%C12")
    value, text, _ = parse_dimension(d, doc)
    assert value == pytest.approx(12.0)
    assert text == "⌀12"


def test_value_ordinate_x_type():
    """坐标标注（X 型）：get_measurement 返回向量，取 X 分量。"""
    doc = ezdxf.new("R2018")
    d = doc.modelspace().add_ordinate_dim(
        feature_location=(123, 50), offset=(123, 80), dtype=0, origin=(0, 0)
    ).render().dimension
    value, _, _ = parse_dimension(d, doc)
    assert value == pytest.approx(123.0)


def test_value_ordinate_y_type():
    """坐标标注（Y 型）：get_measurement 返回向量，取 Y 分量。"""
    doc = ezdxf.new("R2018")
    d = doc.modelspace().add_ordinate_dim(
        feature_location=(50, 456), offset=(80, 456), dtype=1, origin=(0, 0)
    ).render().dimension
    value, _, _ = parse_dimension(d, doc)
    assert value == pytest.approx(456.0)


# —— 公差：覆盖文本显式 ——

def test_tolerance_symmetrical_pp():
    doc = ezdxf.new("R2018")
    d = _dim(doc, text="28%%P0.1")
    value, _, tol = parse_dimension(d, doc)
    assert value == pytest.approx(28.0)
    assert tol.mode == "symmetrical"
    assert tol.upper == pytest.approx(0.1)
    assert tol.lower == pytest.approx(0.1)


def test_tolerance_deviation_stack():
    doc = ezdxf.new("R2018")
    d = _dim(doc, text="\\S+0.1^-0.2;")
    value, _, tol = parse_dimension(d, doc)
    assert value == pytest.approx(28.0)   # 栈式不含名义，回退组码 42
    assert tol.mode == "deviation"
    assert tol.upper == pytest.approx(0.1)
    assert tol.lower == pytest.approx(-0.2)


def test_tolerance_limits_stack():
    doc = ezdxf.new("R2018")
    d = _dim(doc, text="\\S28.1^27.8;")
    value, _, tol = parse_dimension(d, doc)
    assert value == pytest.approx(28.0)
    assert tol.mode == "limits"
    assert tol.upper == pytest.approx(28.1)
    assert tol.lower == pytest.approx(27.8)


# —— 公差：DIMSTYLE 变量 ——

def test_tolerance_style_symmetrical():
    doc = ezdxf.new("R2018")
    ds = doc.dimstyles.get("Standard")
    ds.dxf.dimtol = 1
    ds.dxf.dimtp = 0.1
    ds.dxf.dimtm = 0.1
    d = _dim(doc, text="<>")
    value, _, tol = parse_dimension(d, doc)
    assert value == pytest.approx(28.0)
    assert tol.mode == "symmetrical"
    assert tol.upper == pytest.approx(0.1)
    assert tol.lower == pytest.approx(0.1)


def test_tolerance_style_deviation():
    doc = ezdxf.new("R2018")
    ds = doc.dimstyles.get("Standard")
    ds.dxf.dimtol = 1
    ds.dxf.dimtp = 0.1
    ds.dxf.dimtm = 0.2
    d = _dim(doc, text="<>")
    _, _, tol = parse_dimension(d, doc)
    assert tol.mode == "deviation"
    assert tol.upper == pytest.approx(0.1)
    assert tol.lower == pytest.approx(-0.2)   # DIMTM 存正值，含义为下偏差量


def test_tolerance_style_limits():
    doc = ezdxf.new("R2018")
    ds = doc.dimstyles.get("Standard")
    ds.dxf.dimlim = 1
    ds.dxf.dimtp = 0.1
    ds.dxf.dimtm = 0.2
    d = _dim(doc, text="<>")
    _, _, tol = parse_dimension(d, doc)
    assert tol.mode == "limits"
    assert tol.upper == pytest.approx(28.1)
    assert tol.lower == pytest.approx(27.8)


def test_tolerance_none_by_default():
    doc = ezdxf.new("R2018")
    d = _dim(doc, text="<>")
    _, _, tol = parse_dimension(d, doc)
    assert tol.mode == "none"
    assert tol.upper is None and tol.lower is None


# —— 兜底：不抛异常 ——

def test_parse_tolerance_no_raise_on_garbage():
    doc = ezdxf.new("R2018")
    d = _dim(doc, text="NOT_A_NUMBER")
    value, text, tol = parse_dimension(d, doc)  # 不应抛异常
    assert tol.mode == "none"
    assert tol.raw == "NOT_A_NUMBER"
