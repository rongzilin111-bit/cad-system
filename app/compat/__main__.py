# -*- coding: utf-8 -*-
"""T7.3 兼容性与稳定性命令行入口。

用法：
    python -m app.compat [--matrix-only] [--corrupt-only] [--stress-only]
                         [--stress-file <path>] [--stress-iters N] [--n-files N]
                         [--keep]

    - 默认三项全跑：版本矩阵（抽样 20 文件，AutoCAD 2007–2025）+ 损坏文件
      友好提示 + 内存稳定性（有限次循环，稳态比较）；
    - `--stress-file <path>` 对指定真实文件做内存压力（默认用程序化生成的小图）；
    - `--stress-iters N` 压力循环次数（默认 20）；`--n-files N` 矩阵抽样数（默认 20）；
    - `--keep` 保留生成的样本文件（默认清理）；
    - 三项全部达标退出码 0，否则 1。

隐藏参数 `--stress`（对齐 ARCHITECTURE §9.2）：即 `--stress-only --stress-file
<真实文件> --stress-iters N`，供 72h 交付自测循环观察内存曲线。
"""
from __future__ import annotations

import argparse
import shutil
import sys
import tempfile
from pathlib import Path

from app.compat.corrupt import run_corrupt
from app.compat.matrix import MATRIX_SAMPLE_N, run_matrix
from app.compat.stress import DEFAULT_STRESS_ITERATIONS, run_stress
from app.performance.bench import gen_small_drawing


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="未挂靠尺寸识别 T7.3 兼容性与稳定性验收")
    parser.add_argument("--matrix-only", action="store_true", help="仅跑版本矩阵")
    parser.add_argument("--corrupt-only", action="store_true", help="仅跑损坏文件")
    parser.add_argument("--stress-only", action="store_true", help="仅跑内存稳定性")
    parser.add_argument("--stress", action="store_true", help="隐藏：压力自测（= stress-only）")
    parser.add_argument("--stress-file", type=str, default=None, help="内存压力目标文件（默认小图）")
    parser.add_argument("--stress-iters", type=int, default=DEFAULT_STRESS_ITERATIONS,
                        help=f"压力循环次数（默认 {DEFAULT_STRESS_ITERATIONS}）")
    parser.add_argument("--n-files", type=int, default=MATRIX_SAMPLE_N,
                        help=f"版本矩阵抽样文件数（默认 {MATRIX_SAMPLE_N}）")
    parser.add_argument("--keep", action="store_true", help="保留生成的样本文件")
    args = parser.parse_args(argv)

    # 决定跑哪些项：`--stress` 等价 `--stress-only`；否则默认三项全跑。
    only = any((args.matrix_only, args.corrupt_only, args.stress_only, args.stress))
    run_all = not only

    tmp = Path(tempfile.mkdtemp(prefix="compat_"))
    results: list[tuple[str, bool]] = []

    if run_all or args.matrix_only:
        report = run_matrix(tmp, n=args.n_files)
        print(report.render())
        results.append(("版本矩阵", report.passed))

    if run_all or args.corrupt_only:
        report = run_corrupt(tmp)
        print(report.render())
        results.append(("损坏文件", report.passed))

    if run_all or args.stress_only or args.stress:
        target = args.stress_file or gen_small_drawing(tmp / "stress_small.dxf")
        report = run_stress(target, iterations=args.stress_iters)
        print(report.render())
        results.append(("内存稳定性", report.passed))

    if not args.keep:
        shutil.rmtree(str(tmp), ignore_errors=True)

    if not results:
        print("未选择任何验收项（无任务）。")
        return 1

    all_pass = all(ok for _, ok in results)
    verdicts = "；".join(f"{name}:{'[通过]' if ok else '[未通过]'}" for name, ok in results)
    print("=" * 62)
    print(f"T7.3 综合：{verdicts}")
    print(f"退出码 {'0' if all_pass else '1'}（{'+'.join(n for n, _ in results)}）")
    print("=" * 62)
    return 0 if all_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
