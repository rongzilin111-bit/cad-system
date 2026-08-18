# -*- coding: utf-8 -*-
"""M5 另存 DXF。

T5.1 —— 把已标准化（转块 + 归层）的文档另存为 DXF，完整保留图层 / 颜色 /
线型 / 块定义（含未改动的全部命名块与孤儿 `*D` 块），仅新增
`Dim_Reconstruct_Layer` + 命名块并删除原 DIMENSION（被等价 INSERT 替代）。
全程内存修改，保存前不在磁盘写中间文件（ARCHITECTURE.md §6.3）。

输出命名由上层用 `pipeline.output_dxf_path(input)` 派生 `{原名}_reconstructed.dxf`
（不覆盖原文件），本模块只负责「把 doc 落盘」，不关心命名策略。

GBK 写出（ezdxf 1.4.4 实测怪癖）：`doc.saveas(path, encoding="gbk")` **不会**重写
`$DWGCODEPAGE` 表头（仍写默认 `ANSI_1252`），导致「GBK 字节 + 错误表头」回读
中文乱码。正确写法需三者配合：

    doc.encoding = "gbk"
    doc.header["$DWGCODEPAGE"] = "ANSI_936"
    doc.saveas(path)              # 不再传 encoding 参数

loader 读真实文件时按 `$DWGCODEPAGE=ANSI_936` 自动选码后 `doc.encoding='gbk'`
已实测正确，此处仅在「编码属 GBK 族」时同步表头，非 GBK 文档原样另存不强制。
"""
from __future__ import annotations

from pathlib import Path
from typing import Union

from ezdxf.document import Drawing

# GBK 编码族：loader 按 $DWGCODEPAGE=ANSI_936 自动选码后，doc.encoding 落在这组。
_GBK_CODECS = frozenset({"gbk", "cp936", "gb2312", "gb18030", "ansi_936"})


def _sync_gbk_header(doc: Drawing) -> None:
    """若文档编码属 GBK 族，同步 codec 与 `$DWGCODEPAGE` 表头（防回读乱码）。

    只改编码族内的文档；UTF-8 / cp1252 等原样保留，不越界干预。
    """
    enc = (doc.encoding or "").lower()
    if enc in _GBK_CODECS:
        doc.encoding = "gbk"
        doc.header["$DWGCODEPAGE"] = "ANSI_936"


def save_document(doc: Drawing, path: Union[str, Path]) -> str:
    """把已标准化文档另存为 DXF，返回写入路径字符串。

    版本沿用 `doc.dxfversion`（AC1032），编码保持原文档编码（GBK 无损）。
    自动创建父目录；调用方负责派生「不覆盖原文件」的输出路径。
    """
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    _sync_gbk_header(doc)
    doc.saveas(str(p))
    return str(p)


__all__ = ["save_document"]
