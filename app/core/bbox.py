# -*- coding: utf-8 -*-
"""M3.1 标注轴对齐最小外接矩。

T3.1：计算「整个标注」的轴对齐最小外接矩（含尺寸线 / 延伸线 / 文字 / 箭头），
返回世界坐标 MinX/MinY/MaxX/MaxY。

两种取法（见 ARCHITECTURE.md §3.4）：
    首选 A —— `dim.get_geometry_block()` 遍历几何块图元 + `ezdxf.bbox.extents`，
              零重绘、精确到存储图元、快；依赖 `*D` 块存在。
    回退 B —— `dim.virtual_entities()` 重渲染虚拟图元再算 bbox，
              不依赖既有块；略慢。

`ezdxf.bbox.extents` 会递归展开块内 INSERT（箭头块）、按 MTEXT 高度/列宽
近似文字包围盒，返回 `BoundingBox`，取 `.extmin/.extmax` 即四角坐标。
"""
from __future__ import annotations

from typing import Optional

from ezdxf import bbox as _bbox
from ezdxf.entities import DXFEntity

from app.models import BBox


def _extents_to_bbox(entities) -> Optional[BBox]:
    """对图元列表算 bbox 并转成内部 BBox；空/异常返回 None（绝不抛给调用方）。"""
    if not entities:
        return None
    try:
        ext = _bbox.extents(entities)
    except Exception:  # noqa: BLE001 —— 个别异常图元不应中断流水线
        return None
    if not getattr(ext, "has_data", False):
        return None
    return BBox(
        minx=float(ext.extmin.x),
        miny=float(ext.extmin.y),
        maxx=float(ext.extmax.x),
        maxy=float(ext.extmax.y),
    )


def _block_entities(dim: DXFEntity) -> list:
    """方案 A：取几何块内图元（`*D` 块）；块缺失/空块/异常返回空列表。"""
    try:
        blk = dim.get_geometry_block()
    except Exception:  # noqa: BLE001
        return []
    if blk is None:
        return []
    try:
        return list(blk)
    except Exception:  # noqa: BLE001
        return []


def _virtual_entities(dim: DXFEntity) -> list:
    """方案 B：重渲染虚拟图元；异常返回空列表。"""
    try:
        return list(dim.virtual_entities())
    except Exception:  # noqa: BLE001
        return []


def compute_bbox(dim: DXFEntity) -> Optional[BBox]:
    """计算单个标注的轴对齐最小外接矩（WCS）；无法计算返回 None。

    首选几何块图元（方案 A），空块/缺块回退虚拟图元（方案 B），
    两种都失败返回 None（保证流水线不中断，上层以 None 兜底）。
    """
    result = _extents_to_bbox(_block_entities(dim))
    if result is not None:
        return result
    return _extents_to_bbox(_virtual_entities(dim))


__all__ = ["compute_bbox"]
