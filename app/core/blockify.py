# -*- coding: utf-8 -*-
"""M4 图元标准化：DIMENSION → 命名块（复用 *D 块）、归层。

T4.1 —— DIMENSION → 块重组（方案 A「复用重命名 *D 块」，ARCHITECTURE.md §4）：
    改名 `*D`→唯一命名块 → 清匿名标志 70=1→0 → 建 INSERT（基点=块 base_point、
    scale=1/rot=0）→ 逐图元归层 → 删原 DIMENSION。零重绘、视觉绝对不变。
T4.2 —— 归层处理：新块 INSERT 与块内图元统一落到 `Dim_Reconstruct_Layer`；
    「原本就是块」的标注走 §4.5 幂等分支——引用 `Dim_Reconstruct_` 前缀块的
    INSERT 重跑时仅改图层，不重组（`relayer_existing_blocks`）。

关键事实（§4.1 已实测）：`*D` 块图元坐标为 WCS 绝对坐标、基点 (0,0,0)、
线型 ByBlock → INSERT 到其 base_point、scale=1、rot=0 即原位落点，无平移/缩放/旋转。
孤儿 `*D` 块默认不删（严格满足「保留块定义」，GUI 复选框默认关，§4.6）。

ezdxf 1.4.4 注意：`blocks.rename_block` 是底层工具，**不更新任何引用**（含
DIMENSION 组码 2），改名后组码 2 的旧名成为悬空字符串——但因原 DIMENSION 随即
被删除而无副作用；箭头块是块内 INSERT，设层后其 ByBlock/0 层图元继承新层。

兜底：单尺寸转换失败仅记告警并跳过，绝不中断流水线。
"""
from __future__ import annotations

from typing import Optional

from ezdxf.document import Drawing
from ezdxf.layouts import BlockLayout

from app.config import BLOCK_NAME_PREFIX, TARGET_LAYER
from app.models import BlockInfo, DimensionInfo

# —— 参与转换的尺寸实体类型（与 loader 的 DIMENSION_DXF_TYPES 一致） ——
_DIMENSION_TYPES = ("DIMENSION", "ARC_DIMENSION")


def _ensure_target_layer(doc: Drawing, layer: str = TARGET_LAYER) -> None:
    """确保目标图层存在；不存在则创建（默认色 7，§4.3）。"""
    if layer not in doc.layers:
        doc.layers.add(layer, color=7)


def _unique_block_name(doc: Drawing, handle: str) -> str:
    """生成唯一块名 `Dim_Reconstruct_{handle}`，防撞追加 `_1`/`_2`…（§4.4）。"""
    base = f"{BLOCK_NAME_PREFIX}{handle}"
    name = base
    n = 1
    while name in doc.blocks:
        name = f"{base}_{n}"
        n += 1
    return name


def _force_block_layer(blk: BlockLayout, layer: str = TARGET_LAYER) -> None:
    """强制块内图元归层（颜色/线型/线宽不动，§4.3 步 5）。

    块内图元原在尺寸层（非 0 层），不会继承外层 INSERT 图层，须逐图元设层；
    箭头是块内 INSERT，也设层，使其引用的 ByBlock/0 层图元继承新层。
    """
    for e in blk:
        e.dxf.layer = layer


def relayer_existing_blocks(doc: Drawing, layer: str = TARGET_LAYER) -> int:
    """幂等归层：把已存在的 `Dim_Reconstruct_*` INSERT 仅改图层（§4.5 确定性分支）。

    重跑时这些标注已是 INSERT 而非 DIMENSION，不会进入 `results`，故单独扫描
    模型空间：凡引用块名以 `Dim_Reconstruct_` 前缀开头的 INSERT，一律强制
    `insert.dxf.layer = layer`（不改块、不重组）。块内图元在建块时已归层，此处
    不重复（可选「块内图元同改」留待需要时再加）。返回归层的 INSERT 数。
    """
    msp = doc.modelspace()
    n = 0
    for e in msp:
        if e.dxftype() == "INSERT" and e.dxf.name.startswith(BLOCK_NAME_PREFIX):
            e.dxf.layer = layer
            n += 1
    return n


