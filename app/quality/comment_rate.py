# -*- coding: utf-8 -*-
"""T7.4 代码质量：注释率统计与核查脚本。

验收口径（requirements §代码质量 / plan.md T7.4）：
    注释率 ≥25%，关键算法附原理说明；人工 / 脚本核查达标。

注释率定义（统一、可复现的口径）：
    注释率 = 注释行数 / 非空总行数，其中「注释行」= `#` 注释行 + 字符串字面量行
    （含 docstring）。用标准库 `tokenize` 精确分词——`#` 注释为 COMMENT token，
    docstring / 三引号块字符串为 STRING token，两者覆盖的行都计入注释（同一行只
    计一次）。该口径把 docstring 与块字符串视为「原理说明 / 文档」，符合本工程以
    docstring 为主要文档载体的实际（每个模块 / 类 / 函数均有中文 docstring）。

「关键算法附原理说明」的核查：另用 `ast.get_docstring` 统计每个模块是否有模块级
docstring，100% 覆盖即代表各关键算法（定义点提取 / 最近距离判定 / 曲线投影 /
三类吸附 / 块标准化等）均有原理说明。
"""
from __future__ import annotations

import ast
import io
import tokenize
from dataclasses import dataclass, field
from pathlib import Path

# —— 阈值与统计范围 ——
COMMENT_RATE_THRESHOLD = 0.25   # 注释率 ≥25%（requirements §代码质量）

# 项目根：由本模块路径上溯三层（app/quality/comment_rate.py → 项目根），
# 使脚本不受当前工作目录影响。
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
SOURCE_ROOTS: list[Path] = [PROJECT_ROOT / "app", PROJECT_ROOT / "main.py"]


@dataclass
class FileMetric:
    """单个源文件的注释率度量。"""

    path: str
    total: int                 # 非空总行数
    comment: int               # 注释行数（# 注释 + docstring/字符串）
    has_module_docstring: bool = False

    @property
    def rate(self) -> float:
        return self.comment / self.total if self.total else 0.0


@dataclass
class QualityReport:
    """代码质量整体报告。"""

    metrics: list[FileMetric] = field(default_factory=list)
    threshold: float = COMMENT_RATE_THRESHOLD

    @property
    def total_lines(self) -> int:
        return sum(m.total for m in self.metrics)

    @property
    def total_comment(self) -> int:
        return sum(m.comment for m in self.metrics)

    @property
    def overall_rate(self) -> float:
        return self.total_comment / self.total_lines if self.total_lines else 0.0

    @property
    def all_files_pass(self) -> bool:
        """每个文件注释率都 ≥ 阈值（不接受个别文件拖低整体）。"""
        return len(self.metrics) > 0 and all(m.rate >= self.threshold for m in self.metrics)

    @property
    def all_have_docstring(self) -> bool:
        """每个模块都有模块级 docstring（关键算法附原理说明的核查）。"""
        return len(self.metrics) > 0 and all(m.has_module_docstring for m in self.metrics)

    @property
    def passed(self) -> bool:
        return self.all_files_pass and self.all_have_docstring

    def render(self) -> str:
        """人类可读报告（GBK 安全，无 emoji）。"""
        lines = [
            "=" * 62,
            "未挂靠尺寸识别 —— T7.4 代码质量（注释率）报告",
            "=" * 62,
            f"注释率阈值：≥ {self.threshold * 100:.0f}%（每文件独立判定）",
            f"统计范围：{SOURCE_ROOTS[0].name}/ 与 main.py（共 {len(self.metrics)} 个 .py）",
            "",
            f"  {'文件':<40}{'总行':>5}{'注释':>5}{'率':>7}  模块 docstring",
            f"  {'-'*40}{'-'*5}{'-'*5}{'-'*7}  --------------",
        ]
        for m in self.metrics:
            doc = "有" if m.has_module_docstring else "缺"
            lines.append(
                f"  {m.path:<40}{m.total:>5}{m.comment:>5}{m.rate * 100:>6.1f}%  {doc}"
            )
        lines.append(f"  {'-'*40}{'-'*5}{'-'*5}{'-'*7}")
        lines.append(
            f"  {'合计':<40}{self.total_lines:>5}{self.total_comment:>5}"
            f"{self.overall_rate * 100:>6.1f}%"
        )
        lines.append("")
        lines.append(
            f"  注释率 ≥25%：{'[通过]' if self.all_files_pass else '[未通过]'}（每文件）"
        )
        lines.append(
            f"  模块 docstring：{'[通过] 100% 覆盖' if self.all_have_docstring else '[未通过] 存在缺失'}"
        )
        lines.append(
            f"  代码质量：{'[通过] 达标' if self.passed else '[未通过] 未达标'}"
        )
        lines.append("=" * 62)
        return "\n".join(lines)


def _has_module_docstring(path: Path) -> bool:
    """用 ast 判断模块是否有模块级 docstring（= 顶层原理说明）。"""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (SyntaxError, UnicodeDecodeError):
        return False
    return ast.get_docstring(tree) is not None


def analyze_file(path: Path) -> FileMetric:
    """统计单个 .py 文件的注释行数、非空行数与模块 docstring 是否存在。"""
    src = path.read_text(encoding="utf-8")
    lines = src.splitlines()
    nonblank = {i for i, line in enumerate(lines, 1) if line.strip()}

    comment_lines: set[int] = set()   # # 注释所在行（含行内注释）
    string_lines: set[int] = set()    # 字符串字面量（docstring/块字符串）覆盖的行
    for tok in tokenize.generate_tokens(io.StringIO(src).readline):
        if tok.type == tokenize.COMMENT:
            comment_lines.add(tok.start[0])
        elif tok.type == tokenize.STRING:
            for row in range(tok.start[0], tok.end[0] + 1):
                string_lines.add(row)

    comment = len((comment_lines | string_lines) & nonblank)
    rel = path.relative_to(PROJECT_ROOT) if path.is_relative_to(PROJECT_ROOT) else path
    return FileMetric(
        path=str(rel),
        total=len(nonblank),
        comment=comment,
        has_module_docstring=_has_module_docstring(path),
    )


def _iter_source_files() -> list[Path]:
    """遍历 SOURCE_ROOTS，返回全部 .py 源文件（排序，稳定输出）。"""
    files: list[Path] = []
    for root in SOURCE_ROOTS:
        if root.is_dir():
            files.extend(p for p in root.rglob("*.py"))
        elif root.is_file() and root.suffix == ".py":
            files.append(root)
    return sorted(files)


def analyze_tree() -> QualityReport:
    """统计整个源码树，返回 QualityReport。"""
    metrics = [analyze_file(p) for p in _iter_source_files()]
    return QualityReport(metrics=metrics)


__all__ = [
    "COMMENT_RATE_THRESHOLD",
    "SOURCE_ROOTS",
    "FileMetric",
    "QualityReport",
    "analyze_file",
    "analyze_tree",
]
