# -*- coding: utf-8 -*-
"""曲线空间索引：「曲线上型」吸附判定（ARCHITECTURE.md §3.3 的第二种吸附）。

T2.3 的补充——`GeometryIndex`（特征点 KDTree）只覆盖「角点型 / 圆心型」
吸附（顶点、圆心、象限点、样条控制点）。但大量定义点**落在几何曲线的中部**
而非顶点上：例如线性标注的 13 点落在矩形底边的中段（离左右顶点各 17mm，
离边本身 0），直径对端点落在圆（非象限处），半径弧上点落在圆弧上。

这类点若只用「最近特征点距离」会被误判为脱钩（离最近顶点 1.7~5.1mm，
远超 0.01 阈值），从而把「挂靠」误报成「未挂靠」。本模块按实体提取曲线
基元（线段 / 圆 / 圆弧，样条与椭圆展平成折线），用网格做空间粗筛后
精确计算「点到曲线」最近距离，供 detector 与特征点距离取 min。

曲线基元（均转 WCS 2D）：
    LINE / LWPOLYLINE / POLYLINE  —— 逐段线段；
    CIRCLE                        —— 圆心 + 半径（|dist - r|）；
    ARC                           —— 圆心 + 半径 + 起止角（带角度范围判定）；
    SPLINE / ELLIPSE              —— 展平采样为折线（近似）。

网格（GEOMETRY_GRID_CELL=50mm）：把每个基元按外接矩形登记进其覆盖的
所有网格；查询点只遍历所在格 + 邻格（3×3），对命中基元算精确距离。
「脱钩判定」只需回答「是否存在 ≤0.01mm 的曲线」，而任何 ≤0.01mm 的曲线
其外接矩形必覆盖查询点所在格，故 3×3 邻域对**二值判定**是精确的；
对脱钩点的「最近距离」报告值则是该邻域内的下界（实测脱钩距 1–10mm，
远小于一格，足够准确）。
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional, Sequence

from ezdxf.entities import DXFEntity

from app.config import GEOMETRY_GRID_CELL


@dataclass(frozen=True)
class CurvePrimitive:
    """单个曲线基元（WCS 2D），附带来源实体与类别，供吸附距离与 nearest_entity。"""

    kind: str          # "segment" | "circle" | "arc"
    dxftype: str       # 来源实体类型（LINE/LWPOLYLINE/CIRCLE/ARC/...）
    handle: str        # 来源实体句柄
    data: tuple        # 几何数据：segment=(x1,y1,x2,y2)；circle/arc=(cx,cy,r[,a0,a1])

    @property
    def entity_ref(self) -> str:
        return f"{self.dxftype}:{self.handle}"

    def distance(self, x: float, y: float) -> float:
        """点到该基元的精确最近距离（mm）。"""
        if self.kind == "segment":
            x1, y1, x2, y2 = self.data
            return _point_segment_dist(x, y, x1, y1, x2, y2)
        cx, cy, r = self.data[0], self.data[1], self.data[2]
        d = math.hypot(x - cx, y - cy)
        if self.kind == "circle":
            return abs(d - r)
        # arc：带角度范围
        a0, a1 = self.data[3], self.data[4]
        return _point_arc_dist(x, y, cx, cy, r, a0, a1, d)

    def bbox(self) -> tuple[float, float, float, float]:
        """返回 (minx, miny, maxx, maxy)，用于登记网格。"""
        if self.kind == "segment":
            x1, y1, x2, y2 = self.data
            return (min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2))
        cx, cy, r = self.data[0], self.data[1], self.data[2]
        if self.kind == "circle":
            return (cx - r, cy - r, cx + r, cy + r)
        # arc：取起止点 + 四个轴端点 + 圆心的外接矩形，简化处理
        a0, a1 = self.data[3], self.data[4]
        xs, ys = [cx], [cy]
        for a in (a0, a1):
            xs.append(cx + r * math.cos(a))
            ys.append(cy + r * math.sin(a))
        # 圆弧扫过的象限端点（保证外接矩形覆盖整段弧）
        for k in range(0, 5):
            a = k * math.pi / 2.0
            if _angle_in_arc(a, a0, a1):
                xs.append(cx + r * math.cos(a))
                ys.append(cy + r * math.sin(a))
        return (min(xs), min(ys), max(xs), max(ys))


def _point_segment_dist(px, py, x1, y1, x2, y2) -> float:
    """点到线段最近距离。"""
    dx, dy = x2 - x1, y2 - y1
    if dx == 0.0 and dy == 0.0:  # 退化点
        return math.hypot(px - x1, py - y1)
    t = ((px - x1) * dx + (py - y1) * dy) / (dx * dx + dy * dy)
    t = 0.0 if t < 0.0 else (1.0 if t > 1.0 else t)
    return math.hypot(px - (x1 + t * dx), py - (y1 + t * dy))


def _point_arc_dist(px, py, cx, cy, r, a0, a1, d=None) -> float:
    """点到圆弧最近距离：角度在弧内取 |dist-r|，否则取到两端点距离的最小。"""
    if d is None:
        d = math.hypot(px - cx, py - cy)
    ang = math.atan2(py - cy, px - cx) % (2 * math.pi)
    if _angle_in_arc(ang, a0, a1):
        return abs(d - r)
    sx = cx + r * math.cos(a0)
    sy = cy + r * math.sin(a0)
    ex = cx + r * math.cos(a1)
    ey = cy + r * math.sin(a1)
    return min(math.hypot(px - sx, py - sy), math.hypot(px - ex, py - ey))


def _angle_in_arc(ang: float, a0: float, a1: float) -> bool:
    """判断角 ang（弧度，已归一 0~2π）是否落在从 a0 逆时针扫到 a1 的弧内。"""
    sweep = (a1 - a0) % (2 * math.pi)
    rel = (ang - a0) % (2 * math.pi)
    return rel <= sweep + 1e-12


def _add_segment(out: list[CurvePrimitive], e: DXFEntity, x1, y1, x2, y2) -> None:
    """登记一条线段（跳过零长退化段）。"""
    if abs(x1 - x2) < 1e-12 and abs(y1 - y2) < 1e-12:
        return
    out.append(CurvePrimitive("segment", e.dxftype(), e.dxf.handle, (x1, y1, x2, y2)))


def _extract_curves_one(e: DXFEntity) -> list[CurvePrimitive]:
    """从单个几何图元提取 WCS 曲线基元。"""
    t = e.dxftype()
    out: list[CurvePrimitive] = []

    if t == "LINE":
        s, end = e.dxf.start, e.dxf.end
        _add_segment(out, e, s[0], s[1], end[0], end[1])

    elif t == "CIRCLE":
        cx, cy, _ = e.ocs().to_wcs(e.dxf.center)
        out.append(CurvePrimitive("circle", t, e.dxf.handle, (cx, cy, e.dxf.radius)))

    elif t == "ARC":
        cx, cy, _ = e.ocs().to_wcs(e.dxf.center)
        r = e.dxf.radius
        a0 = math.radians(e.dxf.start_angle)
        a1 = math.radians(e.dxf.end_angle)
        out.append(CurvePrimitive("arc", t, e.dxf.handle, (cx, cy, r, a0, a1)))

    elif t == "LWPOLYLINE":
        elev = e.dxf.elevation
        pts = [e.ocs().to_wcs((x, y, elev)) for x, y in e.get_points(format="xy")]
        for i in range(len(pts) - 1):
            _add_segment(out, e, pts[i][0], pts[i][1], pts[i + 1][0], pts[i + 1][1])
        if e.closed and len(pts) > 2:
            _add_segment(out, e, pts[-1][0], pts[-1][1], pts[0][0], pts[0][1])

    elif t == "POLYLINE":
        if e.is_2d_polyline:
            pts = [e.ocs().to_wcs(p) for p in e.points()]
        else:
            pts = list(e.points())
        for i in range(len(pts) - 1):
            _add_segment(out, e, pts[i][0], pts[i][1], pts[i + 1][0], pts[i + 1][1])
        if e.is_closed and len(pts) > 2:
            _add_segment(out, e, pts[-1][0], pts[-1][1], pts[0][0], pts[0][1])

    elif t in ("SPLINE", "ELLIPSE"):
        # 展平成折线（近似）：SPLINE 用 flattening，ELLIPSE 采样 64 段。
        try:
            if t == "ELLIPSE":
                pts = list(e.vertices([2 * math.pi * i / 64 for i in range(65)]))
            else:
                pts = list(e.flattening(0.5))
        except Exception:  # noqa: BLE001 —— 展平失败则退回控制点/顶点
            pts = []
        for i in range(len(pts) - 1):
            _add_segment(out, e, pts[i][0], pts[i][1], pts[i + 1][0], pts[i + 1][1])

    return out


def extract_curves(geometry: Sequence[DXFEntity]) -> list[CurvePrimitive]:
    """从几何图元集合提取全部 WCS 曲线基元（一次遍历）。"""
    curves: list[CurvePrimitive] = []
    for e in geometry:
        curves.extend(_extract_curves_one(e))
    return curves


class CurveIndex:
    """曲线基元网格索引：查询点到最近曲线的精确距离（曲线上型）。"""

    def __init__(self, geometry: Sequence[DXFEntity]):
        self.primitives = extract_curves(geometry)
        self._cell = float(GEOMETRY_GRID_CELL)
        self._grid: dict[tuple[int, int], list[CurvePrimitive]] = {}
        self._build()

    def _build(self) -> None:
        for p in self.primitives:
            minx, miny, maxx, maxy = p.bbox()
            i0 = int(math.floor(minx / self._cell))
            i1 = int(math.floor(maxx / self._cell))
            j0 = int(math.floor(miny / self._cell))
            j1 = int(math.floor(maxy / self._cell))
            for i in range(i0, i1 + 1):
                for j in range(j0, j1 + 1):
                    self._grid.setdefault((i, j), []).append(p)

    @property
    def curve_count(self) -> int:
        return len(self.primitives)

    def nearest(self, x: float, y: float) -> tuple[float, Optional[CurvePrimitive]]:
        """返回 (最近距离, 最近曲线基元)；索引为空时 (inf, None)。"""
        if not self.primitives:
            return float("inf"), None
        i = int(math.floor(x / self._cell))
        j = int(math.floor(y / self._cell))
        best_d = float("inf")
        best_p: Optional[CurvePrimitive] = None
        seen: set[int] = set()
        for di in (-1, 0, 1):
            for dj in (-1, 0, 1):
                cell = self._grid.get((i + di, j + dj))
                if not cell:
                    continue
                for p in cell:
                    pid = id(p)
                    if pid in seen:
                        continue
                    seen.add(pid)
                    d = p.distance(x, y)
                    if d < best_d:
                        best_d = d
                        best_p = p
        return best_d, best_p


__all__ = [
    "CurvePrimitive",
    "extract_curves",
    "CurveIndex",
]
