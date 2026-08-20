# -*- coding: utf-8 -*-
"""T7.4 代码质量命令行入口。

用法：
    python -m app.quality [--threshold 0.25]

    - 遍历 app/ 与 main.py 统计注释率与模块 docstring 覆盖率，出报告；
    - `--threshold` 覆盖注释率阈值（默认 0.25，即 25%）；
    - 整体达标（每文件 ≥ 阈值 且 模块 docstring 100%）退出码 0，否则 1。
"""
from __future__ import annotations

import argparse

from app.quality.comment_rate import COMMENT_RATE_THRESHOLD, analyze_tree


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="未挂靠尺寸识别 T7.4 代码质量（注释率）核查")
    parser.add_argument("--threshold", type=float, default=COMMENT_RATE_THRESHOLD,
                        help=f"注释率阈值（默认 {COMMENT_RATE_THRESHOLD}）")
    args = parser.parse_args(argv)

    report = analyze_tree()
    report.threshold = args.threshold
    print(report.render())
    return 0 if report.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
