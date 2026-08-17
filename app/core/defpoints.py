# -*- coding: utf-8 -*-
"""M2.1 尺寸类型判定 + M2.2 定义点提取（分类型）。

T2.1 —— 尺寸类型判定：
    判断类型**只信**「实体类 + 组码 70」的掩码结果，绝不看子类名。
    掩码 `dimtype & 0x07` 得到 0~6（线性/对齐/角度/直径/半径/三点角度/坐标）；
    弧长标注（ARC_DIMENSION）需单独判定——其实体类即弧长，因为 ezdxf 中
    ARC_DIMENSION 的组码 70 存 37（=0x25，即 `angular_3p | BLOCK_EXCLUSIVE`），
    若只 `& 0x07` 会误判成三点角度（实测已确认，见 ARCHITECTURE.md §3.1）。

T2.2 —— 定义点提取（分类型）：
    按类型提取「应吸附」定义点（组码 13/14/10/11/15），OCS→WCS 变换。
    组码语义经实测测试文件逐类型对账（离最近几何 ≤0.01mm 即「挂靠」），
    与 DXF 规范有三处出入（均已在 `_DEFPOINT_SPECS` 注释标注）：
    - 直径对端点是 10 与 14（15 恒 0）；半径弧上点是 14（15 恒 0）；
    - 线性/对齐的 origin2 落在 11（14 恒 0）；
    - 坐标标注的被测特征点落在 11（13 为结构性偏移点）。

角色命名与 JSON schema（ARCHITECTURE.md §5.1）一致：
    线性/对齐 origin1/origin2；角度 origin1/origin2/vertex；
    三点角度 vertex/origin1/origin2；半径 center/arc_point；
    直径 endpoint1/endpoint2；坐标 feature；弧长 center。
"""
from __future__ import annotations

from typing import Optional

from ezdxf.entities import DXFEntity

from app.config import DIM_TYPE_MASK
from app.models import MeasurementPoint

# —— 类型码 → 类型名。8=弧长（ARC_DIMENSION 实体类），5=三点角度 ——
DIM_TYPE_NAMES: dict[int, str] = {
    0: "linear",
    1: "aligned",
    2: "angular",
    3: "diameter",
    4: "radius",
    5: "angular_3p",
    6: "ordinate",
    8: "arc",
}

# —— 各类型要检查的定义点规格：role -> (组码, ezdxf 属性名) ——
# 组码：10=defpoint、11=defpoint2、13=defpoint3、14=defpoint4、15=defpoint5。
# 下表经实测测试文件逐类型对账校准（离最近几何 ≤0.01mm 视为「挂靠」）：
#   - 直径的 10/15 在 DXF 规范里是对端点，但**本文件**实测对端点是 10 与 14，
#     15 恒为 (0,0,0)；同理半径的弧上点是 14 而非 15。
#   - 线性/对齐的第二个延伸线原点 (14) 本文件恒 (0,0,0)，实际原点落在 11
#     （defpoint2 / 文字中点）——故 origin2 取 11。
#   - 坐标标注的「被测特征点」实测在 11（defpoint2），而非规范里的 13。
#   - 三点角度的顶点本文件落在 10（15 恒 0）。
_DEFPOINT_SPECS: dict[int, list[tuple[str, int, str]]] = {
    0: [  # linear 线性（origin2 实测在 11，14 恒 0）
        ("origin1", 13, "defpoint3"),
        ("origin2", 11, "defpoint2"),
    ],
    1: [  # aligned 对齐（同上）
        ("origin1", 13, "defpoint3"),
        ("origin2", 11, "defpoint2"),
    ],
    2: [  # angular 角度（顶点 + 两延伸线原点）
        ("vertex", 10, "defpoint"),
        ("origin1", 13, "defpoint3"),
        ("origin2", 14, "defpoint4"),
    ],
    3: [  # diameter 直径（对端点实测为 10 与 14，圆心=中点，M3 再算）
        ("endpoint1", 10, "defpoint"),
        ("endpoint2", 14, "defpoint4"),
    ],
    4: [  # radius 半径（10 圆心、14 弧上点）
        ("center", 10, "defpoint"),
        ("arc_point", 14, "defpoint4"),
    ],
    5: [  # angular_3p 三点角度（顶点本文件在 10，13/14 两端点）
        ("vertex", 10, "defpoint"),
        ("origin1", 13, "defpoint3"),
        ("origin2", 14, "defpoint4"),
    ],
    6: [  # ordinate 坐标（被测特征点实测在 11）
        ("feature", 11, "defpoint2"),
    ],
    8: [  # arc 弧长（圆心/中心点）
        ("center", 10, "defpoint"),
    ],
}


