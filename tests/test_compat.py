# -*- coding: utf-8 -*-
"""T7.3 兼容性与稳定性单测。

覆盖三大验收点（requirements §兼容性 / §稳定性，ARCHITECTURE §6.2/§9.2）：
    1. 版本矩阵 —— AutoCAD 2007–2025 抽样 20 文件，加载 + 检测无崩溃、版本一致；
    2. 损坏文件 —— 任意损坏输入不抛未预期异常（友好 LoadError 或宽容解析），不崩溃；
    3. 内存稳定性 —— 循环处理稳态增长趋于 0（无泄漏）。

大图 / 真实文件的 72h 压测走 CLI `python -m app.compat --stress`（机器相关），
此处用确定性小图做自包含、可复现的有限次校验。
"""
from __future__ import annotations

import pytest

from app.compat.corrupt import CORRUPT_CASES, check_corrupt, run_corrupt
from app.compat.matrix import AUTOCAD_MATRIX, gen_matrix, run_matrix
from app.compat.stress import STRESS_LEAK_THRESHOLD_BYTES, run_stress
from app.core.loader import LoadError, load_dxf
from app.performance.bench import gen_small_drawing


# —— 版本矩阵 ——

def test_matrix_covers_autocad_2007_2025():
    """版本档完整覆盖 AutoCAD 2007（AC1021）→ 2024/2025（AC1036）。"""
    acadvers = {row[1] for row in AUTOCAD_MATRIX}
    assert acadvers == {"AC1021", "AC1024", "AC1027", "AC1032", "AC1035", "AC1036"}


def test_matrix_all_versions_load_and_detect(tmp_path):
    """抽样 20 文件（6 个版本档轮转）全部加载 + 检测成功、版本一致。"""
    report = run_matrix(tmp_path, n=20)
    assert report.n_files == 20
    assert len(report.checks) == 20
    assert report.passed
    for c in report.checks:
        assert c.ok, f"{c.file} 失败: {c.error}"
        assert c.dimension_count > 0
        assert c.entity_count >= c.dimension_count


def test_matrix_newer_versions_readable(tmp_path):
    """AC1035/AC1036（AutoCAD 2021/2024，ezdxf 只读不写）落盘后能正确回读解析。"""
    files = gen_matrix(tmp_path, n=6)  # 6 个版本各一份，含 AC1035/AC1036
    acadver_by_version = {row[0]: row[1] for row in AUTOCAD_MATRIX}
    for path, version, acadver, _autocad in files:
        loaded = load_dxf(path)
        assert loaded.doc.dxfversion == acadver_by_version[version]
        assert loaded.doc.dxfversion == acadver


# —— 损坏文件 ——

def test_corrupt_cases_no_crash(tmp_path):
    """全部损坏样本（7 类）均不崩溃：要么友好 LoadError，要么宽容解析/recover。"""
    report = run_corrupt(tmp_path)
    assert len(report.checks) == len(CORRUPT_CASES)
    assert report.passed
    for c in report.checks:
        assert c.outcome != "crashed", f"{c.name} 崩溃: {c.exception}: {c.message}"


def test_garbage_file_raises_friendly_load_error(tmp_path):
    """二进制垃圾必须抛友好 LoadError，而非裸 OSError（loader 修复回归点）。"""
    p = tmp_path / "garbage.dxf"
    p.write_bytes(bytes(range(256)) * 4)
    with pytest.raises(LoadError):
        load_dxf(p)


def test_empty_and_truncated_do_not_crash(tmp_path):
    """空文件 / 截断文件走 recover 宽容解析，不抛未预期异常（不崩溃）。"""
    empty = tmp_path / "empty.dxf"
    empty.write_bytes(b"")
    loaded = load_dxf(empty)  # 不抛异常即达标
    assert loaded.recovered is True
    assert loaded.entity_count == 0

    truncated = tmp_path / "trunc.dxf"
    truncated.write_bytes(b"0\nSECTION\n2\nENTITIES\n0\nLINE\n8\n0\n10\n0.0\n20\n")
    # 截断文件：要么宽容加载，要么友好 LoadError，绝不抛裸 OSError/AttributeError。
    check = check_corrupt(truncated, "截断的 ENTITIES")
    assert check.friendly


# —— 内存稳定性 ——

def test_stress_no_leak(tmp_path):
    """循环处理小图 20 次，稳态增长远低于阈值（无泄漏）。"""
    small = tmp_path / "small.dxf"
    gen_small_drawing(small)
    report = run_stress(small, iterations=20)

    assert report.sample.peak_bytes > 0          # tracemalloc 确实度量到分配
    assert report.sample.growth_bytes <= STRESS_LEAK_THRESHOLD_BYTES
    assert report.passed
