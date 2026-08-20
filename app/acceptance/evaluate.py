# -*- coding: utf-8 -*-
"""T7.1 比对评估：实际输出 vs 预期结果，计算直通率 / 误报率 / 漏报率。

指标口径（与需求分析 §8 对齐，均为「逐标注」二分类统计）：
    直通率（准确率，First-Pass Accuracy）= (TP + TN) / N
        即「判定正确的标注」占「全部标注」的比例，验收要求 ≥ 99%。
    误报率（False Positive Rate）= FP / (FP + TN)
        即「实际挂靠却被误判为未挂靠」占「实际挂靠」的比例，要求 ≤ 1%。
    漏报率（False Negative Rate）= FN / (FN + TP)
        「实际未挂靠却被漏判」占比，仅作附加参考（需求未设硬阈值）。

判定四类：
    TP = 预期未挂靠 ∧ 实际未挂靠；TN = 预期挂靠 ∧ 实际挂靠；
    FP = 预期挂靠 ∧ 实际未挂靠（误报）；FN = 预期未挂靠 ∧ 实际挂靠（漏报）。
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from app.config import DETACH_TOLERANCE
from app.core.pipeline import run_pipeline

# —— 验收阈值（需求分析 §8）——
ACCURACY_THRESHOLD = 0.99   # 直通率 ≥ 99%
FPR_THRESHOLD = 0.01        # 误报率 ≤ 1%


@dataclass
class Metrics:
    """二分类混淆矩阵 + 派生指标。"""
    total: int = 0
    tp: int = 0
    tn: int = 0
    fp: int = 0
    fn: int = 0
    missing: int = 0          # 真值 handle 在结果中缺失（视为错误）

    @property
    def accuracy(self) -> float:
        """直通率 = (TP+TN)/N。"""
        return (self.tp + self.tn) / self.total if self.total else 0.0

    @property
    def fpr(self) -> float:
        """误报率 = FP / (FP+TN)（实际挂靠中误判占比）。"""
        denom = self.fp + self.tn
        return self.fp / denom if denom else 0.0

    @property
    def fnr(self) -> float:
        """漏报率 = FN / (FN+TP)（实际未挂靠中漏判占比）。"""
        denom = self.fn + self.tp
        return self.fn / denom if denom else 0.0


@dataclass
class AcceptanceReport:
    """一次验收的完整报告。"""
    sample_count: int = 0
    metrics: Metrics = field(default_factory=Metrics)
    mismatches: list[dict] = field(default_factory=list)  # (file, handle, type, expected, actual)
    tolerance: float = DETACH_TOLERANCE

    @property
    def passed(self) -> bool:
        """直通率 ≥ 99% 且误报率 ≤ 1%（漏报率仅参考，不判达标）。"""
        return self.metrics.accuracy >= ACCURACY_THRESHOLD and self.metrics.fpr <= FPR_THRESHOLD

    def render(self) -> str:
        m = self.metrics
        lines = [
            "=" * 60,
            "未挂靠尺寸识别 —— T7.1 自动化验收报告",
            "=" * 60,
            f"样本（图纸）数     : {self.sample_count}",
            f"标注样本总数       : {m.total}",
            f"判定阈值           : {self.tolerance} mm",
            "",
            "—— 混淆矩阵 ——",
            f"  真阳性 TP（未挂靠→未挂靠）: {m.tp}",
            f"  真阴性 TN（挂靠→挂靠）    : {m.tn}",
            f"  假阳性 FP（挂靠→未挂靠，误报）: {m.fp}",
            f"  假阴性 FN（未挂靠→挂靠，漏报）: {m.fn}",
            f"  真值缺失（handle 无结果）   : {m.missing}",
            "",
            "—— 指标 ——",
            f"  直通率（准确率）  : {m.accuracy:.4%}  （要求 ≥ {ACCURACY_THRESHOLD:.0%}）",
            f"  误报率            : {m.fpr:.4%}  （要求 ≤ {FPR_THRESHOLD:.0%}）",
            f"  漏报率（参考）    : {m.fnr:.4%}",
            "",
            f"结论：{'[通过] 达标' if self.passed else '[未通过] 未达标'}",
        ]
        if self.mismatches:
            lines.append("")
            lines.append(f"—— 误判明细（{len(self.mismatches)} 处）——")
            for mm in self.mismatches[:20]:
                lines.append(
                    f"  {mm['file']} {mm['handle']} {mm['type']}: "
                    f"预期{'未挂靠' if mm['expected'] else '挂靠'} → "
                    f"实际{'未挂靠' if mm['actual'] else '挂靠'}"
                )
            if len(self.mismatches) > 20:
                lines.append(f"  …（其余 {len(self.mismatches) - 20} 处省略）")
        lines.append("=" * 60)
        return "\n".join(lines)


def _actual_map(result) -> dict[str, bool]:
    """Result → {handle: unattached}。"""
    return {d.handle: d.unattached for d in result.dimensions}


def evaluate_sample(sample_dir: Path, sample: dict, tolerance: float) -> tuple[Metrics, list[dict]]:
    """跑单个样本图纸，返回 (该样本 Metrics, 误判明细)。"""
    file_path = sample_dir / sample["file"]
    out = run_pipeline(str(file_path), tolerance=tolerance, do_blockify=False)
    actual = _actual_map(out.result)

    metrics = Metrics(total=len(sample["cases"]))
    mismatches: list[dict] = []
    for case in sample["cases"]:
        expected = bool(case["expected_unattached"])
        handle = case["handle"]
        got = actual.get(handle)
        if got is None:
            metrics.missing += 1
            mismatches.append({"file": sample["file"], "handle": handle,
                               "type": case["type"], "expected": expected, "actual": None})
            continue
        if expected and got:
            metrics.tp += 1
        elif not expected and not got:
            metrics.tn += 1
        elif not expected and got:
            metrics.fp += 1
            mismatches.append({"file": sample["file"], "handle": handle,
                               "type": case["type"], "expected": expected, "actual": got})
        else:  # expected and not got
            metrics.fn += 1
            mismatches.append({"file": sample["file"], "handle": handle,
                               "type": case["type"], "expected": expected, "actual": got})
    return metrics, mismatches


def run_acceptance(manifest_path, tolerance: float = DETACH_TOLERANCE) -> AcceptanceReport:
    """加载 manifest，逐样本跑 pipeline 比对真值，汇总成报告。

    `manifest_path`：`generate_sample_set` 产出的 manifest.json 路径；
    样本 DXF 与其同目录。`tolerance` 与真值生成口径一致（默认 0.01）。
    """
    manifest_path = Path(manifest_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    sample_dir = manifest_path.parent

    report = AcceptanceReport(sample_count=len(manifest["samples"]), tolerance=tolerance)
    for sample in manifest["samples"]:
        m, mismatches = evaluate_sample(sample_dir, sample, tolerance)
        report.metrics.total += m.total
        report.metrics.tp += m.tp
        report.metrics.tn += m.tn
        report.metrics.fp += m.fp
        report.metrics.fn += m.fn
        report.metrics.missing += m.missing
        report.mismatches.extend(mismatches)
    return report


__all__ = [
    "ACCURACY_THRESHOLD",
    "FPR_THRESHOLD",
    "Metrics",
    "AcceptanceReport",
    "evaluate_sample",
    "run_acceptance",
]
