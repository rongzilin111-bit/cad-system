# -*- coding: utf-8 -*-
"""M1 文件解析：读取 / 解码 / 校验 / recover 容错。

TODO(T1.1/T1.2): 实现 `ezdxf.readfile` + GBK 解码 + audit/recover 三级容错，
抽取几何实体、DIMENSION、块定义、图层表，提供统一数据接口。
见 ARCHITECTURE.md §6。
"""
from __future__ import annotations
