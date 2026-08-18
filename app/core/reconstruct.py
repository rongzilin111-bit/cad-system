# -*- coding: utf-8 -*-
"""M3.3 测量点位吸附重构。

T3.3 —— 对「未挂靠」定义点按类别吸附回最近几何，记录纠偏坐标
（corrected 标记），直径补 center、半径/直径做一致性自检（见 ARCHITECTURE.md §3.3）。

三类吸附口径（由 role 判定，role 语义见 defpoints.py，不按组码，规避组码与实测出入）：
    - 角点型（origin1/origin2/vertex/feature）→ 最近特征点（KDTree）
    - 曲线上型（endpoint1/endpoint2/arc_point）→ 点在曲线上的投影（网格）
    - 圆心型（center）→ 最近圆心/弧心（特征点中筛 circle/arc center）

吸附流程（对每个脱钩定义点）：
    1. 依类别查最近目标，得距离 d 与目标坐标 Q；
    2. d ≤ snap_radius → 吸附到 Q，记 corrected=true / corrected_x/y / nearest_entity；
    3. d > snap_radius → 保留原坐标，记 corrected=false / unresolved=true
       （避免吸附到全图无关几何）；
    4. 直径补 center（两对端点纠偏后中点），半径/直径做一致性自检，
       不符标 low_confidence（confidence=0.5）。

兜底：任何异常不抛，保证流水线不中断。
"""
from __future__ import annotations

import math
from typing import Optional

from app.config import SNAP_RADIUS
from app.core.curve_index import CurveIndex, CurvePrimitive
from app.core.geometry_index import GeometryIndex
from app.models import DimensionInfo, MeasurementPoint

# —— 低置信标记（一致性自检失败时写 confidence） ——
LOW_CONFIDENCE = 0.5

# —— 一致性自检半径容差（mm）：吸附是精确投影，正确吸附与真值差 ≪1mm，
#    错吸附（最近≠正确）会差毫米级以上，故 1mm 是安全的判别界 ——
_RADIUS_TOL = 1.0

# —— 定义点类别（按 role 判定） ——
_ON_CURVE_ROLES = frozenset({"endpoint1", "endpoint2", "arc_point"})
_CENTER_ROLES = frozenset({"center"})


def _effective(mp: MeasurementPoint) -> tuple[float, float]:
    """取定义点「有效坐标」：已纠偏用纠偏坐标，否则用原始坐标。"""
    if mp.corrected and mp.corrected_x is not None and mp.corrected_y is not None:
        return mp.corrected_x, mp.corrected_y
    return mp.x, mp.y


def _snap_corner(mp: MeasurementPoint, index: GeometryIndex, snap_radius: float) -> None:
    """角点型：吸附到最近特征点。"""
    dist, fp = index.nearest(mp.x, mp.y)
    if fp is None:
        mp.unresolved = True
        return
    if dist <= snap_radius:
        mp.corrected = True
        mp.corrected_x = float(fp.x)
        mp.corrected_y = float(fp.y)
        mp.nearest_entity = fp.entity_ref
    else:
        mp.unresolved = True


def _snap_on_curve(
    mp: MeasurementPoint, curve_index: CurveIndex, snap_radius: float
) -> Optional[CurvePrimitive]:
    """曲线上型：吸附到点在曲线上的投影；返回吸附到的曲线（供一致性自检）。"""
    dist, prim = curve_index.nearest(mp.x, mp.y)
    if prim is None:
        mp.unresolved = True
        return None
    if dist <= snap_radius:
        px, py = prim.closest_point(mp.x, mp.y)
        mp.corrected = True
        mp.corrected_x = float(px)
        mp.corrected_y = float(py)
        mp.nearest_entity = prim.entity_ref
        return prim
    mp.unresolved = True
    return None


def _snap_center(mp: MeasurementPoint, index: GeometryIndex, snap_radius: float) -> None:
    """圆心型：吸附到最近圆心/弧心（特征点中筛 circle/arc center）。"""
    dist, fp = index.nearest_center(mp.x, mp.y)
    if fp is None:
        mp.unresolved = True
        return
    if dist <= snap_radius:
        mp.corrected = True
        mp.corrected_x = float(fp.x)
        mp.corrected_y = float(fp.y)
        mp.nearest_entity = fp.entity_ref
    else:
        mp.unresolved = True


