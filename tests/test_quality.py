# -*- coding: utf-8 -*-
"""T7.4 代码质量单测：注释率 ≥25% + 模块 docstring 覆盖（脚本核查）。

验收口径（requirements §代码质量 / plan.md T7.4）：
    注释率 ≥25%，关键算法附原理说明；人工 / 脚本核查达标。

本单测直接调用 `app.quality.comment_rate.analyze_tree` 对当前源码树做自检，
锁定「整体注释率 ≥25%、每文件 ≥25%、模块 docstring 100% 覆盖」三条不变量，
防止后续提交悄悄稀释注释。
"""
from __future__ import annotations

from app.quality.comment_rate import COMMENT_RATE_THRESHOLD, analyze_tree


def test_overall_comment_rate_above_threshold():
    """整体注释率（注释行 / 非空总行）≥ 25%。"""
    report = analyze_tree()
    assert report.total_lines > 0
    assert report.overall_rate >= COMMENT_RATE_THRESHOLD


def test_every_file_above_threshold():
    """每个源文件注释率都 ≥ 25%（不接受个别文件拖低整体）。"""
    report = analyze_tree()
    assert len(report.metrics) > 0
    for m in report.metrics:
        assert m.rate >= COMMENT_RATE_THRESHOLD, f"{m.path} 注释率 {m.rate:.1%} 低于阈值"


def test_every_module_has_docstring():
    """每个模块都有模块级 docstring（关键算法附原理说明的核查）。"""
    report = analyze_tree()
    assert report.all_have_docstring
    for m in report.metrics:
        assert m.has_module_docstring, f"{m.path} 缺模块 docstring"


def test_report_passed():
    """整体 `passed` 判定为真（三条不变量全部满足）。"""
    assert analyze_tree().passed
