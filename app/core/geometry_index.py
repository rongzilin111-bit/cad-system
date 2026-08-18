# -*- coding: utf-8 -*-
"""空间索引：几何特征点提取 + KDTree（T2.3）。

从模型空间几何图元（LINE/ARC/CIRCLE/SPLINE/LWPOLYLINE/POLYLINE/ELLIPSE/POINT）
提取特征点（实测 37,829 量级），构建 scipy.cKDTree 支持最近邻查询，scipy
缺失时回退 numpy 暴力。刻意**不取** DIMENSION/INSERT/TEXT/MTEXT/HATCH/SOLID
及 `*D` 块内部图元——这些不是「可吸附」的几何轮廓（ARCHITECTURE.md §3.2）。

特征点提取规则（§3.2）：
    LINE 起点+终点；ARC 起点+终点+圆心；CIRCLE 圆心+4 象限点；
    SPLINE 控制点；LWPOLYLINE/POLYLINE 全部顶点；ELLIPSE 中心+长短轴端点；
    POINT 该点。

坐标系约定（依 ezdxf 源码逐项核实）：
    WCS 直接可用 —— Line.dxf.start/end、Arc.start_point/end_point、
        Spline.control_points、Circle/Ellipse.vertices(...)；
    OCS 需转 —— Arc/Circle/Ellipse 的 dxf.center、LWPOLYLINE.get_points、
        Polyline（2D）points、Point.dxf.location → 实体 `.ocs().to_wcs()`。

「曲线上型」吸附所需的几何网格（点到线段/圆弧投影）在 M3 `reconstruct.py`
实现，不在此处——M2 判定只用特征点 KDTree。
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional, Sequence

import numpy as np
from ezdxf.entities import DXFEntity


@dataclass(frozen=True)
class FeaturePoint:
    """单个几何特征点（WCS 2D），附带来源实体与类别标签。"""
    x: float
    y: float
    dxftype: str      # 来源实体类型（LINE/ARC/...）
    handle: str       # 来源实体句柄
    kind: str         # 类别：line_end/arc_center/circle_quadrant/...

    @property
    def entity_ref(self) -> str:
        """形如 'LINE:ABC1' 的实体引用，供 MeasurementPoint.nearest_entity。"""
        return f"{self.dxftype}:{self.handle}"


def _fp(e: DXFEntity, point, kind: str) -> FeaturePoint:
    """把 (x, y, z) 点包装成 FeaturePoint（截取前两维）。"""
    return FeaturePoint(
        x=float(point[0]),
        y=float(point[1]),
        dxftype=e.dxftype(),
        handle=e.dxf.handle,
        kind=kind,
    )


def _extract_one(e: DXFEntity) -> list[FeaturePoint]:
    """从单个几何图元提取 WCS 特征点（按类型分派）。"""
    t = e.dxftype()
    out: list[FeaturePoint] = []

    if t == "LINE":
        out.append(_fp(e, e.dxf.start, "line_end"))
        out.append(_fp(e, e.dxf.end, "line_end"))

    elif t == "ARC":
        out.append(_fp(e, e.start_point, "arc_end"))
        out.append(_fp(e, e.end_point, "arc_end"))
        out.append(_fp(e, e.ocs().to_wcs(e.dxf.center), "arc_center"))

    elif t == "CIRCLE":
        out.append(_fp(e, e.ocs().to_wcs(e.dxf.center), "circle_center"))
        for p in e.vertices([0, 90, 180, 270]):
            out.append(_fp(e, p, "circle_quadrant"))

    elif t == "SPLINE":
        for cp in e.control_points:
            out.append(_fp(e, cp, "spline_control"))

    elif t == "LWPOLYLINE":
        elev = e.dxf.elevation
        for x, y in e.get_points(format="xy"):
            out.append(_fp(e, e.ocs().to_wcs((x, y, elev)), "polyline_vertex"))

    elif t == "POLYLINE":
        # 2D 多段线顶点为 OCS，3D 多段线顶点为 WCS（ezdxf 约定）。
        if e.is_2d_polyline:
            for p in e.points():
                out.append(_fp(e, e.ocs().to_wcs(p), "polyline_vertex"))
        else:
            for p in e.points():
                out.append(_fp(e, p, "polyline_vertex"))

    elif t == "ELLIPSE":
        out.append(_fp(e, e.ocs().to_wcs(e.dxf.center), "ellipse_center"))
        # 0/π = 长轴端点，π/2/3π/2 = 短轴端点（参数化顶点，WCS）。
        for p in e.vertices([0, math.pi / 2, math.pi, 3 * math.pi / 2]):
            out.append(_fp(e, p, "ellipse_axis"))

    elif t == "POINT":
        out.append(_fp(e, e.ocs().to_wcs(e.dxf.location), "point"))

    return out


def extract_feature_points(geometry: Sequence[DXFEntity]) -> list[FeaturePoint]:
    """从几何图元集合提取全部 WCS 特征点（§3.2 规则，一次遍历）。"""
    points: list[FeaturePoint] = []
    for e in geometry:
        points.extend(_extract_one(e))
    return points


class GeometryIndex:
    """几何特征点空间索引。

    主索引 scipy.cKDTree（O(log n) 查询）；scipy 不可用时回退 numpy 暴力
    （38k 点 × 数千查询在秒级内，仍满足「小图 ≤1s」）。索引只建一次、全查询复用。
    """

    def __init__(self, geometry: Sequence[DXFEntity], expand_insert: bool = False):
        # expand_insert 为 ARCHITECTURE.md §11 的「几何藏块内」扩展开关，M2 暂不展开。
        self.points = extract_feature_points(geometry)
        self._coords = np.asarray(
            [[p.x, p.y] for p in self.points], dtype=float
        )
        self._tree = None
        if len(self.points) > 0:
            try:
                from scipy.spatial import cKDTree  # 局部导入，便于 PyInstaller 裁剪
                self._tree = cKDTree(self._coords)
            except Exception:  # noqa: BLE001 —— scipy 缺失，回退暴力
                self._tree = None
        # 圆心型吸附专用：惰性构建「圆心/弧心」子索引（M3.3 才用）。
        self._center_points: list[FeaturePoint] = []
        self._center_tree = None

    @property
    def point_count(self) -> int:
        return len(self.points)

    def nearest_center(self, x: float, y: float) -> tuple[float, Optional[FeaturePoint]]:
        """返回 (最近距离, 最近圆心/弧心)；供圆心型定义点吸附（M3.3）。

        只在 kind ∈ {circle_center, arc_center} 的特征点里查最近，
        避免圆心吸附到线端点等无关特征点（见 ARCHITECTURE.md §3.3）。
        """
        if self._center_tree is None:
            self._build_center_index()
        if not self._center_points:
            return float("inf"), None
        if self._center_tree is None:  # scipy 缺失，回退暴力
            return self._nearest_center_bruteforce(x, y)
        dist, idx = self._center_tree.query([x, y])
        return float(dist), self._center_points[int(idx)]

    def _build_center_index(self) -> None:
        """惰性构建圆心/弧心子索引（首次 nearest_center 时）。"""
        self._center_points = [
            p for p in self.points if p.kind in ("arc_center", "circle_center")
        ]
        if not self._center_points:
            return
        coords = np.asarray(
            [[p.x, p.y] for p in self._center_points], dtype=float
        )
        try:
            from scipy.spatial import cKDTree  # 局部导入，便于 PyInstaller 裁剪
            self._center_tree = cKDTree(coords)
        except Exception:  # noqa: BLE001 —— scipy 缺失，回退暴力
            self._center_tree = None

    def _nearest_center_bruteforce(self, x: float, y: float) -> tuple[float, Optional[FeaturePoint]]:
        """圆心子集暴力回退。"""
        coords = np.asarray(
            [[p.x, p.y] for p in self._center_points], dtype=float
        )
        delta = coords - np.array([x, y], dtype=float)
        dists = np.einsum("ij,ij->i", delta, delta)
        idx = int(np.argmin(dists))
        return float(math.sqrt(dists[idx])), self._center_points[idx]

    def nearest(self, x: float, y: float) -> tuple[float, Optional[FeaturePoint]]:
        """返回 (最近距离, 最近特征点)；空索引时 (inf, None)。"""
        if self._tree is None:
            return self._nearest_bruteforce(x, y)
        dist, idx = self._tree.query([x, y])
        return float(dist), self.points[int(idx)]

    def _nearest_bruteforce(self, x: float, y: float) -> tuple[float, Optional[FeaturePoint]]:
        """numpy 暴力回退：全点算距离取最小。"""
        if len(self._coords) == 0:
            return float("inf"), None
        delta = self._coords - np.array([x, y], dtype=float)
        dists = np.einsum("ij,ij->i", delta, delta)  # 平方距离，免开方
        idx = int(np.argmin(dists))
        return float(math.sqrt(dists[idx])), self.points[idx]


__all__ = [
    "FeaturePoint",
    "extract_feature_points",
    "GeometryIndex",
]
