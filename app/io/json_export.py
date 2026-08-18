# -*- coding: utf-8 -*-
"""M3.4 JSON 结构化输出。

T3.4 —— 将 `Result` 序列化为需求分析 §7 / ARCHITECTURE.md §5.1 的 JSON
结构，供下游脚本解析比对验收。

字段映射（严格对齐 §5.1 schema，注释里标注与草稿 §7 的差异）：
    - 顶层：file / output_dxf / unit / dxf_version / detach_tolerance /
      snap_radius / processed_at / total_dimensions / unattached_count /
      summary / dimensions / warnings。
    - `dimensions` = **仅未挂靠**标注（完整字段）；`summary` = **全部**尺寸
      （handle/type/value/unattached），供自动化比对验收（§5.1 附注）。
    - `tolerance` 恒为对象（mode 枚举含 `none`，无损），仅 Tolerance 为 None
      时为 null —— 与草稿 §7 的 `"tolerance": null` 不同，这里按 §5.1 细化版
      保留 mode 字段，下游可直接读 `dim["tolerance"]["mode"]`。
    - `measurement_points` 以 role 为键（feature/center/origin1/…），值为
      group_code/x/y/detached/corrected/corrected_x/corrected_y/unresolved/
      distance/nearest_entity/confidence —— 含 M3.3 吸附结果。

序列化约定：
    - 数值用原生 float 序列化（Python3 repr 最短往返表示，28.0→28.0）。
    - `ensure_ascii=False` 保证中文图层/块名/文字原样输出（GBK 无损）。
    - 计数在 `dimensions` 非空时由其派生（dimensions 是全部尺寸的权威来源），
      空时回退显式字段，避免未接线时输出 0 的假值。
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Optional, Union

from app.models import (
    BBox,
    BlockInfo,
    DimensionInfo,
    MeasurementPoint,
    Result,
    SummaryEntry,
    Tolerance,
)


def _now_iso() -> str:
    """当前时间 ISO 字符串（秒精度），供 processed_at 兜底。"""
    return datetime.now().isoformat(timespec="seconds")


def _point_to_dict(mp: MeasurementPoint) -> dict:
    """MeasurementPoint → JSON 对象（§5.1 measurement_points 的单个值）。"""
    return {
        "group_code": mp.group_code,
        "x": mp.x,
        "y": mp.y,
        "detached": mp.detached,
        "corrected": mp.corrected,
        "corrected_x": mp.corrected_x,
        "corrected_y": mp.corrected_y,
        "unresolved": mp.unresolved,
        "distance": mp.distance,
        "nearest_entity": mp.nearest_entity,
        "confidence": mp.confidence,
    }


def _tolerance_to_dict(tol: Optional[Tolerance]):
    """Tolerance → JSON 对象；None → null（§5.1：mode 含 none 恒为对象）。"""
    if tol is None:
        return None
    return {
        "raw": tol.raw,
        "mode": tol.mode,
        "nominal": tol.nominal,
        "upper": tol.upper,
        "lower": tol.lower,
    }


def _bbox_to_dict(bbox: Optional[BBox]):
    """BBox → JSON 对象；None → null。"""
    if bbox is None:
        return None
    return {
        "minx": bbox.minx,
        "miny": bbox.miny,
        "maxx": bbox.maxx,
        "maxy": bbox.maxy,
    }


def _block_to_dict(block: Optional[BlockInfo]):
    """BlockInfo → JSON 对象；None → null（M4 尚未标准化时为空）。"""
    if block is None:
        return None
    return {
        "name": block.name,
        "created": block.created,
        "layer": block.layer,
        "converted_from": block.converted_from,
    }


def _dimension_to_dict(info: DimensionInfo) -> dict:
    """DimensionInfo → JSON 对象（dimensions 数组元素，完整字段）。"""
    return {
        "handle": info.handle,
        "type": info.type,
        "dxf_type_code": info.dxf_type_code,
        "dimstyle": info.dimstyle,
        "layer": info.layer,
        "value": info.value,
        "text": info.text,
        "tolerance": _tolerance_to_dict(info.tolerance),
        "bbox": _bbox_to_dict(info.bbox),
        "unattached": info.unattached,
        "detach_distance": info.detach_distance,
        "measurement_points": {
            role: _point_to_dict(mp) for role, mp in info.points.items()
        },
        "block": _block_to_dict(info.block),
    }


def _summary_to_dict(entry: SummaryEntry) -> dict:
    """SummaryEntry → JSON 对象（summary 数组元素）。"""
    return {
        "handle": entry.handle,
        "type": entry.type,
        "value": entry.value,
        "unattached": entry.unattached,
    }


def _build_summary(result: Result) -> list[dict]:
    """summary 数组：优先 result.summary，缺省由完整 dimensions 派生。"""
    if result.summary:
        return [_summary_to_dict(s) for s in result.summary]
    return [
        {
            "handle": d.handle,
            "type": d.type,
            "value": d.value,
            "unattached": d.unattached,
        }
        for d in result.dimensions
    ]


def result_to_dict(result: Result) -> dict:
    """Result → 顶层 JSON 对象（严格对齐 §5.1 schema）。"""
    full = result.dimensions  # 全部尺寸（detector 输出），权威来源

    # 计数：dimensions 非空时由之派生，空时回退显式字段（避免未接线输出 0）。
    if full:
        total = len(full)
        unattached = sum(1 for d in full if d.unattached)
    else:
        total = result.total_dimensions
        unattached = result.unattached_count

    return {
        "file": result.file,
        "output_dxf": result.output_dxf,
        "unit": result.unit,
        "dxf_version": result.dxf_version,
        "detach_tolerance": result.detach_tolerance,
        "snap_radius": result.snap_radius,
        "processed_at": result.processed_at or _now_iso(),
        "total_dimensions": total,
        "unattached_count": unattached,
        "summary": _build_summary(result),
        "dimensions": [_dimension_to_dict(d) for d in full if d.unattached],
        "warnings": list(result.warnings),
    }


def dumps(result: Result, indent: int = 2) -> str:
    """Result → JSON 字符串（ensure_ascii=False 保证中文原样输出）。"""
    return json.dumps(result_to_dict(result), ensure_ascii=False, indent=indent)


def dump(result: Result, path: Union[str, Path], indent: int = 2) -> None:
    """Result → 写入 JSON 文件（UTF-8，无 BOM）。"""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(dumps(result, indent=indent), encoding="utf-8")


__all__ = [
    "result_to_dict",
    "dumps",
    "dump",
]
