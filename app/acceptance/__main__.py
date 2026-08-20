# -*- coding: utf-8 -*-
"""T7.1 自动化验收脚本入口。

用法：`python -m app.acceptance [--n 50] [--out-dir <dir>] [--keep]`
    - 在 `<out-dir>`（默认 `build/acceptance`）生成样本集 + manifest.json；
    - 逐样本跑 pipeline 比对真值；
    - 打印验收报告；`--keep` 保留样本目录，否则结束后清理；
    - 直通率 ≥ 99% 且误报率 ≤ 1% 时退出码 0，否则退出码 1。
"""
from __future__ import annotations

import argparse
import shutil
import sys
import tempfile
from pathlib import Path

from app.acceptance.evaluate import run_acceptance
from app.acceptance.sample_gen import generate_sample_set

DEFAULT_OUT_DIR = Path("build") / "acceptance"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="未挂靠尺寸识别 T7.1 自动化验收")
    parser.add_argument("--n", type=int, default=50, help="样本（图纸）数量（默认 50）")
    parser.add_argument("--out-dir", type=str, default=str(DEFAULT_OUT_DIR),
                        help="样本集输出目录（默认 build/acceptance）")
    parser.add_argument("--keep", action="store_true", help="保留样本目录（默认验收后清理）")
    args = parser.parse_args(argv)

    if args.keep:
        out_dir = Path(args.out_dir)
        manifest = generate_sample_set(out_dir, n=args.n)
        manifest_path = out_dir / "manifest.json"
    else:
        tmp = tempfile.mkdtemp(prefix="acceptance_")
        generate_sample_set(tmp, n=args.n)
        manifest_path = Path(tmp) / "manifest.json"
        out_dir = Path(tmp)

    report = run_acceptance(manifest_path)
    print(report.render())

    if not args.keep:
        shutil.rmtree(str(tmp), ignore_errors=True)

    return 0 if report.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
