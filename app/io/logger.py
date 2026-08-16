# -*- coding: utf-8 -*-
"""M5 轮转日志（保留 ≥180 天）。

TODO(T5.2): RotatingFileHandler（按大小/日期轮转），记录检测时间/文件名/
问题统计；本地处理不联网。见 ARCHITECTURE.md §9.2。
"""
from __future__ import annotations
