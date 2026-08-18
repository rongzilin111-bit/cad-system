# -*- coding: utf-8 -*-
"""块转换单测（T4.1/T4.2）。

覆盖方案 A「复用重命名 *D 块」的关键验收点：视觉位置不变（bbox 前后一致）、
块定义唯一且匿名标志已清（可编辑）、新块 INSERT + 块内图元归入
`Dim_Reconstruct_Layer`、挂靠尺寸不动、防撞后缀、缺几何块跳过、另存重开块仍在。
"""
from __future__ import annotations

import pytest

import ezdxf
from ezdxf import bbox as _bbox

from app.config import TARGET_LAYER
from app.core.blockify import blockify, convert_dimension_to_block, relayer_existing_blocks
from app.models import DimensionInfo


def _linear(doc, base, p1, p2):
    """已渲染线性标注，返回 DIMENSION 实体。"""
    return doc.modelspace().add_linear_dim(base=base, p1=p1, p2=p2).render().dimension


def _info(dim, unattached=True) -> DimensionInfo:
    """由实体句柄构造最小 DimensionInfo（blockify 只消费 handle/unattached）。"""
    return DimensionInfo(handle=dim.dxf.handle, type="linear", dxf_type_code=0,
                         unattached=unattached)


def _extents_box(entities):
    """图元列表 → (minx, miny, maxx, maxy)；用于视觉不变前后对比。"""
    ext = _bbox.extents(entities)
    return (ext.extmin.x, ext.extmin.y, ext.extmax.x, ext.extmax.y)


def test_convert_linear_dimension_to_block():
    """方案 A：DIMENSION → 命名块 INSERT，视觉位置不变、块定义唯一可编辑。"""
    doc = ezdxf.new("R2018")
    msp = doc.modelspace()
    dim = _linear(doc, base=(5, 3), p1=(2, 4), p2=(10, 0))
    handle = dim.dxf.handle
    before = _extents_box(list(dim.virtual_entities()))

    info = _info(dim)
    warnings = blockify(doc, [info])

    # 无告警，BlockInfo 字段齐全
    assert warnings == []
    assert info.block is not None
    assert info.block.name == f"Dim_Reconstruct_{handle}"
    assert info.block.created is True
    assert info.block.layer == TARGET_LAYER
    assert info.block.converted_from == "DIMENSION"

    # 原 DIMENSION 已删，新块存在且匿名标志已清（可编辑）
    assert dim.is_alive is False
    blk = doc.blocks.get(f"Dim_Reconstruct_{handle}")
    assert blk.block.dxf.flags == 0

    # 新 INSERT 引用该块
    inserts = [e for e in msp if e.dxftype() == "INSERT"]
    assert len(inserts) == 1
    ins = inserts[0]
    assert ins.dxf.name == f"Dim_Reconstruct_{handle}"

    # 视觉不变：INSERT 展开 bbox ≈ 转换前 bbox
    assert _extents_box([ins]) == pytest.approx(before)


def test_block_internal_entities_forced_to_layer():
    """T4.2 归层：新 INSERT 与块内图元（含箭头 INSERT）统一落目标层。"""
    doc = ezdxf.new("R2018")
    msp = doc.modelspace()
    dim = _linear(doc, base=(5, 3), p1=(2, 4), p2=(10, 0))
    handle = dim.dxf.handle
    info = _info(dim)
    blockify(doc, [info])

    blk = doc.blocks.get(f"Dim_Reconstruct_{handle}")
    assert len(list(blk)) > 0                    # 块内确有图元
    for e in blk:
        assert e.dxf.layer == TARGET_LAYER
    ins = next(e for e in msp if e.dxftype() == "INSERT")
    assert ins.dxf.layer == TARGET_LAYER


def test_only_unattached_converted():
    """只转换未挂靠尺寸；挂靠尺寸保持原 DIMENSION 不动。"""
    doc = ezdxf.new("R2018")
    msp = doc.modelspace()
    dim_a = _linear(doc, base=(5, 3), p1=(0, 0), p2=(10, 0))   # 挂靠
    dim_b = _linear(doc, base=(15, 3), p1=(12, 4), p2=(20, 0))  # 未挂靠

    info_a = _info(dim_a, unattached=False)
    info_b = _info(dim_b, unattached=True)
    blockify(doc, [info_a, info_b])

    assert dim_a.is_alive is True and info_a.block is None       # 挂靠不动
    assert dim_b.is_alive is False and info_b.block is not None  # 未挂靠转块
    assert len([e for e in msp if e.dxftype() == "INSERT"]) == 1


