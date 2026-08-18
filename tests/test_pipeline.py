# -*- coding: utf-8 -*-
"""流水线串联单测（M4 收口后的编排层）。

覆盖：load → index → detect → bbox/值/公差 → reconstruct → blockify → Result
一条端到端链路，以及「挂靠不转块」「do_blockify=False 只检测不改图」两条分支。
"""
from __future__ import annotations

import ezdxf

from app.config import BLOCK_NAME_PREFIX, TARGET_LAYER
from app.core.pipeline import output_dxf_path, run_pipeline


def _build_dxf(path, detached: bool) -> str:
    """构造含一条线段 + 一个线性标注的最小 DXF，落盘后返回路径。

    detached=True 时 origin1(13) 离线段 4mm → 判定未挂靠；
    detached=False 时两端点都落在线段上 → 挂靠。
    """
    doc = ezdxf.new("R2018")
    msp = doc.modelspace()
    msp.add_line((0, 0), (10, 0))
    p1 = (2, 4) if detached else (0, 0)
    d = msp.add_linear_dim(base=(5, 3), p1=p1, p2=(10, 0))
    d.render()
    dim = d.dimension
    dim.dxf.defpoint3 = (*p1, 0)
    dim.dxf.defpoint2 = (10, 0, 0)
    doc.saveas(path)
    return str(path)


def test_run_pipeline_end_to_end(tmp_path):
    """端到端：未挂靠尺寸走完判定→提取→重构→转块，Result 与 doc 齐备。"""
    p = _build_dxf(tmp_path / "in.dxf", detached=True)
    out = run_pipeline(p)

    # —— Result 计数与字段 ——
    assert out.result.total_dimensions == 1
    assert out.result.unattached_count == 1
    assert out.result.file == "in.dxf"
    assert out.result.output_dxf.endswith("_reconstructed.dxf")
    assert out.result.dxf_version == "AC1032"

    dim = out.result.dimensions[0]
    assert dim.unattached is True
    assert dim.value is not None
    assert dim.bbox is not None
    assert dim.tolerance is not None and dim.tolerance.mode == "none"

    # —— M4：已转块，块名带前缀，写入 info.block ——
    assert dim.block is not None
    assert dim.block.name.startswith(BLOCK_NAME_PREFIX)
    assert dim.block.converted_from == "DIMENSION"

    # —— doc 已标准化：原 DIMENSION 删、新增 INSERT、块定义可编辑 ——
    msp = out.doc.modelspace()
    assert not [e for e in msp if e.dxftype() == "DIMENSION"]
    inserts = [e for e in msp if e.dxftype() == "INSERT"]
    assert len(inserts) == 1
    assert inserts[0].dxf.layer == TARGET_LAYER

    # —— loaded 封装保留原始分类（dimension_count 仍为 1） ——
    assert out.loaded.dimension_count == 1


def test_run_pipeline_attached_dim_not_blockified(tmp_path):
    """挂靠尺寸：判定为挂靠、不转块（block=None），原 DIMENSION 保留。"""
    p = _build_dxf(tmp_path / "attached.dxf", detached=False)
    out = run_pipeline(p)

    assert out.result.total_dimensions == 1
    assert out.result.unattached_count == 0
    assert out.result.dimensions[0].unattached is False
    assert out.result.dimensions[0].block is None   # 挂靠不转块
    assert out.result.summary[0].unattached is False

    msp = out.doc.modelspace()
    assert len([e for e in msp if e.dxftype() == "DIMENSION"]) == 1
    assert not [e for e in msp if e.dxftype() == "INSERT"]


def test_run_pipeline_do_blockify_false(tmp_path):
    """do_blockify=False：只检测不改图，原 DIMENSION 保留、无 INSERT。"""
    p = _build_dxf(tmp_path / "in.dxf", detached=True)
    out = run_pipeline(p, do_blockify=False)

    assert out.result.unattached_count == 1
    assert out.result.dimensions[0].block is None   # 未标准化

    msp = out.doc.modelspace()
    assert len([e for e in msp if e.dxftype() == "DIMENSION"]) == 1
    assert not [e for e in msp if e.dxftype() == "INSERT"]


def test_output_dxf_path_suffix():
    """输出路径派生：原名 + _reconstructed 后缀，保留原扩展名。"""
    from pathlib import Path
    assert Path(output_dxf_path("d:/a/图纸.dxf")) == Path("d:/a/图纸_reconstructed.dxf")
    assert Path(output_dxf_path("d:/a/图纸.DXF")) == Path("d:/a/图纸_reconstructed.DXF")
