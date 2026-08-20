# -*- coding: utf-8 -*-
"""T7.1 自动化验收单测：样本集生成 + 实际 vs 预期比对 + 指标达标。

验收口径（需求分析 §8）：≥50 样本、直通率 ≥99%、误报率 ≤1%。
样本真值由 `sample_gen` 程序化确定（挂靠点最近距离≈0、未挂靠点≫0.01mm、
另有 0.005/0.02mm 阈值边界样本），故可严格验证判定正确性与二分类指标。
"""
from __future__ import annotations

import json
from pathlib import Path

from app.acceptance.evaluate import (
    ACCURACY_THRESHOLD,
    FPR_THRESHOLD,
    Metrics,
    evaluate_sample,
    run_acceptance,
)
from app.acceptance.sample_gen import ALL_TYPES, generate_sample_set
from app.core.pipeline import run_pipeline


def _per_drawing_cases() -> int:
    """每张图纸的标注数 = 8 类 × 2（挂靠/未挂靠）+ 2 个阈值边界样本 = 18。"""
    return len(ALL_TYPES) * 2 + 2


# —— 指标运算 ——
def test_metrics_properties():
    m = Metrics(total=10, tp=3, tn=6, fp=0, fn=1)
    assert m.accuracy == 0.9          # (3+6)/10
    assert m.fpr == 0.0               # 0/(0+6)
    assert m.fnr == 0.25              # 1/(1+3)

    m2 = Metrics(total=100, tp=50, tn=49, fp=1, fn=0)
    assert m2.fpr == 1 / 50           # 1/(1+49)
    assert m2.accuracy == 0.99


def test_metrics_empty_denominator():
    assert Metrics().accuracy == 0.0
    assert Metrics().fpr == 0.0
    assert Metrics().fnr == 0.0


# —— 单个样本：生成即真值一致、handle 跨 save/reload 稳定 ——
def test_generate_sample_handles_match_pipeline(tmp_path):
    from app.acceptance.sample_gen import generate_sample

    cases = generate_sample(tmp_path / "s.dxf", index=0, dx=0.0, dy=0.0)
    assert len(cases) == _per_drawing_cases()

    out = run_pipeline(str(tmp_path / "s.dxf"), do_blockify=False)
    actual = {d.handle: d.unattached for d in out.result.dimensions}
    # 每个真值 handle 都能在结果里找到（句柄 save/reload 稳定）
    assert all(c.handle in actual for c in cases)


# —— 全量验收：50 样本、直通率 ≥99%、误报率 ≤1% ——
def test_acceptance_meets_thresholds(tmp_path):
    manifest = generate_sample_set(tmp_path, n=50)
    report = run_acceptance(tmp_path / "manifest.json")

    assert report.sample_count == 50
    assert report.metrics.total == 50 * _per_drawing_cases()
    assert report.metrics.fp == 0
    assert report.metrics.fn == 0
    assert report.metrics.missing == 0
    assert report.metrics.accuracy >= ACCURACY_THRESHOLD
    assert report.metrics.fpr <= FPR_THRESHOLD
    assert report.passed is True

    # manifest 结构自检
    assert manifest["n_drawings"] == 50
    assert len(manifest["samples"]) == 50
    assert all(len(s["cases"]) == _per_drawing_cases() for s in manifest["samples"])


# —— 阈值边界：0.005mm 挂靠、0.02mm 未挂靠 ——
def test_boundary_samples_classified_correctly(tmp_path):
    from app.acceptance.sample_gen import generate_sample

    cases = generate_sample(tmp_path / "b.dxf", index=1, dx=500.0, dy=0.0)
    boundary = [c for c in cases if c.type.startswith("linear::boundary")]
    assert len(boundary) == 2

    out = run_pipeline(str(tmp_path / "b.dxf"), do_blockify=False)
    actual = {d.handle: d.unattached for d in out.result.dimensions}
    near = next(c for c in boundary if c.type.endswith("near"))
    far = next(c for c in boundary if c.type.endswith("far"))
    assert actual[near.handle] is False    # 0.005mm → 挂靠
    assert actual[far.handle] is True      # 0.02mm → 未挂靠
