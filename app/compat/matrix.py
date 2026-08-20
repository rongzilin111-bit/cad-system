# -*- coding: utf-8 -*-
"""T7.3 兼容性：AutoCAD 2007–2025 版本矩阵（抽样 20 文件）。

验收口径（requirements §兼容性 / 需求分析 §9）：
    成功加载并解析 AutoCAD 2007–2025 生成的 .dxf/.dwg 文件，抽样测试 20 个
    不同版本文件，无崩溃。（本项目为 DXF 处理，DWG 由上游 CAD 导出为 DXF 交付，
    见 需求分析 §9；ezdxf 不解析 DWG。）

版本覆盖：AutoCAD 2007–2025 期间，DXF 版本号随大版本升级共 6 档：
    R2007(AC1021)=AutoCAD 2007、R2010(AC1024)=2010、R2013(AC1027)=2013、
    R2018(AC1032)=2018、AC1035=AutoCAD 2021、AC1036=AutoCAD 2024/2025。
ezdxf 1.4.4 的 **写**上限是 R2018(AC1032)，AC1035/AC1036 只能**读**；因 R2018
之后实体模型未变、仅 `$ACADVER` 版本号递增，故 2021/2024 用「按 R2018 落盘 +
字节级改写 `$ACADVER`」生成，结构与真实 AutoCAD 产出一致，ezdxf 可正常回读。

每个样本文件含多类几何 + 挂靠/未挂靠标注，跑通 `load_dxf`（解析）+ `run_pipeline`
（检测）两段，断言：无崩溃、尺寸数 > 0 且流水线计数一致、版本号正确保留。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Union

import ezdxf

from app.core.loader import load_dxf
from app.core.pipeline import run_pipeline

# —— AutoCAD 2007–2025 → DXF 版本档 ——
# (目标版本, 目标 $ACADVER, AutoCAD 版本名, ezdxf.new() 的落盘基版本)
# 基版本 == 目标版本时 saveas 直接写出目标 $ACADVER；AC1035/AC1036 以 R2018 落盘后
# 由 `_patch_acadver` 字节级改写（R2018 之后仅版本号变化，结构一致）。
AUTOCAD_MATRIX: list[tuple[str, str, str, str]] = [
    ("R2007",  "AC1021", "AutoCAD 2007",      "R2007"),
    ("R2010",  "AC1024", "AutoCAD 2010",      "R2010"),
    ("R2013",  "AC1027", "AutoCAD 2013",      "R2013"),
    ("R2018",  "AC1032", "AutoCAD 2018",      "R2018"),
    ("AC1035", "AC1035", "AutoCAD 2021",      "R2018"),
    ("AC1036", "AC1036", "AutoCAD 2024/2025", "R2018"),
]

# 抽样文件数（requirements §验收：「抽样测试 20 个不同版本文件」）。
MATRIX_SAMPLE_N = 20


@dataclass
class VersionCheck:
    """一个样本文件的兼容性检查结果。"""

    file: str                 # 文件名
    version: str              # 目标 DXF 版本（R2007 / AC1035 …）
    acadver: str              # 实际回读的 $ACADVER（应等于目标）
    autocad: str              # AutoCAD 版本名（用于报告可读性）
    entity_count: int = 0
    dimension_count: int = 0
    unattached_count: int = 0
    ok: bool = False
    error: Optional[str] = None
    warnings: list[str] = field(default_factory=list)


@dataclass
class MatrixReport:
    """版本矩阵整体报告。"""

    checks: list[VersionCheck] = field(default_factory=list)
    n_files: int = 0

    @property
    def passed(self) -> bool:
        """全部样本加载 + 检测成功且版本一致。"""
        return len(self.checks) == self.n_files and self.n_files > 0 and all(
            c.ok for c in self.checks
        )

    def render(self) -> str:
        """人类可读报告（GBK 安全，无 emoji）。"""
        lines = [
            "=" * 62,
            "未挂靠尺寸识别 —— T7.3 版本兼容矩阵报告",
            "=" * 62,
            f"抽样文件数：{self.n_files}（AutoCAD 2007–2025，共 6 个 DXF 版本档）",
            "",
            f"  {'文件':<22}{'DXF':<9}{'实体':>6}{'尺寸':>5}{'未挂靠':>6}  结果",
            f"  {'-'*22}{'-'*9}{'-'*6}{'-'*5}{'-'*6}  ----",
        ]
        for c in self.checks:
            status = "[通过]" if c.ok else f"[失败] {c.error or ''}"
            lines.append(
                f"  {c.file:<22}{c.acadver:<9}{c.entity_count:>6}"
                f"{c.dimension_count:>5}{c.unattached_count:>6}  {status}"
            )
        lines.append("")
        lines.append(
            f"  版本矩阵：{'[通过] 达标' if self.passed else '[未通过] 存在失败'}"
        )
        lines.append("=" * 62)
        return "\n".join(lines)


# —— 样本生成 ——

def _add_entities(msp, n_lines: int) -> None:
    """铺确定性几何 + 标注。

    核心几何（线/弧/圆/点/二维多段线/单行文字）为 R12 起全版本通用；标注用
    线性（挂靠）+ 半径（未挂靠，render 后整体平移 defpoints 到空旷区），触发
    检测 + 转块全路径。R2000+ 再补样条/椭圆/轻量多段线/多行文字。
    """
    for i in range(n_lines):
        msp.add_line((i * 12.0, 0.0), (i * 12.0 + 8.0, 3.0))
    msp.add_circle((0.0, 40.0), 3.0)
    msp.add_arc((20.0, 40.0), 4.0, 0.0, 90.0)
    msp.add_point((40.0, 40.0))
    msp.add_polyline2d([(0.0, 60.0), (10.0, 60.0), (10.0, 66.0)])
    msp.add_text("sample", dxfattribs={"height": 2.0})

    # R2000+ 才支持的图元（R12 写这些会 DXFVersionError，故按版本选择性铺）。
    if msp.doc.dxfversion >= "AC1015":
        msp.add_spline([(0.0, 80.0), (10.0, 85.0), (20.0, 80.0)])
        msp.add_ellipse((30.0, 80.0), major_axis=(6.0, 0.0), ratio=0.5)
        msp.add_lwpolyline([(50.0, 80.0), (60.0, 80.0), (60.0, 88.0)])
        msp.add_mtext("rich")

    # 标注：线性挂靠（定义点在几何线上）+ 半径未挂靠（定义点整体平移 +300）。
    linear = msp.add_linear_dim(base=(0, -10), p1=(0, 0), p2=(10, 0))
    linear.render()
    radius = msp.add_radius_dim(center=(0, 40), mpoint=(3, 40))
    radius.render()
    dim = radius.dimension
    for attr in ("defpoint", "defpoint2", "defpoint3", "defpoint4"):
        if hasattr(dim.dxf, attr):
            p = getattr(dim.dxf, attr)
            setattr(dim.dxf, attr, (p[0] + 300.0, p[1] + 300.0, p[2]))


def _patch_acadver(path: Union[str, Path], target: str) -> None:
    """AC1035/AC1036 无法由 ezdxf.new() 写，落盘后字节级改写 `$ACADVER`。

    仅当目标非 AC1032（R2018）时执行；`AC1032` 仅出现在表头 $ACADVER，字节级
    replace 不影响其余结构，且与文件编码无关（ASCII 子串，字节直接替换）。
    """
    if target == "AC1032":
        return
    p = Path(path)
    p.write_bytes(p.read_bytes().replace(b"AC1032", target.encode("ascii")))


def _gen_one(path: Union[str, Path], base_version: str, acadver: str, n_lines: int) -> str:
    """按基版本落盘一张样本，必要时改写 $ACADVER，返回路径。"""
    doc = ezdxf.new(base_version)
    _add_entities(doc.modelspace(), n_lines)
    doc.saveas(str(path))
    _patch_acadver(path, acadver)
    return str(path)


def gen_matrix(directory: Union[str, Path], n: int = MATRIX_SAMPLE_N) -> list[tuple[str, str, str, str]]:
    """生成 n 个抽样文件（轮转覆盖 6 个版本档），返回 (路径, 版本, $ACADVER, AutoCAD)。

    每文件实体数由索引微调（确定性、可复现），使 20 个样本非字节重复，更贴近
    「抽样」语义。返回列表供 `run_matrix` 逐一检查。
    """
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    out: list[tuple[str, str, str, str]] = []
    for i in range(n):
        version, acadver, autocad, base = AUTOCAD_MATRIX[i % len(AUTOCAD_MATRIX)]
        path = directory / f"sample_{i:02d}_{version}.dxf"
        _gen_one(path, base, acadver, n_lines=8 + (i % 5))
        out.append((str(path), version, acadver, autocad))
    return out


def check_file(path: str, version: str, acadver: str, autocad: str) -> VersionCheck:
    """对一个样本文件做「加载 + 检测」，返回 VersionCheck（任何异常也不抛出）。"""
    name = Path(path).name
    try:
        loaded = load_dxf(path)
        out = run_pipeline(path)
        version_ok = loaded.doc.dxfversion == acadver
        return VersionCheck(
            file=name,
            version=version,
            acadver=loaded.doc.dxfversion,
            autocad=autocad,
            entity_count=loaded.entity_count,
            dimension_count=loaded.dimension_count,
            unattached_count=out.result.unattached_count,
            ok=version_ok
            and loaded.dimension_count > 0
            and out.result.total_dimensions == loaded.dimension_count,
            warnings=loaded.warnings,
        )
    except Exception as exc:  # noqa: BLE001 —— 兼容性检查：单文件失败只记 error，不中断矩阵
        return VersionCheck(
            file=name,
            version=version,
            acadver=acadver,
            autocad=autocad,
            ok=False,
            error=f"{type(exc).__name__}: {exc}",
        )


def run_matrix(directory: Union[str, Path], n: int = MATRIX_SAMPLE_N) -> MatrixReport:
    """生成抽样文件并逐一检查，返回 MatrixReport。"""
    files = gen_matrix(directory, n=n)
    checks = [check_file(p, v, a, ac) for p, v, a, ac in files]
    return MatrixReport(checks=checks, n_files=n)


__all__ = [
    "AUTOCAD_MATRIX",
    "MATRIX_SAMPLE_N",
    "VersionCheck",
    "MatrixReport",
    "gen_matrix",
    "check_file",
    "run_matrix",
]
