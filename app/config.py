# -*- coding: utf-8 -*-
"""全局配置常量。

依据 `ARCHITECTURE.md` §2/§4/§7，集中存放判定阈值、吸附半径、图层名、
块名前缀等可配置项。GUI 中允许用户覆盖部分参数（如容差、吸附半径）。
"""
from __future__ import annotations

# —— 未挂靠判定 ——
DETACH_TOLERANCE = 0.01      # 判定阈值（mm）。实测距离分布双峰，0.01 为干净分界
SNAP_RADIUS = 50.0           # 测量点位吸附最大距离（mm）。实测脱钩距 1–10mm

# —— 图元标准化 ——
TARGET_LAYER = "Dim_Reconstruct_Layer"   # 需求指定的专用图层名
BLOCK_NAME_PREFIX = "Dim_Reconstruct_"   # 命名块前缀（与 handle 拼接，见 §4.4）

# —— 输出 ——
OUTPUT_SUFFIX = "_reconstructed"          # 另存 DXF 文件后缀
LOG_RETENTION_DAYS = 180                  # 日志保留天数（需求 ≥180 天）
LOG_DIR = "logs"

# —— 空间索引 ——
GEOMETRY_GRID_CELL = 50.0                 # 几何网格边长（mm），用于「曲线上型」吸附

# —— 类型判定 ——
# 判断尺寸类型只用 `dimtype & 0x07`（不要信子类名）。此处为掩码常量。
DIM_TYPE_MASK = 0x07
