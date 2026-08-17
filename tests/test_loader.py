# -*- coding: utf-8 -*-
"""M1 文件解析单测。

覆盖 T1.1（GBK 解码回读）+ T1.2（实体分类 / 过滤查询 / 数据无丢失）。
大文件（9.85MB / 961 尺寸）的全量对账见 `_verify_m1.py`（一次性验收脚本），
此处用合成小图锁定分类逻辑，避免测试依赖外部大文件。
"""
from __future__ import annotations

import ezdxf

from app.core.loader import (
    GEOMETRY_DXF_TYPES,
    load_dxf,
)


def _make_doc() -> ezdxf.document.Drawing:
    """构造一张包含各类实体的小图，供分类测试。"""
    doc = ezdxf.new("R2018")
    msp = doc.modelspace()
    # ezdxf 不会因实体引用而自动建图层，需显式 add
    doc.layers.add("MY_LAYER")
    doc.layers.add("PH_DIM")

    # 几何图元：LINE/ARC/CIRCLE/SPLINE/LWPOLYLINE/ELLIPSE/POINT（7 个）
    msp.add_line((0, 0), (10, 0))
    msp.add_arc((0, 0), radius=5, start_angle=0, end_angle=90)
    msp.add_circle((0, 0), radius=3)
    msp.add_spline([(0, 0), (5, 5), (10, 0)])
    msp.add_lwpolyline([(0, 0), (1, 1), (2, 0)], format="xy")
    msp.add_ellipse((0, 0), major_axis=(5, 0), ratio=0.5)
    msp.add_point((0, 0))

    # 非几何：TEXT/MTEXT/INSERT（3 个），INSERT 依赖命名块
    msp.add_text("28", dxfattribs={"layer": "PH_DIM"})
    msp.add_mtext("±0.1")
    doc.blocks.new("B")
    msp.add_blockref("B", (0, 0))

    # 单独一个放在自定义图层的 LINE，供图层过滤测试
    msp.add_line((0, 0), (1, 1), dxfattribs={"layer": "MY_LAYER"})
    return doc


def test_classify_and_filter(tmp_path):
    """实体分类正确、过滤查询可用、数据无丢失。"""
    src = tmp_path / "t.dxf"
    _make_doc().saveas(src)

    ld = load_dxf(src)

    # 几何 = 8 个（7 白名单 + 1 自定义图层 LINE），非几何 = 3
    assert ld.geometry_count == 8
    assert ld.dimension_count == 0
    assert ld.other_count == 3
    # 数据无丢失：全部实体 = 几何 + 其他
    assert ld.entity_count == ld.geometry_count + ld.other_count == 11

    # 按类型过滤
    assert sum(1 for _ in ld.iter_entities("LINE")) == 2
    # 按图层过滤
    assert sum(1 for _ in ld.iter_entities("LINE", layer="MY_LAYER")) == 1
    # 几何白名单不含 TEXT/INSERT
    assert "TEXT" not in GEOMETRY_DXF_TYPES
    assert "INSERT" not in GEOMETRY_DXF_TYPES
    # 图层表包含自定义层
    assert "MY_LAYER" in ld.layers


def test_gbk_roundtrip(tmp_path):
    """GBK（ANSI_936）文件写入后回读无损（T1.1 解码验收）。

    ezdxf 需 `doc.encoding='gbk'` + 表头 `$DWGCODEPAGE=ANSI_936` 配合才会
    真正写出 GBK 字节；单用 `saveas(encoding=...)` 不重写表头（1.4.4 怪癖）。
    """
    doc = ezdxf.new("R2018")
    doc.encoding = "gbk"
    doc.header["$DWGCODEPAGE"] = "ANSI_936"
    doc.modelspace().add_text("未挂靠尺寸标注", dxfattribs={"layer": "Dim"})

    src = tmp_path / "gbk.dxf"
    doc.saveas(src)

    ld = load_dxf(src)
    texts = [e.dxf.text for e in ld.iter_entities("TEXT")]
    assert texts == ["未挂靠尺寸标注"]
    assert ld.doc.encoding == "gbk"
    assert ld.doc.header.get("$DWGCODEPAGE") == "ANSI_936"
    assert not ld.warnings  # 主读取直接成功，无回退/告警
