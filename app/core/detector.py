# -*- coding: utf-8 -*-
"""M2 未挂靠判定（核心）。

TODO(T2.4): 对每个 DIMENSION 的定义点查最近几何距离，
任一距离 > DETACH_TOLERANCE(0.01mm) → 判定「未挂靠」。
见 ARCHITECTURE.md §3.2。
"""
from __future__ import annotations
