# -*- coding: utf-8 -*-
"""M3.2 尺寸值与公差解析。

TODO(T3.2): 优先 `dim.get_measurement()`（组码 42），文字覆盖时解析覆盖文本；
解码 `%%C/%%D/%%P`、`\S上^下`；无显式公差读 DIMSTYLE 的 DIMTOL/DIMTP/DIMTM。
见 ARCHITECTURE.md §5.3。
"""
from __future__ import annotations
