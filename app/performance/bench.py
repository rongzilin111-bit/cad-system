# -*- coding: utf-8 -*-
"""T7.2 性能测试：计时实测「小图 ≤1s」与「大图合理耗时」。

验收口径（需求分析 §8 / requirements §2.1.2）：
    小图（≤200 几何实体）全流程检测耗时 ≤ 1 秒（测试环境 i7 / 16GB / SSD）；
    大图（约 1.2 万实体）不适用 ≤1s，只要求「合理」耗时 —— 依据
    ARCHITECTURE.md §9.1，瓶颈在 DXF 另存（~1M 行文本写盘 1–3s）。

「全流程检测」= `run_pipeline`（load → index → detect → bbox/值/公差 →
reconstruct → blockify），即需求所指的「检测」本身；另存 DXF / 写 JSON 属
M5 输出，与检测分开计时上报（小图两者都应远小于 1s）。

计时方法（确保公平、可复现）：
    1. `time.perf_counter` 高精度计时；
    2. 先预热一次 —— 排除 numpy / scipy 首次导入与 cKDTree 冷启动；
    3. 多次运行取**最小值** —— 剔除 OS 调度抖动，反映稳态耗时（阈值判定
       只对最小值生效，不给「偶尔一次慢」留误杀空间，也不让抖动掩盖真实
       性能退化）。
"""
from __future__ import annotations

import statistics
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Union

import ezdxf

from app.config import DETACH_TOLERANCE
from app.core.loader import load_dxf
from app.core.pipeline import output_dxf_path, run_pipeline
from app.gui.presentation import output_json_path
from app.io import dxf_export, json_export

# —— 验收阈值 ——
SMALL_ENTITY_BUDGET = 200     # 小图几何实体上限（需求 §2.1.2「≤200+ 几何实体」）
SMALL_TIME_BUDGET_S = 1.0     # 小图全流程检测 ≤ 1s（硬指标）
LARGE_ENTITY_FLOOR = 10_000   # 大图实体下限（约 1.2 万实体，判定「是大图」）
LARGE_TIME_BUDGET_S = 30.0    # 大图「合理」上限（含另存；保守裕量，实测远低于此）

# —— 小图生成参数（确定性，总实体 ≈ 188，几何 168，均在 200 以内）——
_N_LINES = 150
_N_CIRCLES = 10
_N_ARCS = 6
_N_DIMS = 20


@dataclass
class PerfSample:
    """一次计时的结果：一张图 + 一组（已预热后的）耗时样本。"""

    label: str
    entity_count: int = 0
    dimension_count: int = 0
    timings: list[float] = field(default_factory=list)   # 多次运行的 wall 秒

    @property
    def min(self) -> float:
        """最小时耗（阈值判定用，剔除调度抖动）。"""
        return min(self.timings) if self.timings else 0.0

    @property
    def median(self) -> float:
        """中位时耗（稳定性参考）。"""
        return statistics.median(self.timings) if self.timings else 0.0

    @property
    def mean(self) -> float:
        """平均时耗。"""
        return statistics.fmean(self.timings) if self.timings else 0.0


