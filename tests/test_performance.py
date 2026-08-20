# -*- coding: utf-8 -*-
"""T7.2 性能测试单测：小图 ≤1s 计时实测 + 生成器自检 + 报告口径。

验收口径（需求分析 §8 / requirements §2.1.2）：
    单图纸（≤200 几何实体）全流程检测耗时 ≤ 1 秒（i7 / 16GB / SSD）。
本单测只覆盖**小图**（确定性生成、自包含、可 CI 复现）；大图（1.2 万实体）
针对真实测试文件、耗时随机器波动，故走 CLI `python -m app.performance
--large-file <path>` 手动实测，不在此硬编码绝对路径断言。
"""
from __future__ import annotations

from app.config import DETACH_TOLERANCE
from app.core.loader import load_dxf
from app.core.pipeline import run_pipeline
from app.performance.bench import (
    SMALL_ENTITY_BUDGET,
    SMALL_TIME_BUDGET_S,
    PerfReport,
    PerfSample,
    benchmark_small,
    gen_small_drawing,
)


# —— 生成器自检：确为「小图」，且含挂靠 + 未挂靠标注（检测 + 转块全路径被触发） ——
def test_small_drawing_entity_count_within_budget(tmp_path):
    path = gen_small_drawing(tmp_path / "small.dxf")
    loaded = load_dxf(path)

    assert loaded.entity_count <= SMALL_ENTITY_BUDGET
    assert loaded.geometry_count <= SMALL_ENTITY_BUDGET   # 需求口径「≤200 几何实体」
    assert loaded.dimension_count > 0                     # 含标注，非空跑
    assert loaded.dimension_count % 2 == 0                # 挂靠/未挂靠各半（轮换）


def test_small_drawing_exercises_detection_and_blockify(tmp_path):
    """生成的标注里既有挂靠又有未挂靠，保证判定与转块两条路径都被计时覆盖。"""
    path = gen_small_drawing(tmp_path / "small.dxf")
    out = run_pipeline(path, tolerance=DETACH_TOLERANCE)

    assert out.result.total_dimensions > 0
    assert 0 < out.result.unattached_count < out.result.total_dimensions  # 两类都有


# —— 报告口径：最小/中位/平均与达标判定 ——
def test_perf_sample_statistics():
    s = PerfSample(label="x", timings=[0.3, 0.5, 0.7])
    assert s.min == 0.3
    assert s.median == 0.5
    assert s.mean == 0.5

    assert PerfSample(label="empty").min == 0.0
    assert PerfSample(label="empty").median == 0.0
    assert PerfSample(label="empty").mean == 0.0


def test_perf_report_small_passed_logic():
    ok = PerfReport(small_pipeline=PerfSample(label="a", timings=[0.5]))
    assert ok.small_passed is True

    slow = PerfReport(small_pipeline=PerfSample(label="a", timings=[1.5]))
    assert slow.small_passed is False

    no_measure = PerfReport()
    assert no_measure.small_passed is False   # 未测小图不可判达标

    # 端到端超预算同样判不达标
    e2e_slow = PerfReport(
        small_pipeline=PerfSample(label="a", timings=[0.5]),
        small_end_to_end=PerfSample(label="b", timings=[1.5]),
    )
    assert e2e_slow.small_passed is False


# —— 核心验收：小图全流程检测 ≤ 1s（取多次最小值，剔除调度抖动） ——
def test_small_pipeline_within_budget(tmp_path):
    report = benchmark_small(tmp_path / "small.dxf", runs=3)

    assert report.small_pipeline is not None
    assert report.small_pipeline.min <= SMALL_TIME_BUDGET_S
    assert report.small_passed is True


def test_small_end_to_end_within_budget(tmp_path):
    """端到端（检测 + 另存 DXF + JSON）对 188 实体小图同样远小于 1s。"""
    report = benchmark_small(tmp_path / "small.dxf", runs=3)

    assert report.small_end_to_end is not None
    assert report.small_end_to_end.min <= SMALL_TIME_BUDGET_S
    assert report.small_passed is True
