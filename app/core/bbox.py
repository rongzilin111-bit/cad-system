# -*- coding: utf-8 -*-
"""M3.1 标注轴对齐最小外接矩。

TODO(T3.1): 首选 `dim.get_geometry_block()` 图元 + `ezdxf.bbox.extents`；
块缺失时回退 `get_geometry().virtual_entities()`。取 extmin/extmax 即
MinX/MinY/MaxX/MaxY。见 ARCHITECTURE.md §3.4。
"""
from __future__ import annotations
