# -*- coding: utf-8 -*-
"""GUI 纯展示层（无 Qt 依赖）：格式化、表格行构建、详情渲染、运行配置。

把「数据 → 界面字符串」的转换从 Qt 组件里抽出成纯函数，好处有二：
    1. 结果表格 / 详情面板 / 汇总栏的展示口径集中一处，改一处即全改；
    2. 不依赖 PySide6，可被 pytest 直接单测（本机未装 PySide6 时仍能验证）。

Qt 层（worker.py / result_view.py / main_window.py）只负责「控件 + 信号槽」，
展示字符串一律调用本模块的函数，不自行拼格式。
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Union

from app.config import DETACH_TOLERANCE, SNAP_RADIUS, TARGET_LAYER
from app.models import (
    BBox,
    DimensionInfo,
    MeasurementPoint,
    Result,
    Tolerance,
)

# —— 尺寸类型 → 中文显示名（与 defpoints.DIM_TYPE_NAMES 对应） ——
TYPE_LABELS: dict[str, str] = {
    "linear": "线性",
    "aligned": "对齐",
    "angular": "角度",
    "diameter": "直径",
    "radius": "半径",
    "angular_3p": "三点角度",
    "ordinate": "坐标",
    "arc": "弧长",
}

# —— 结果表格列（顺序即列序）。detach_distance 为脱钩距、block 为块名 ——
SUMMARY_COLUMNS = ("handle", "type", "value", "tolerance", "detach_distance", "block")
SUMMARY_HEADERS = ("句柄", "类型", "尺寸值", "公差", "脱钩距(mm)", "块")


def type_label(type_name: str) -> str:
    """尺寸类型名 → 中文显示名；未知码原样返回（如 unknown_9）。"""
    return TYPE_LABELS.get(type_name, type_name)


@dataclass
class WorkerConfig:
    """一次后台处理的输入配置（GUI 参数 → pipeline 参数）。"""

    path: str
    tolerance: float = DETACH_TOLERANCE
    snap_radius: float = SNAP_RADIUS
    expand_insert: bool = False
    layer: str = TARGET_LAYER
    do_blockify: bool = True
    clean_orphan: bool = False


@dataclass
class RunReport:
    """一次处理完成后的轻量报告（不携带 ezdxf doc，避免跨线程搬运大对象）。"""

    result: Result
    dxf_path: str = ""
    json_path: str = ""
    elapsed_sec: float = 0.0


def output_json_path(path: Union[str, Path]) -> str:
    """由输入路径派生 JSON 结果路径：`{原名}_result.json`（与 DXF 另存并列）。"""
    p = Path(path)
    return str(p.with_name(p.stem + "_result.json"))


def _g(value: Optional[float]) -> str:
    """数值 → 最短可读串；None → 占位符（`g` 格式：28.0→"28"、28.5→"28.5"）。"""
    return "—" if value is None else f"{value:g}"


def format_value(value: Optional[float]) -> str:
    """尺寸名义值展示。"""
    return _g(value)


def format_tolerance(tol: Optional[Tolerance]) -> str:
    """公差 → 人类可读串（§5.3 模式语义）。

    symmetrical → ``±0.1``；deviation → ``+0.1/-0.2``；limits → ``27.8~28.1``；
    basic → ``□``；none / None → ``—``。
    """
    if tol is None or tol.mode == "none":
        return "—"
    if tol.mode == "symmetrical":
        return f"±{_g(tol.upper)}"
    if tol.mode == "deviation":
        return f"{tol.upper:+g}/{tol.lower:+g}" if tol.upper is not None else tol.raw
    if tol.mode == "limits":
        return f"{_g(tol.lower)}~{_g(tol.upper)}"
    if tol.mode == "basic":
        return "□"
    return tol.raw or "—"


def format_bbox(bbox: Optional[BBox]) -> str:
    """外接矩 → `(minx, miny)–(maxx, maxy)`。"""
    if bbox is None:
        return "—"
    return f"({_g(bbox.minx)}, {_g(bbox.miny)})–({_g(bbox.maxx)}, {_g(bbox.maxy)})"


def format_distance(info: DimensionInfo) -> str:
    """脱钩距展示：未挂靠显示 4 位小数（0.01mm 阈值量级），挂靠显示占位。"""
    return f"{info.detach_distance:.4f}" if info.unattached else "—"


def format_point(mp: MeasurementPoint) -> str:
    """单个测量点 → 一行说明（原始坐标 / 脱钩 / 纠偏 / 最近实体 / 置信）。"""
    base = f"组码{mp.group_code} ({_g(mp.x)}, {_g(mp.y)})"
    if mp.detached:
        base += " · 脱钩"
        if mp.corrected and mp.corrected_x is not None and mp.corrected_y is not None:
            base += f" → 纠偏({_g(mp.corrected_x)}, {_g(mp.corrected_y)})"
        if mp.unresolved:
            base += " [未纠偏]"
    if mp.distance is not None:
        base += f" · 距{mp.distance:.4f}mm"
    if mp.nearest_entity:
        base += f" · 近{mp.nearest_entity}"
    if mp.confidence < 1.0:
        base += " [低置信]"
    return base


def build_summary_rows(result: Result) -> list[dict]:
    """把 Result 摊平成结果表格行（每行一个 dict）。

    优先用 `result.dimensions`（pipeline 保证其为**全部**尺寸，含挂靠），空时
    回退 `result.summary`。每行返回列显示串 + `unattached`（高亮）与
    `detach_distance_raw`（排序）两个辅助键。
    """
    rows: list[dict] = []
    if result.dimensions:
        for d in result.dimensions:
            rows.append(
                {
                    "handle": d.handle,
                    "type": type_label(d.type),
                    "value": format_value(d.value),
                    "tolerance": format_tolerance(d.tolerance),
                    "detach_distance": format_distance(d),
                    "block": d.block.name if d.block else "",
                    "unattached": d.unattached,
                    "detach_distance_raw": d.detach_distance,
                }
            )
        return rows

    for s in result.summary:
        rows.append(
            {
                "handle": s.handle,
                "type": type_label(s.type),
                "value": format_value(s.value),
                "tolerance": "—",
                "detach_distance": "—",
                "block": "",
                "unattached": s.unattached,
                "detach_distance_raw": 0.0,
            }
        )
    return rows


def render_detail(dim: DimensionInfo) -> str:
    """单个尺寸的详情面板文本（纯文本多行，Qt 面板用 setPlainText 直显）。"""
    lines = [
        f"句柄: {dim.handle}",
        f"类型: {type_label(dim.type)}（组码 {dim.dxf_type_code}）",
        f"图层: {dim.layer or '—'}",
        f"标注样式: {dim.dimstyle or '—'}",
        f"尺寸值: {format_value(dim.value)}",
        f"文字: {dim.text or '—'}",
        f"公差: {format_tolerance(dim.tolerance)}",
        f"外接矩: {format_bbox(dim.bbox)}",
        f"未挂靠: {'是' if dim.unattached else '否'}"
        + (f"（脱钩距 {dim.detach_distance:.4f}mm）" if dim.unattached else ""),
    ]
    if dim.block is not None:
        lines.append(
            f"块: {dim.block.name}（图层 {dim.block.layer}，来源 {dim.block.converted_from}）"
        )
    lines.append("测量点位:")
    if dim.points:
        for role, mp in dim.points.items():
            lines.append(f"  {role}: {format_point(mp)}")
    else:
        lines.append("  （无）")
    return "\n".join(lines)


__all__ = [
    "TYPE_LABELS",
    "SUMMARY_COLUMNS",
    "SUMMARY_HEADERS",
    "WorkerConfig",
    "RunReport",
    "type_label",
    "output_json_path",
    "format_value",
    "format_tolerance",
    "format_bbox",
    "format_distance",
    "format_point",
    "build_summary_rows",
    "render_detail",
]