def _add_diameter_center(info: DimensionInfo) -> None:
    """直径：补 center（两对端点纠偏后中点），与 schema 的 endpoint1/endpoint2/center 对齐。

    group_code=0 表示该点为计算点（无组码）；x/y 存纠偏前中点，
    corrected_x/y 存纠偏后中点。
    """
    e1 = info.points.get("endpoint1")
    e2 = info.points.get("endpoint2")
    if e1 is None or e2 is None:
        return
    ox, oy = (e1.x + e2.x) / 2.0, (e1.y + e2.y) / 2.0
    (x1, y1), (x2, y2) = _effective(e1), _effective(e2)
    cx, cy = (x1 + x2) / 2.0, (y1 + y2) / 2.0
    center = MeasurementPoint(role="center", group_code=0, x=ox, y=oy)
    center.detached = False
    center.corrected = True
    center.corrected_x = cx
    center.corrected_y = cy
    center.distance = 0.0
    info.points["center"] = center


def _curve_params(prim: Optional[CurvePrimitive]):
    """circle/arc 基元 → (cx, cy, r)；segment/None → None。"""
    if prim is None or prim.kind not in ("circle", "arc"):
        return None
    return prim.data[0], prim.data[1], prim.data[2]


def _check_radius(
    info: DimensionInfo, snapped: dict[str, Optional[CurvePrimitive]]
) -> None:
    """半径一致性：重构半径 |center−arc_point| 应 ≈ 弧点吸附到的圆/弧半径。"""
    center = info.points.get("center")
    arc_point = info.points.get("arc_point")
    if center is None or arc_point is None:
        return
    if not (center.corrected and arc_point.corrected):
        return  # 未成功吸附的点已由 unresolved 标记，无需再自检
    params = _curve_params(snapped.get("arc_point"))
    if params is None:
        # 弧点应落在圆/弧上，落到线段/无曲线 → 可疑
        center.confidence = LOW_CONFIDENCE
        arc_point.confidence = LOW_CONFIDENCE
        return
    cx0, cy0, r0 = params
    (ccx, ccy), (ax, ay) = _effective(center), _effective(arc_point)
    if abs(math.hypot(ax - ccx, ay - ccy) - r0) > _RADIUS_TOL:
        center.confidence = LOW_CONFIDENCE
        arc_point.confidence = LOW_CONFIDENCE


def _check_diameter(
    info: DimensionInfo, snapped: dict[str, Optional[CurvePrimitive]]
) -> None:
    """直径一致性：两端点应吸附到同一圆上，且重构圆心（中点）≈ 该圆圆心。"""
    e1 = info.points.get("endpoint1")
    e2 = info.points.get("endpoint2")
    center = info.points.get("center")
    if e1 is None or e2 is None:
        return
    if not (e1.corrected and e2.corrected):
        return
    p1 = _curve_params(snapped.get("endpoint1"))
    p2 = _curve_params(snapped.get("endpoint2"))
    targets = [mp for mp in (e1, e2, center) if mp is not None]
    if p1 is None or p2 is None:
        for mp in targets:
            mp.confidence = LOW_CONFIDENCE
        return
    cx1, cy1, r1 = p1
    cx2, cy2, r2 = p2
    same_circle = (
        math.hypot(cx1 - cx2, cy1 - cy2) <= _RADIUS_TOL
        and abs(r1 - r2) <= _RADIUS_TOL
    )
    ccx, ccy = _effective(center)
    center_ok = math.hypot(ccx - cx1, ccy - cy1) <= _RADIUS_TOL
    if not (same_circle and center_ok):
        for mp in targets:
            mp.confidence = LOW_CONFIDENCE


def reconstruct_points(
    info: DimensionInfo,
    index: GeometryIndex,
    curve_index: CurveIndex,
    snap_radius: float = SNAP_RADIUS,
) -> None:
    """对单个 DimensionInfo 的脱钩定义点按类别吸附（原地更新）。

    `index`/`curve_index` 复用 detector 建好的索引；直径额外补 center，
    半径/直径做一致性自检。
    """
    snapped: dict[str, Optional[CurvePrimitive]] = {}
    for role, mp in info.points.items():
        if not mp.detached:
            continue  # 已挂靠点不动
        if role in _CENTER_ROLES:
            _snap_center(mp, index, snap_radius)
        elif role in _ON_CURVE_ROLES:
            snapped[role] = _snap_on_curve(mp, curve_index, snap_radius)
        else:
            _snap_corner(mp, index, snap_radius)

    if info.dxf_type_code == 3:
        _add_diameter_center(info)

    if info.dxf_type_code == 4:
        _check_radius(info, snapped)
    elif info.dxf_type_code == 3:
        _check_diameter(info, snapped)


def reconstruct(
    infos: list[DimensionInfo],
    index: GeometryIndex,
    curve_index: CurveIndex,
    snap_radius: float = SNAP_RADIUS,
) -> None:
    """对全部 DimensionInfo 做测量点位重构（原地更新）。"""
    for info in infos:
        reconstruct_points(info, index, curve_index, snap_radius)


__all__ = [
    "LOW_CONFIDENCE",
    "reconstruct",
    "reconstruct_points",
]
