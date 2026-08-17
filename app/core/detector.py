# -*- coding: utf-8 -*-
"""M2 未挂靠判定（核心）。

T2.4：遍历全部 DIMENSION/ARC_DIMENSION，按类型提取定义点，对每个定义点
查最近几何特征点距离，**任一距离 > DETACH_TOLERANCE(0.01mm) → 判定「未挂靠」**。
阈值可配置（GUI 覆盖）。判定式与空间索引见 ARCHITECTURE.md §3.2。

输出：每个尺寸一个 `DimensionInfo`，填充 handle/type/dxf_type_code/dimstyle/layer
/points（含 detached/distance/nearest_entity）/detach_distance/unattached；
value/text/bbox/block 等字段留待 M3/M4 补全。
"""
from __future__ import annotations

from typing import Optional

from app.config import DETACH_TOLERANCE
from app.core.curve_index import CurveIndex
from app.core.defpoints import dim_type_code, dim_type_name, extract_defpoints
from app.core.geometry_index import GeometryIndex
from app.core.loader import LoadedDrawing
from app.models import DimensionInfo, MeasurementPoint


def _detect_one(
    dim,
    index: GeometryIndex,
    curve_index: CurveIndex,
    tolerance: float,
) -> DimensionInfo:
    """判定单个尺寸：提取定义点 → 查最近几何（特征点 ∪ 曲线取 min）→ 任一超阈值即未挂靠。

    吸附距离 = min(最近特征点距离, 最近曲线距离)，对应三种吸附口径
    （角点型 / 圆心型 → 特征点 KDTree；曲线上型 → 曲线网格，ARCHITECTURE.md §3.3）。
    """
    info = DimensionInfo(
        handle=dim.dxf.handle,
        type=dim_type_name(dim),
        dxf_type_code=dim_type_code(dim),
        dimstyle=dim.dxf.dimstyle,
        layer=dim.dxf.layer,
    )

    points: dict[str, MeasurementPoint] = {}
    max_dist = 0.0
    unattached = False
    for mp in extract_defpoints(dim):
        dist_v, fp = index.nearest(mp.x, mp.y)
        dist_c, _ = curve_index.nearest(mp.x, mp.y)
        dist = min(dist_v, dist_c)
        mp.distance = dist
        mp.detached = dist > tolerance
        if fp is not None:
            mp.nearest_entity = fp.entity_ref
        points[mp.role] = mp
        max_dist = max(max_dist, dist)
        unattached = unattached or mp.detached

    info.points = points
    info.detach_distance = max_dist
    info.unattached = unattached
    return info


def detect_unattached(
    loaded: LoadedDrawing,
    tolerance: float = DETACH_TOLERANCE,
    expand_insert: bool = False,
    index: Optional[GeometryIndex] = None,
    curve_index: Optional[CurveIndex] = None,
) -> list[DimensionInfo]:
    """对 loaded 中全部尺寸做未挂靠判定，返回按模型空间顺序的 DimensionInfo 列表。

    `index` / `curve_index` 可传入已建索引（pipeline 复用，避免重复建
    3.9 万特征点 KDTree + 4.2 万曲线网格）；缺省时内部构建一次。
    `expand_insert` 为「几何藏块内」扩展开关（§11，默认关）。
    """
    if index is None:
        index = GeometryIndex(loaded.geometry, expand_insert=expand_insert)
    if curve_index is None:
        curve_index = CurveIndex(loaded.geometry)

    results: list[DimensionInfo] = []
    for dim in loaded.dimensions:
        results.append(_detect_one(dim, index, curve_index, tolerance))
    return results


def count_unattached(results: list[DimensionInfo]) -> int:
    """统计未挂靠数量（供验收 / 日志 / 汇总）。"""
    return sum(1 for r in results if r.unattached)


__all__ = [
    "detect_unattached",
    "count_unattached",
]
