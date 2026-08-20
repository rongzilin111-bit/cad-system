# -*- coding: utf-8 -*-
"""T7.2 性能验收命令行入口。

用法：
    python -m app.performance [--small] [--large-file <path>] [--runs N] [--keep]

    - 默认生成一张确定性小图并计时（检测 + 端到端）；
    - `--large-file <path>` 对真实大图计时（检测 + 端到端），与 `--small` 可并存；
    - `--runs N` 小图计时运行次数（默认 5）；`--large-runs N` 大图（默认 3）；
    - `--keep` 保留生成的小图（默认计时后清理）；
    - 小图达标（检测 ≤1s）时退出码 0，否则退出码 1；大图仅参考，不判退出码。
"""
from __future__ import annotations

import argparse
import shutil
import sys
import tempfile
from pathlib import Path

from app.performance.bench import (
    SMALL_TIME_BUDGET_S,
    benchmark_large,
    benchmark_small,
)

DEFAULT_RUNS = 5
DEFAULT_LARGE_RUNS = 3


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="未挂靠尺寸识别 T7.2 性能验收")
    parser.add_argument("--small", action="store_true", default=True,
                        help="生成小图并计时（默认开启）")
    parser.add_argument("--large-file", type=str, default=None,
                        help="真实大图 DXF 路径（可选，计时检测 + 端到端）")
    parser.add_argument("--runs", type=int, default=DEFAULT_RUNS,
                        help="小图计时运行次数（默认 5）")
    parser.add_argument("--large-runs", type=int, default=DEFAULT_LARGE_RUNS,
                        help="大图计时运行次数（默认 3）")
    parser.add_argument("--keep", action="store_true",
                        help="保留生成的小图（默认计时后清理）")
    args = parser.parse_args(argv)

    # 小图：在临时目录生成，计时后（除非 --keep）清理。
    tmp = tempfile.mkdtemp(prefix="perf_small_")
    small_path = Path(tmp) / "small.dxf"
    report = benchmark_small(small_path, runs=args.runs)

    # 大图（可选）：直接测真实文件（一次 benchmark_large 同时产出检测 + 端到端）。
    if args.large_file:
        large = benchmark_large(args.large_file, runs=args.large_runs)
        report.large_pipeline = large.large_pipeline
        report.large_end_to_end = large.large_end_to_end

    print(report.render())

    if not args.keep:
        shutil.rmtree(str(tmp), ignore_errors=True)

    # 退出码只由「小图达标」决定；大图仅参考（需求未对大图设硬阈值）。
    return 0 if report.small_passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
