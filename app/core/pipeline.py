# -*- coding: utf-8 -*-
"""编排层：单文件 → Result 的完整流水线。

TODO: 串联 loader → geometry_index → defpoints → detector → bbox →
dimension_text → reconstruct → blockify → io 导出。见 ARCHITECTURE.md §1.2。
"""
from __future__ import annotations