def convert_dimension_to_block(
    dim,
    doc: Drawing,
    msp,
    layer: str = TARGET_LAYER,
) -> Optional[BlockInfo]:
    """将单个 DIMENSION/ARC_DIMENSION 转成命名块 INSERT（方案 A）。

    返回转换结果的 `BlockInfo`；缺几何块（`get_geometry_block()` 为 None，即
    未渲染或几何组码 2 为空）时无法复用，返回 None 由上层记告警并跳过
    （不实现复杂易偏差的方案 B，见 §4.2）。
    """
    blk = dim.get_geometry_block()
    if blk is None:
        return None

    handle = dim.dxf.handle
    new_name = _unique_block_name(doc, handle)

    # 1. 复用重命名 *D 块 → 唯一命名块（rename_block 不更新引用，见模块头注释）。
    doc.blocks.rename_block(blk.name, new_name)
    blk = doc.blocks.get(new_name)

    # 2. 清匿名标志 70=1 → 0，转普通命名块（可编辑）。
    blk.block.dxf.flags = 0

    # 3. 建 INSERT：基点=块 base_point（通常 (0,0,0)），scale=1/rot=0 → 原位落点。
    base_point = blk.block.dxf.base_point
    msp.add_blockref(new_name, base_point, dxfattribs={"layer": layer})

    # 4. 逐图元归层（含箭头 INSERT）。
    _force_block_layer(blk, layer=layer)

    # 5. 删原 DIMENSION。
    msp.delete_entity(dim)

    return BlockInfo(
        name=new_name,
        created=True,
        layer=layer,
        converted_from="DIMENSION",
    )


def blockify(
    doc: Drawing,
    results: list[DimensionInfo],
    layer: str = TARGET_LAYER,
) -> list[str]:
    """对全部「未挂靠」尺寸执行块重组 + 归层（原地改 doc / results），返回告警列表。

    只处理 `unattached=True` 的尺寸（§4.3「对每个未挂靠 DIMENSION」）；
    挂靠尺寸保持原 DIMENSION 不动。缺几何块的尺寸跳过并记告警。转换结果写回
    `info.block`（供 JSON `block` 字段输出，§5.1）。
    """
    _ensure_target_layer(doc, layer=layer)
    msp = doc.modelspace()

    # 幂等：先归层「上次已转块」的 `Dim_Reconstruct_*` INSERT（§4.5），再转新块。
    relayer_existing_blocks(doc, layer=layer)

    # handle → 尺寸实体映射（一次遍历，转换前建好，避免删除后句柄失效）。
    by_handle: dict[str, object] = {
        e.dxf.handle: e
        for e in msp
        if e.dxftype() in _DIMENSION_TYPES
    }

    warnings: list[str] = []
    for info in results:
        if not info.unattached:
            continue
        dim = by_handle.get(info.handle)
        if dim is None:
            warnings.append(f"尺寸 {info.handle} 未找到对应实体，跳过块转换")
            continue
        try:
            blk_info = convert_dimension_to_block(dim, doc, msp, layer=layer)
        except Exception as exc:  # noqa: BLE001 —— 单尺寸失败不中断流水线
            warnings.append(f"尺寸 {info.handle} 块转换失败：{type(exc).__name__}: {exc}")
            continue
        if blk_info is None:
            warnings.append(f"尺寸 {info.handle} 缺几何块（*D），跳过块转换")
            continue
        info.block = blk_info

    return warnings


def clean_orphan_blocks(doc: Drawing) -> list[str]:
    """清理无任何引用的孤儿 `*D` 匿名块，返回删除的块名清单（§4.6）。

    引用来源两类（都收集进 `referenced` 集）：
        a) 任意布局（模型空间 + 各图纸空间）里 DIMENSION/ARC_DIMENSION 组码 2
           （`dxf.geometry`）与 INSERT 组码 2（`dxf.name`）；
        b) 任意块定义内部嵌套的 INSERT 组码 2（块套块）。
    仅删除「块名以 `*D` 前缀」且**不在**引用集的块，绝不触碰用户命名块；
    删除失败（被占用等）记入返回清单之外的静默跳过，不中断。
    """
    referenced: set[str] = set()

    def _scan(entities) -> None:
        for e in entities:
            t = e.dxftype()
            if t == "INSERT":
                referenced.add(e.dxf.name)
            elif t in _DIMENSION_TYPES:
                geo = e.dxf.get("geometry")
                if geo:
                    referenced.add(geo)

    # a) 所有布局（含模型空间与各图纸空间）。
    for layout in doc.layouts:
        _scan(layout)
    # b) 所有块定义内部（块套块的嵌套引用）。
    for block in doc.blocks:
        _scan(block)

    deleted: list[str] = []
    for block in list(doc.blocks):
        name = block.name
        if name.startswith("*D") and name not in referenced:
            try:
                doc.blocks.delete_block(name, safe=False)
            except Exception:  # noqa: BLE001 —— 单个块删除失败不中断
                continue
            deleted.append(name)
    return deleted


__all__ = [
    "convert_dimension_to_block",
    "blockify",
    "relayer_existing_blocks",
    "clean_orphan_blocks",
]
