# -*- coding: utf-8 -*-
"""M6 后台处理线程（QThread）。

TODO(T6.1): 在后台线程执行 pipeline，避免 UI 冻结；进度条/日志流信号回主线程。
见 ARCHITECTURE.md §7.2。
"""
from __future__ import annotations
