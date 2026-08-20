# -*- coding: utf-8 -*-
"""T7.3 稳定性：内存无泄漏自测。

验收口径（requirements §稳定性 / ARCHITECTURE.md §9.2）：
    连续运行 72 小时无内存泄漏；提供 `--stress` 隐藏参数循环处理 + `tracemalloc`
    监控验证无泄漏（交付自测用）。

72 小时无法在单测里真实跑满，这里交付等价、可复现的信号：

    1. **稳态比较**（单测用）：先预热一次（排除 numpy/scipy/ezdxf 首次导入与
       cKDTree 冷启动），`gc.collect()` 后取基线；再循环 N 次处理同一图，每轮
       `gc.collect()` 后对比当前分配。无泄漏时当前分配应回到基线附近（增长趋 0）；
       有泄漏则随 N 线性增长，可稳定复现。阈值取保守裕量，只抓「单调无界增长」，
       不给 GC 抖动 / 首次缓存留误杀空间。

    2. **`--stress` 长循环**（CLI）：循环处理真实文件并输出当前/峰值内存，供
       72h 交付自测（可后台挂机跑数小时观察曲线是否爬升）。
"""
from __future__ import annotations

import gc
import tracemalloc
from dataclasses import dataclass
from pathlib import Path
from typing import Union

from app.core.pipeline import run_pipeline

# 稳态增长上限（bytes）：预热 + 循环 N 次后，当前分配较基线的增长不应超过此值。
# 取 4 MB 保守裕量——只拦「随迭代线性无界增长」的真泄漏，容忍 GC 碎片与缓存抖动。
STRESS_LEAK_THRESHOLD_BYTES = 4 * 1024 * 1024

# 单测默认循环次数：足够暴露线性泄漏，又不拖慢 CI。
DEFAULT_STRESS_ITERATIONS = 20


@dataclass
class StressSample:
    """一次循环压力测试的内存度量。"""

    iterations: int
    base_bytes: int        # 预热 + gc 后基线（当前分配）
    final_bytes: int       # N 次循环 + gc 后当前分配
    peak_bytes: int        # 期间峰值分配

    @property
    def growth_bytes(self) -> int:
        """循环前后当前分配的增量（无泄漏应 ≈ 0）。"""
        return self.final_bytes - self.base_bytes


@dataclass
class StressReport:
    """内存稳定性报告。"""

    sample: StressSample
    threshold_bytes: int = STRESS_LEAK_THRESHOLD_BYTES

    @property
    def passed(self) -> bool:
        return self.sample.growth_bytes <= self.threshold_bytes

    def render(self) -> str:
        """人类可读报告（GBK 安全，无 emoji）。"""
        s = self.sample
        lines = [
            "=" * 62,
            "未挂靠尺寸识别 —— T7.3 内存稳定性报告",
            "=" * 62,
            f"循环次数：{s.iterations}（预热 1 次后计时，每轮 gc.collect()）",
            "",
            f"  基线分配   {s.base_bytes / 1024:>10.1f} KB",
            f"  末轮分配   {s.final_bytes / 1024:>10.1f} KB",
            f"  峰值分配   {s.peak_bytes / 1024:>10.1f} KB",
            f"  增长       {s.growth_bytes / 1024:>10.1f} KB（阈值 {self.threshold_bytes / 1024 / 1024:.0f} MB）",
            "",
            f"  内存稳定性：{'[通过] 无泄漏' if self.passed else '[未通过] 存在泄漏'}"
            + ("（增长趋于 0）" if s.growth_bytes <= 0 else ""),
            "=" * 62,
        ]
        return "\n".join(lines)


def measure(path: Union[str, Path], iterations: int = DEFAULT_STRESS_ITERATIONS,
            warmup: int = 1) -> StressSample:
    """循环处理 `path` 共 `iterations` 次，用 tracemalloc 度量稳态增长。

    预热 `warmup` 次（导入 + cKDTree 冷启动 + ezdxf 缓存），`gc.collect()` 后取
    基线，再循环处理，每轮 `gc.collect()`；返回基线 / 末轮 / 峰值分配。
    """
    p = str(path)
    for _ in range(warmup):
        run_pipeline(p)
    gc.collect()

    tracemalloc.start()
    base = tracemalloc.get_traced_memory()[0]
    for _ in range(iterations):
        run_pipeline(p)
        gc.collect()
    final, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    return StressSample(
        iterations=iterations,
        base_bytes=base,
        final_bytes=final,
        peak_bytes=peak,
    )


def run_stress(path: Union[str, Path], iterations: int = DEFAULT_STRESS_ITERATIONS,
               warmup: int = 1) -> StressReport:
    """对 `path` 做内存稳定性测量，返回 StressReport。"""
    return StressReport(sample=measure(path, iterations, warmup))


__all__ = [
    "STRESS_LEAK_THRESHOLD_BYTES",
    "DEFAULT_STRESS_ITERATIONS",
    "StressSample",
    "StressReport",
    "measure",
    "run_stress",
]