@dataclass
class PerfReport:
    """一次性能验收的完整报告。"""

    small_pipeline: Optional[PerfSample] = None    # 小图：检测（run_pipeline）
    small_end_to_end: Optional[PerfSample] = None  # 小图：检测 + 另存 DXF + JSON
    large_pipeline: Optional[PerfSample] = None    # 大图：检测
    large_end_to_end: Optional[PerfSample] = None  # 大图：检测 + 另存 DXF + JSON
    small_budget_s: float = SMALL_TIME_BUDGET_S
    large_budget_s: float = LARGE_TIME_BUDGET_S

    @property
    def small_passed(self) -> bool:
        """小图达标：检测 ≤ 1s 且端到端 ≤ 1s（端到端未测则不约束）。"""
        if self.small_pipeline is None or self.small_pipeline.min > self.small_budget_s:
            return False
        if self.small_end_to_end is not None and self.small_end_to_end.min > self.small_budget_s:
            return False
        return True

    @property
    def large_passed(self) -> bool:
        """大图「合理」：检测 ≤ 预算（未测大图则视为通过，不阻塞小图验收）。"""
        if self.large_pipeline is None:
            return True
        return self.large_pipeline.min <= self.large_budget_s

    def render(self) -> str:
        """人类可读报告（GBK 安全，无 emoji）。"""
        lines = [
            "=" * 60,
            "未挂靠尺寸识别 —— T7.2 性能验收报告",
            "=" * 60,
            f"小图阈值（检测 ≤ {self.small_budget_s:.0f}s；几何实体 ≤ {SMALL_ENTITY_BUDGET}）",
            f"大图阈值（检测 ≤ {self.large_budget_s:.0f}s，合理裕量）",
            "",
        ]

        def _row(s: Optional[PerfSample]) -> list[str]:
            if s is None:
                return []
            return [
                f"  {s.label}: 实体 {s.entity_count} / 尺寸 {s.dimension_count}",
                f"    最小时耗 {s.min * 1000:.1f} ms | 中位 {s.median * 1000:.1f} ms "
                f"| 平均 {s.mean * 1000:.1f} ms（{len(s.timings)} 次，已预热）",
            ]

        lines.append("—— 小图（程序化生成，确定性）——")
        for sample in (self.small_pipeline, self.small_end_to_end):
            lines.extend(_row(sample))
        lines.append("")
        lines.append("—— 大图（真实测试文件，若提供）——")
        for sample in (self.large_pipeline, self.large_end_to_end):
            lines.extend(_row(sample))
        lines.append("")

        verdicts = []
        verdicts.append(f"  小图：{'[通过] 达标' if self.small_passed else '[未通过] 未达标'}")
        if self.large_pipeline is not None:
            verdicts.append(f"  大图：{'[通过] 合理' if self.large_passed else '[未通过] 超预算'}")
        lines.extend(verdicts)
        lines.append("=" * 60)
        return "\n".join(lines)


# —— 确定性小图生成 ——

