# -*- coding: utf-8 -*-
"""M5 另存 DXF 单测（T5.1）。

覆盖：GBK 中文无损回环（含 `$DWGCODEPAGE` 表头同步）、图层/颜色/块定义完整
保留、父目录自动创建、非 GBK 文档不被越界改码。
"""
from __future__ import annotations

import ezdxf

from app.io.dxf_export import save_document


def _gbk_doc_with_text():
    """构造含中文 TEXT 的文档，模拟 loader 读真实 GBK 文件后的状态。

    只设 `doc.encoding='gbk'`、`$DWGCODEPAGE` 故意留默认（ANSI_1252）——
    这正是 ezdxf 1.4.4 的怪癖触发点，save_document 须同步表头才对。
    """
    doc = ezdxf.new("R2018")
    msp = doc.modelspace()
    msp.add_text("未挂靠尺寸", dxfattribs={"height": 2.5}).set_placement((0, 0))
    doc.encoding = "gbk"
    doc.header["$DWGCODEPAGE"] = "ANSI_1252"  # 模拟 saveas(encoding=...) 留下的错误表头
    return doc


def test_save_document_gbk_roundtrip(tmp_path):
    """GBK 中文无损：save_document 同步表头后，回读中文不乱码。"""
    doc = _gbk_doc_with_text()
    out = tmp_path / "out.dxf"

    ret = save_document(doc, out)

    assert ret == str(out)
    assert out.exists()

    doc2 = ezdxf.readfile(str(out))
    # 关键：表头已同步为 ANSI_936（非错误默认 ANSI_1252）
    assert doc2.header["$DWGCODEPAGE"] == "ANSI_936"
    texts = [e for e in doc2.modelspace() if e.dxftype() == "TEXT"]
    assert len(texts) == 1
    assert texts[0].dxf.text == "未挂靠尺寸"


def test_save_document_preserves_blocks_layers_colors(tmp_path):
    """图层 / 命名块 / 颜色 / 线型完整保留，无丢失。"""
    doc = ezdxf.new("R2018")
    msp = doc.modelspace()
    layer = doc.layers.add("MyLayer", color=1, linetype="DASHED")
    blk = doc.blocks.new("MyBlock")
    blk.add_line((0, 0), (10, 0), dxfattribs={"layer": "MyLayer", "color": 3})
    msp.add_blockref("MyBlock", (0, 0))

    out = tmp_path / "out.dxf"
    save_document(doc, out)

    doc2 = ezdxf.readfile(str(out))
    assert "MyLayer" in doc2.layers
    assert doc2.layers.get("MyLayer").dxf.color == 1
    assert doc2.layers.get("MyLayer").dxf.linetype == "DASHED"
    assert "MyBlock" in doc2.blocks
    assert len([e for e in doc2.modelspace() if e.dxftype() == "INSERT"]) == 1


def test_save_document_creates_parent_dir(tmp_path):
    """输出父目录不存在时自动创建。"""
    doc = ezdxf.new("R2018")
    doc.modelspace().add_line((0, 0), (1, 0))
    out = tmp_path / "deep" / "nested" / "out.dxf"
    save_document(doc, out)
    assert out.exists()


def test_save_document_non_gbk_untouched(tmp_path):
    """非 GBK 编码文档：不越界改码，表头保持原样。"""
    doc = ezdxf.new("R2018")
    doc.modelspace().add_line((0, 0), (1, 0))
    # 默认 ASCII/UTF 文档 encoding 非 GBK 族，_sync_gbk_header 应跳过
    out = tmp_path / "out.dxf"
    save_document(doc, out)
    doc2 = ezdxf.readfile(str(out))
    # 无中文，头不强制成 ANSI_936（若非 None/非 ANSI_936 即证明未越界干预）
    assert doc2.header["$DWGCODEPAGE"] != "ANSI_936"
