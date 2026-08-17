# -*- coding: utf-8 -*-
"""M1 文件解析：读取 / 解码 / 校验 / recover 容错。

T1.1 —— DXF 解析与解码：
    ezdxf 读取 DXF，正确处理 GBK（ANSI_936）编码；容错损坏文件。
T1.2 —— 实体与图层抽取：
    抽取几何实体、DIMENSION、块定义、图层表，提供统一数据接口，
    可「按类型 / 按图层」过滤查询，且不丢失任何模型空间实体。

三级容错策略（见 ARCHITECTURE.md §6.2）：
    1. 主读取 `ezdxf.readfile(errors="replace")`，自动按 `$DWGCODEPAGE` 选码；
    2. 编码兜底：`UnicodeDecodeError` 时显式按 GBK 重读；
    3. 结构损坏：`ezdxf.recover.readfile()` 修复模式兜底。
任何异常不抛给调用方崩溃，而是记录进 `LoadedDrawing.warnings`；
仅「文件不存在 / 三种方式全部失败」才抛 `LoadError`（由 GUI 友好提示）。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator, Optional, Sequence

import ezdxf
from ezdxf.document import Drawing
from ezdxf.entities import DXFEntity

# —— 几何图元类型：供 M2 特征点提取用。含线/弧/圆/样条/多段线/椭圆/点 ——
# 刻意**不含** DIMENSION/INSERT/TEXT/MTEXT/HATCH/SOLID 及 `*D` 块内部图元，
# 因为这些不是「可吸附」的几何轮廓（见 ARCHITECTURE.md §3.2）。
GEOMETRY_DXF_TYPES: frozenset[str] = frozenset({
    "LINE", "ARC", "CIRCLE", "SPLINE", "LWPOLYLINE", "POLYLINE", "ELLIPSE", "POINT",
})

# —— 尺寸标注图元类型。ARC_DIMENSION 为「弧长标注」，与 DIMENSION 同族参与判定 ——
DIMENSION_DXF_TYPES: frozenset[str] = frozenset({
    "DIMENSION", "ARC_DIMENSION",
})


class LoadError(RuntimeError):
    """DXF 加载失败（主读取 + recover 均失败时的兜底异常）。

    上层（GUI / pipeline）捕获后友好提示，不让程序崩溃退出。
    """


def _normalize_types(dxftype: Optional[str | Sequence[str]]) -> Optional[frozenset[str]]:
    """把单个字符串 / 序列统一成 frozenset，便于 `in` 查询；None 表示不过滤。"""
    if dxftype is None:
        return None
    if isinstance(dxftype, str):
        return frozenset({dxftype})
    return frozenset(dxftype)


@dataclass
class LoadedDrawing:
    """一次加载的结果封装。

    `doc` 负责后续 DXF 修改（M4 块转换 / M5 另存）；分类列表负责快速遍历查询。
    `entities` 保留模型空间**全部**实体（保序），保证「数据无丢失」可自检：
    `len(entities) == len(dimensions) + len(geometry) + len(other)`。
    """

    path: str
    doc: Drawing
    entities: list[DXFEntity] = field(default_factory=list)    # 模型空间全部实体（保序）
    dimensions: list[DXFEntity] = field(default_factory=list)  # DIMENSION + ARC_DIMENSION
    geometry: list[DXFEntity] = field(default_factory=list)    # 几何图元（§3.2 白名单）
    blocks: list = field(default_factory=list)                 # 块定义（BlockLayout 对象）
    layers: list[str] = field(default_factory=list)            # 图层名（升序）
    warnings: list[str] = field(default_factory=list)          # 非致命告警（解码回退/审计等）
    recovered: bool = False                                    # 是否走了 recover 修复模式

    # —— 便捷计数（供 GUI 汇总 / 日志） ——
    @property
    def entity_count(self) -> int:
        return len(self.entities)

    @property
    def dimension_count(self) -> int:
        return len(self.dimensions)

    @property
    def geometry_count(self) -> int:
        return len(self.geometry)

    @property
    def other_count(self) -> int:
        """非尺寸、非几何的其余实体（TEXT/MTEXT/INSERT/HATCH/SOLID…）数量。"""
        return self.entity_count - self.dimension_count - self.geometry_count

    @property
    def layer_count(self) -> int:
        return len(self.layers)

    @property
    def block_count(self) -> int:
        return len(self.blocks)

    # —— 统一数据接口：按类型 / 图层过滤查询（T1.2 验收点） ——
    def iter_entities(
        self,
        dxftype: Optional[str | Sequence[str]] = None,
        layer: Optional[str] = None,
    ) -> Iterator[DXFEntity]:
        """迭代模型空间实体，支持按 dxftype（单个或集合）与图层过滤。

        两者皆为 None 时等价于遍历全部实体。
        """
        types = _normalize_types(dxftype)
        for e in self.entities:
            if types is not None and e.dxftype() not in types:
                continue
            if layer is not None and e.dxf.layer != layer:
                continue
            yield e

    def count_by_type(self) -> dict[str, int]:
        """按 dxftype 统计实体数量（用于验收：与实测画像对账）。"""
        counts: dict[str, int] = {}
        for e in self.entities:
            counts[e.dxftype()] = counts.get(e.dxftype(), 0) + 1
        return counts

    def summarize(self) -> str:
        """单行概览，用于日志与 M1 验收输出（如「961 尺寸 / 56 图层」）。"""
        return (
            f"实体 {self.entity_count}（尺寸 {self.dimension_count} / "
            f"几何 {self.geometry_count} / 其他 {self.other_count}）"
            f"，图层 {self.layer_count}，块定义 {self.block_count}"
        )


def _read_doc(path: Path) -> tuple[Drawing, list[str], bool]:
    """按三级容错读取 DXF，返回 (doc, warnings, recovered)。

    仅在三种方式全部失败时抛 `LoadError`；文件不存在抛 `FileNotFoundError`。
    """
    warnings: list[str] = []
    recovered = False
    doc: Optional[Drawing] = None

    # 1. 主读取：自动按 header 的 $DWGCODEPAGE 选码（ANSI_936 → GBK），
    #    errors="replace" 防止个别生僻字符导致整文件解码中断。
    try:
        doc = ezdxf.readfile(str(path), errors="replace")
    except UnicodeDecodeError:
        # 2. 编码兜底：自动选码失败时显式按 GBK 重读。
        try:
            doc = ezdxf.readfile(str(path), encoding="gbk", errors="replace")
            warnings.append("编码回退：自动按 $DWGCODEPAGE 解码失败，已显式按 GBK 读取")
        except Exception as exc:  # noqa: BLE001 —— 记录后交给 recover
            warnings.append(f"GBK 显式读取失败：{type(exc).__name__}: {exc}")
            doc = None
    except (ezdxf.DXFStructureError, ezdxf.DXFVersionError, ezdxf.DXFError) as exc:
        warnings.append(f"结构/版本异常：{type(exc).__name__}: {exc}")
        doc = None
    except OSError:
        raise  # 文件级错误（权限/占用等）原样上抛，由 GUI 提示
    except Exception as exc:  # noqa: BLE001 —— 兜底，绝不因未知异常崩溃
        warnings.append(f"读取异常：{type(exc).__name__}: {exc}")
        doc = None

    # 3. 严重损坏回退 recover 修复模式。
    if doc is None:
        recovered = True
        try:
            result = ezdxf.recover.readfile(str(path), errors="replace")
            # recover.readfile 返回 (doc, auditor) 二元组
            doc, auditor = result if isinstance(result, tuple) else (result, None)
            warnings.append("已进入 recover 修复模式读取（可能丢失部分损坏数据）")
            if auditor is not None and getattr(auditor, "has_errors", False):
                warnings.append(f"recover 修复报告 {len(auditor.errors)} 处错误")
        except Exception as exc:  # noqa: BLE001
            raise LoadError(f"DXF 无法加载（含修复模式）：{type(exc).__name__}: {exc}") from exc

    if doc is None:
        raise LoadError("DXF 无法加载：主读取与修复模式均未返回有效文档")

    # 4. 结构自检：audit 报告错误但继续（ezdxf 宽容解析），错误仅告警不中断。
    try:
        auditor = doc.audit()
        if auditor.has_errors:
            warnings.append(f"结构自检发现 {len(auditor.errors)} 处错误（已宽容保留）")
    except Exception as exc:  # noqa: BLE001
        warnings.append(f"audit 自检失败：{type(exc).__name__}")

    return doc, warnings, recovered


def _build_loaded(
    path: Path, doc: Drawing, warnings: list[str], recovered: bool
) -> LoadedDrawing:
    """遍历模型空间，分类抽取实体，并收集图层表 / 块定义。"""
    loaded = LoadedDrawing(
        path=str(path), doc=doc, warnings=warnings, recovered=recovered
    )

    # 模型空间实体：一次遍历完成全部分类，不重复扫描（§9.1）。
    for e in doc.modelspace():
        loaded.entities.append(e)
        dxftype = e.dxftype()
        if dxftype in DIMENSION_DXF_TYPES:
            loaded.dimensions.append(e)
        elif dxftype in GEOMETRY_DXF_TYPES:
            loaded.geometry.append(e)

    # 图层表（升序，便于对账）；块定义（含 *Model_Space/*Paper_Space 与全部 *D 块）。
    loaded.layers = sorted(layer.dxf.name for layer in doc.layers)
    loaded.blocks = list(doc.blocks)

    return loaded


def load_dxf(path: str | Path) -> LoadedDrawing:
    """加载 DXF 文件入口：解析 + 分类，返回 `LoadedDrawing`。

    仅「文件不存在」或「主读取 + recover 均失败」时抛异常，其余情况
    一律返回带 `warnings` 的封装对象，保证流水线不因非致命问题中断。
    """
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"文件不存在：{p}")

    doc, warnings, recovered = _read_doc(p)
    return _build_loaded(p, doc, warnings, recovered)


__all__ = [
    "LoadedDrawing",
    "LoadError",
    "load_dxf",
    "GEOMETRY_DXF_TYPES",
    "DIMENSION_DXF_TYPES",
]