def _add_small_geometry(msp) -> None:
    """铺几何：网格线 + 圆 + 圆弧 + 折线 + 点（确定性，坐标间距固定）。"""
    for i in range(_N_LINES):
        x = (i % 15) * 12.0
        y = (i // 15) * 12.0
        msp.add_line((x, y), (x + 8.0, y + 3.0))
    for i in range(_N_CIRCLES):
        msp.add_circle((i * 20.0, 400.0), 3.0)
    for i in range(_N_ARCS):
        msp.add_arc((i * 20.0, 450.0), 4.0, 0.0, 90.0)
    msp.add_lwpolyline([(0.0, 500.0), (10.0, 500.0), (10.0, 510.0)])
    msp.add_point((20.0, 500.0))


def _add_small_dims(msp, n_dims: int) -> int:
    """加 n_dims 个标注（线性/对齐/半径/直径轮换，奇偶决定挂靠/未挂靠）。

    返回未挂靠数（供报告参考）。每个标注 render() 后再覆写定义点（否则
    loader 的 audit() 会删掉未渲染 DIMENSION —— 见 sample_gen 注释）。
    未挂靠的定义点整体平移 +500mm 到空旷区（远离一切几何 ≥300mm，超过
    snap_radius=50mm 与曲线网格 50mm 邻域），确保判定为未挂靠。
    """
    unattached = 0
    for i in range(n_dims):
        attached = (i % 2 == 0)
        x = 30.0 * i + 20.0
        if i % 4 == 0:
            obj = msp.add_linear_dim(base=(x, -10), p1=(x, 0), p2=(x + 10, 0))
        elif i % 4 == 1:
            obj = msp.add_aligned_dim(p1=(x, 0), p2=(x + 10, 0), distance=5)
        elif i % 4 == 2:
            obj = msp.add_radius_dim(center=(x + 20, 400), mpoint=(x + 23, 400))
        else:
            obj = msp.add_diameter_dim(center=(x + 20, 450), mpoint=(x + 23, 450))
        obj.render()
        if not attached:
            unattached += 1
            dim = obj.dimension
            for attr in ("defpoint", "defpoint2", "defpoint3", "defpoint4"):
                if hasattr(dim.dxf, attr):
                    p = getattr(dim.dxf, attr)
                    setattr(dim.dxf, attr, (p[0] + 500.0, p[1] + 500.0, p[2]))
    return unattached


def gen_small_drawing(path: Union[str, Path]) -> str:
    """生成一张确定性小图（总实体 ≈ 188，几何 168 ≤ 200），落盘返回路径。

    含多类几何 + 挂靠/未挂靠标注，使检测 + 转块全路径被触发，模拟真实小图。
    """
    doc = ezdxf.new("R2018")
    msp = doc.modelspace()
    _add_small_geometry(msp)
    _add_small_dims(msp, _N_DIMS)
    doc.saveas(str(path))
    return str(path)


# —— 计时器 ——

def _time(fn, runs: int, warmup: int) -> list[float]:
    """预热 warmup 次后跑 runs 次 fn()，返回每次 wall 秒。"""
    for _ in range(warmup):
        fn()
    out: list[float] = []
    for _ in range(runs):
        t0 = time.perf_counter()
        fn()
        out.append(time.perf_counter() - t0)
    return out


def _stats(path: str) -> tuple[int, int]:
    """读文件统计（实体数、尺寸数），供报告；不参与计时。"""
    loaded = load_dxf(path)
    return loaded.entity_count, loaded.dimension_count


def benchmark_small(path: Union[str, Path], runs: int = 5, warmup: int = 1) -> PerfReport:
    """生成小图并计时：检测（run_pipeline）与端到端（+另存 DXF+JSON）。"""
    path = gen_small_drawing(path)
    ent, dim = _stats(str(path))

    pipeline = PerfSample(
        label="小图·检测（run_pipeline）", entity_count=ent, dimension_count=dim,
        timings=_time(lambda: run_pipeline(str(path)), runs, warmup),
    )
    end_to_end = PerfSample(
        label="小图·端到端（检测+另存+JSON）", entity_count=ent, dimension_count=dim,
        timings=_time(lambda: _run_end_to_end(str(path)), runs, warmup),
    )
    return PerfReport(small_pipeline=pipeline, small_end_to_end=end_to_end)


def benchmark_large(path: Union[str, Path], runs: int = 3, warmup: int = 1) -> PerfReport:
    """对给定大图计时：检测与端到端（不生成，直接测真实文件）。"""
    ent, dim = _stats(str(path))

    pipeline = PerfSample(
        label="大图·检测（run_pipeline）", entity_count=ent, dimension_count=dim,
        timings=_time(lambda: run_pipeline(str(path)), runs, warmup),
    )
    end_to_end = PerfSample(
        label="大图·端到端（检测+另存+JSON）", entity_count=ent, dimension_count=dim,
        timings=_time(lambda: _run_end_to_end(str(path)), runs, warmup),
    )
    return PerfReport(large_pipeline=pipeline, large_end_to_end=end_to_end)


def _run_end_to_end(path: str) -> None:
    """检测 + 另存 DXF + 写 JSON（对齐 GUI worker 的全流程，不改图只计时）。"""
    out = run_pipeline(path, tolerance=DETACH_TOLERANCE)
    dxf_export.save_document(out.doc, output_dxf_path(path))
    json_export.dump(out.result, output_json_path(path))


__all__ = [
    "SMALL_ENTITY_BUDGET",
    "SMALL_TIME_BUDGET_S",
    "LARGE_ENTITY_FLOOR",
    "LARGE_TIME_BUDGET_S",
    "PerfSample",
    "PerfReport",
    "gen_small_drawing",
    "benchmark_small",
    "benchmark_large",
]