def dim_type_code(dim: DXFEntity) -> int:
    """返回尺寸类型码（0~6 或 8=弧长）。

    ARC_DIMENSION 实体类直接判为弧长（8）；其余 DIMENSION 用 `dimtype & 0x07`。
    """
    if dim.dxftype() == "ARC_DIMENSION":
        return 8
    return dim.dxf.dimtype & DIM_TYPE_MASK


def dim_type_name(dim: DXFEntity) -> str:
    """返回尺寸类型名（如 "ordinate"）；未知码回退 "unknown_<code>"。"""
    code = dim_type_code(dim)
    return DIM_TYPE_NAMES.get(code, f"unknown_{code}")


def _to_wcs(dim: DXFEntity, point) -> tuple[float, float]:
    """把实体 OCS 内的定义点转到 WCS（2D），兼容旋转 UCS 图纸。

    组码 10/13/14/15 存于实体 OCS（§3.1），统一用 `dim.ocs().to_wcs()` 转 WCS；
    测试文件 Z=0、拉伸 (0,0,1)，OCS=WCS，但代码保留该变换。
    """
    try:
        wcs = dim.ocs().to_wcs(point)
    except Exception:  # noqa: BLE001 —— OCS 异常时退回原始坐标，绝不中断
        wcs = point
    return float(wcs[0]), float(wcs[1])


def extract_defpoints(dim: DXFEntity) -> list[MeasurementPoint]:
    """按类型提取「应吸附」定义点，返回 MeasurementPoint 列表（含 role/组码/WCS 坐标）。

    直径只返回两个对端点（endpoint1/endpoint2），圆心由 M3 重构时取中点计算。
    """
    code = dim_type_code(dim)
    specs = _DEFPOINT_SPECS.get(code, [])
    points: list[MeasurementPoint] = []
    for role, group_code, attr in specs:
        vec = getattr(dim.dxf, attr, None)
        if vec is None:  # 属性缺失则跳过（防御性）
            continue
        x, y = _to_wcs(dim, vec)
        points.append(
            MeasurementPoint(role=role, group_code=group_code, x=x, y=y)
        )
    return points


def diameter_center(dim: DXFEntity) -> Optional[tuple[float, float]]:
    """直径标注的圆心 = 两对端点中点（§3.1 纠正：对端点不是圆心）。

    仅当类型为 diameter(3) 时返回 (cx, cy)，否则返回 None。供 M3 重构用。
    本文件直径对端点为组码 10 与 14（见 _DEFPOINT_SPECS）。
    """
    if dim_type_code(dim) != 3:
        return None
    p1 = getattr(dim.dxf, "defpoint", None)   # 10
    p2 = getattr(dim.dxf, "defpoint4", None)  # 14
    if p1 is None or p2 is None:
        return None
    (x1, y1), (x2, y2) = _to_wcs(dim, p1), _to_wcs(dim, p2)
    return (x1 + x2) / 2.0, (y1 + y2) / 2.0


__all__ = [
    "DIM_TYPE_NAMES",
    "dim_type_code",
    "dim_type_name",
    "extract_defpoints",
    "diameter_center",
]
