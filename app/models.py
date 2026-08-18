# -*- coding: utf-8 -*-
"""内部数据模型（dataclass）。

依据 `ARCHITECTURE.md` §5.2。数据在内存中以 `doc`（ezdxf Drawing）与
`Result`（本模块 dataclass）两种形态流转：`doc` 负责 DXF 修改，
`Result` 负责 JSON 序列化与 GUI 展示。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class MeasurementPoint:
    """单个定义点的吸附结果。"""
    role: str                      # 点位角色：origin1/origin2/vertex/center/feature ...
    group_code: int                # 组码 13/14/10/15
    x: float
    y: float
    detached: bool = False
    corrected: bool = False
    corrected_x: Optional[float] = None
    corrected_y: Optional[float] = None
    unresolved: bool = False       # 吸附目标超出 snap_radius，保留原坐标未能纠偏
    distance: Optional[float] = None
    nearest_entity: Optional[str] = None
    confidence: float = 1.0        # 1.0 高置信；吸附后一致性自检失败标 low_confidence


@dataclass
class Tolerance:
    """尺寸公差。mode 枚举：none/symmetrical/deviation/limits/basic。"""
    raw: str = ""
    mode: str = "none"
    nominal: Optional[float] = None
    upper: Optional[float] = None
    lower: Optional[float] = None


@dataclass
class BBox:
    """轴对齐最小外接矩（世界坐标）。"""
    minx: float = 0.0
    miny: float = 0.0
    maxx: float = 0.0
    maxy: float = 0.0


@dataclass
class BlockInfo:
    """标注图元标准化（转块）结果。"""
    name: str = ""
    created: bool = False
    layer: str = ""
    converted_from: str = ""       # "DIMENSION" / "INSERT"


@dataclass
class DimensionInfo:
    """单个尺寸标注的完整信息。"""
    handle: str
    type: str
    dxf_type_code: int = 0
    dimstyle: str = ""
    layer: str = ""
    value: Optional[float] = None
    text: str = ""
    tolerance: Optional[Tolerance] = None
    bbox: Optional[BBox] = None
    unattached: bool = False
    detach_distance: float = 0.0
    points: dict[str, MeasurementPoint] = field(default_factory=dict)
    block: Optional[BlockInfo] = None


@dataclass
class SummaryEntry:
    """全部尺寸的概要（供自动化比对验收）。"""
    handle: str
    type: str
    value: Optional[float]
    unattached: bool


@dataclass
class Result:
    """一次处理的完整结果。"""
    file: str = ""
    output_dxf: str = ""
    unit: str = "mm"
    dxf_version: str = ""
    detach_tolerance: float = 0.01
    snap_radius: float = 50.0
    processed_at: str = ""          # 处理时间（ISO）；空时由 json_export 兜底填充
    total_dimensions: int = 0
    unattached_count: int = 0
    summary: list[SummaryEntry] = field(default_factory=list)
    dimensions: list[DimensionInfo] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
