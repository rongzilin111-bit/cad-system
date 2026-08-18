# -*- coding: utf-8 -*-
"""编排层：单文件 → Result 的完整流水线（串联 M1→M4）。

把已独立实现并单测过的各模块按依赖顺序接成一条链，供 GUI worker / M5 导出 /
M7 验收一键调用，取代临时 smoke 脚本：

    load_dxf → GeometryIndex + CurveIndex → detect_unattached →
    (M3) compute_bbox + parse_dimension → reconstruct → blockify → Result

顺序要点：
    - detect 与 M3 的 bbox / 值 / 公差都依赖原始 DIMENSION 实体，故必须排在
      blockify（删原 DIMENSION）**之前**；reconstruct 只改 `DimensionInfo`，
      与 blockify 无依赖。
    - `results` 由 detector 按模型空间顺序生成，与 `loaded.dimensions` 严格
      同序，故 M3 补全用 `zip(results, loaded.dimensions)` 一一对应。
    - blockify 原地改 `doc`（转块 + 归层），转换结果写回 `info.block`。

输出 `PipelineOutput`：`result`（JSON/GUI 用）+ `doc`（已标准化的文档，
供 M5 dxf_export 另存）。文件 I/O（另存 DXF / 写 JSON / 日志）不在本层，
由 M5 模块或上层编排调用，见 ARCHITECTURE.md §1.2/§6.3。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Union

from ezdxf.document import Drawing

from app.config import (
    DETACH_TOLERANCE,
    OUTPUT_SUFFIX,
    SNAP_RADIUS,
    TARGET_LAYER,
)
from app.core.bbox import compute_bbox
from app.core.blockify import blockify
from app.core.curve_index import CurveIndex
from app.core.detector import detect_unattached
from app.core.dimension_text import parse_dimension
from app.core.geometry_index import GeometryIndex
from app.core.loader import LoadedDrawing, load_dxf
from app.core.reconstruct import reconstruct
from app.models import DimensionInfo, Result, SummaryEntry


@dataclass
class PipelineOutput:
    """一次流水线运行的结果封装：JSON 结果 + 已标准化的文档 + 加载封装。"""

    result: Result
    doc: Drawing                          # 已标准化（转块/归层）文档，供 M5 另存
    loaded: LoadedDrawing                 # 原始加载封装（分类列表 + warnings + summarize）


def output_dxf_path(path: Union[str, Path]) -> str:
    """由输入路径派生另存 DXF 完整路径：`{原名}_reconstructed.dxf`（§6.3）。"""
    p = Path(path)
    return str(p.with_name(p.stem + OUTPUT_SUFFIX + p.suffix))


def run_pipeline(
    path: Union[str, Path],
    *,
    tolerance: float = DETACH_TOLERANCE,
    snap_radius: float = SNAP_RADIUS,
    expand_insert: bool = False,
    layer: str = TARGET_LAYER,
    do_blockify: bool = True,
) -> PipelineOutput:
    """加载 → 索引 → 判定 → 提取 → 重构 → 标准化，产出 `PipelineOutput`。

    参数皆可被 GUI 覆盖；`do_blockify=False` 时跳过图元标准化（只检测不改图）。
    加载失败抛 `LoadError` / `FileNotFoundError`，由上层友好提示。
    """
    loaded = load_dxf(path)
    doc = loaded.doc

    # —— M2：空间索引（建一次，判定 + 重构复用） ——
    index = GeometryIndex(loaded.geometry, expand_insert=expand_insert)
    curve_index = CurveIndex(loaded.geometry)

    results: list[DimensionInfo] = detect_unattached(
        loaded,
        tolerance=tolerance,
        expand_insert=expand_insert,
        index=index,
        curve_index=curve_index,
    )

    # —— M3：外接矩 + 尺寸值/文字/公差（与 results 同序一一对应） ——
    for info, dim in zip(results, loaded.dimensions):
        info.bbox = compute_bbox(dim)
        value, text, tol = parse_dimension(dim, doc=doc)
        info.value = value
        info.text = text
        info.tolerance = tol

    # —— M3.3：测量点位重构（原地改 info.points） ——
    reconstruct(results, index, curve_index, snap_radius=snap_radius)

    # —— M4：图元标准化（转块 + 归层，原地改 doc，结果写回 info.block） ——
    warnings = list(loaded.warnings)
    if do_blockify:
        warnings.extend(blockify(doc, results, layer=layer))

    summary = [
        SummaryEntry(handle=r.handle, type=r.type, value=r.value, unattached=r.unattached)
        for r in results
    ]

    result = Result(
        file=Path(path).name,
        output_dxf=output_dxf_path(path),
        unit="mm",
        dxf_version=doc.dxfversion,
        detach_tolerance=tolerance,
        snap_radius=snap_radius,
        total_dimensions=len(results),
        unattached_count=sum(1 for r in results if r.unattached),
        dimensions=results,
        summary=summary,
        warnings=warnings,
    )
    return PipelineOutput(result=result, doc=doc, loaded=loaded)


__all__ = [
    "PipelineOutput",
    "output_dxf_path",
    "run_pipeline",
]