def test_name_collision_suffix():
    """预置同名块 → 防撞追加 _1 后缀（§4.4）。"""
    doc = ezdxf.new("R2018")
    msp = doc.modelspace()
    dim = _linear(doc, base=(5, 3), p1=(2, 4), p2=(10, 0))
    handle = dim.dxf.handle
    doc.blocks.new(f"Dim_Reconstruct_{handle}")  # 制造碰撞

    info = _info(dim)
    blockify(doc, [info])
    assert info.block.name == f"Dim_Reconstruct_{handle}_1"
    assert f"Dim_Reconstruct_{handle}_1" in doc.blocks


def test_missing_geometry_block_skipped():
    """未渲染（无 *D 几何块）→ 记告警跳过，原 DIMENSION 不删。"""
    doc = ezdxf.new("R2018")
    msp = doc.modelspace()
    dim = doc.modelspace().add_linear_dim(base=(5, 3), p1=(2, 4), p2=(10, 0)).dimension
    info = _info(dim)

    warnings = blockify(doc, [info])
    assert len(warnings) == 1
    assert "缺几何块" in warnings[0]
    assert info.block is None
    assert dim.is_alive is True


def test_target_layer_created():
    """目标图层不存在时自动创建。"""
    doc = ezdxf.new("R2018")
    msp = doc.modelspace()
    dim = _linear(doc, base=(5, 3), p1=(2, 4), p2=(10, 0))
    assert TARGET_LAYER not in doc.layers

    blockify(doc, [_info(dim)])
    assert TARGET_LAYER in doc.layers


def test_roundtrip_save_reload(tmp_path):
    """另存重开：命名块与 INSERT 持久保留，匿名标志仍为 0（可编辑）。"""
    doc = ezdxf.new("R2018")
    msp = doc.modelspace()
    dim = _linear(doc, base=(5, 3), p1=(2, 4), p2=(10, 0))
    handle = dim.dxf.handle
    blockify(doc, [_info(dim)])

    p = tmp_path / "out.dxf"
    doc.saveas(p)

    doc2 = ezdxf.readfile(str(p))
    assert f"Dim_Reconstruct_{handle}" in doc2.blocks
    assert doc2.blocks.get(f"Dim_Reconstruct_{handle}").block.dxf.flags == 0
    inserts = [e for e in doc2.modelspace() if e.dxftype() == "INSERT"]
    assert len(inserts) == 1
    assert inserts[0].dxf.name == f"Dim_Reconstruct_{handle}"
    assert inserts[0].dxf.layer == TARGET_LAYER


def test_convert_single_returns_none_for_missing_block():
    """convert_dimension_to_block 对缺块直接返回 None（不抛异常）。"""
    doc = ezdxf.new("R2018")
    msp = doc.modelspace()
    dim = doc.modelspace().add_linear_dim(base=(5, 3), p1=(2, 4), p2=(10, 0)).dimension
    assert convert_dimension_to_block(dim, doc, msp) is None


def test_relayer_existing_blocks_idempotent():
    """T4.2 §4.5：引用 `Dim_Reconstruct_*` 前缀块的 INSERT 仅改层，非前缀块不动。"""
    doc = ezdxf.new("R2018")
    msp = doc.modelspace()

    # 上次已转块：INSERT 引 `Dim_Reconstruct_*` 块，但图层被手动改走
    blk = doc.blocks.new("Dim_Reconstruct_ABC")
    blk.add_line((0, 0), (10, 0))
    ins = msp.add_blockref("Dim_Reconstruct_ABC", (0, 0), dxfattribs={"layer": "SomeLayer"})

    # 无关 INSERT（图框）：不应被归层
    frame = doc.blocks.new("FRAME")
    frame.add_line((0, 0), (10, 0))
    frame_ins = msp.add_blockref("FRAME", (0, 0), dxfattribs={"layer": "FrameLayer"})

    n = relayer_existing_blocks(doc)

    assert n == 1                                  # 只归层了 1 个前缀块
    assert ins.dxf.layer == TARGET_LAYER           # 前缀块被归层
    assert frame_ins.dxf.layer == "FrameLayer"     # 图框块不动


def test_blockify_idempotent_rerun():
    """幂等重跑：转块后再跑一次，图层漂移的 INSERT 被归层，不重复转块。"""
    doc = ezdxf.new("R2018")
    msp = doc.modelspace()
    dim = _linear(doc, base=(5, 3), p1=(2, 4), p2=(10, 0))
    info = _info(dim)

    blockify(doc, [info])                          # 首次：转块
    ins = next(e for e in msp if e.dxftype() == "INSERT")
    assert ins.dxf.layer == TARGET_LAYER

    ins.dxf.layer = "OtherLayer"                   # 模拟图层漂移
    blockify(doc, [])                              # 重跑（results 空，仅归层）

    assert ins.dxf.layer == TARGET_LAYER           # 归层恢复
    assert len([e for e in msp if e.dxftype() == "INSERT"]) == 1  # 未重复转块
