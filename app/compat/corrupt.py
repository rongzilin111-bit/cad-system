# -*- coding: utf-8 -*-
"""T7.3 稳定性：损坏文件友好提示（无崩溃）。

验收口径（requirements §稳定性 / ARCHITECTURE.md §6.2）：
    对损坏的 CAD 文件应弹出友好提示而非程序异常退出。

核心不变量：对任意损坏输入，`load_dxf` 要么返回带 `warnings` 的 `LoadedDrawing`
（宽容解析 / recover 修复），要么抛 `LoadError`（友好异常）——绝不抛裸
`OSError` / `AttributeError` 等未预期异常导致上层崩溃。GUI `worker.py` 捕获
任意异常转 `failed` 信号，`dialogs.show_error` 友好弹窗，故「不崩溃」即达标。

覆盖的损坏形态（确定性字节，自包含可复现）：
    空文件 / ASCII 垃圾 / 二进制垃圾 / 只有表头 / 截断的 ENTITIES / 非法 $ACADVER /
    非法组码。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional, Union

from app.core.loader import LoadError, load_dxf


@dataclass
class CorruptCheck:
    """一个损坏输入的处理结果。"""

    name: str
    outcome: str                      # loaded | load_error | file_not_found | crashed
    exception: Optional[str] = None   # 异常类型名（load_error / crashed 时）
    message: str = ""                 # 异常信息（截断，供报告可读）
    recovered: bool = False           # 是否走了 recover 修复模式
    warning_count: int = 0            # 加载告警数（宽容解析的证据）

    @property
    def friendly(self) -> bool:
        """未崩溃：返回 loaded，或抛友好的 LoadError / FileNotFoundError。"""
        return self.outcome in ("loaded", "load_error", "file_not_found")


@dataclass
class CorruptReport:
    """损坏文件整体报告。"""

    checks: list[CorruptCheck] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        """全部损坏输入均未崩溃（友好提示而非异常退出）。"""
        return len(self.checks) > 0 and all(c.friendly for c in self.checks)

    def render(self) -> str:
        """人类可读报告（GBK 安全，无 emoji）。"""
        lines = [
            "=" * 62,
            "未挂靠尺寸识别 —— T7.3 损坏文件友好提示报告",
            "=" * 62,
            f"损坏样本数：{len(self.checks)}（确定性字节，自包含可复现）",
            "",
            f"  {'样本':<16}{'结果':<16}{'告警':>4}  说明",
            f"  {'-'*16}{'-'*16}{'-'*4}  ----",
        ]
        for c in self.checks:
            if c.outcome == "loaded":
                flag = "recover 修复" if c.recovered else "宽容解析"
                note = f"{flag}（告警 {c.warning_count}）"
            elif c.outcome == "load_error":
                note = f"友好异常 {c.exception}"
            elif c.outcome == "file_not_found":
                note = "FileNotFoundError"
            else:
                note = f"崩溃 {c.exception}: {c.message[:40]}"
            lines.append(f"  {c.name:<16}{c.outcome:<16}{c.warning_count:>4}  {note}")
        lines.append("")
        lines.append(
            f"  损坏文件：{'[通过] 全部友好提示、无崩溃' if self.passed else '[未通过] 存在崩溃'}"
        )
        lines.append("=" * 62)
        return "\n".join(lines)


# —— 确定性损坏样本生成器 ——

def _case_empty() -> bytes:
    return b""


def _case_ascii_garbage() -> bytes:
    return b"this is definitely not a DXF file\njust some plain text\n"


def _case_binary_garbage() -> bytes:
    return bytes(range(256)) * 4


def _case_header_only() -> bytes:
    return b"0\nSECTION\n2\nHEADER\n9\n$ACADVER\n1\nAC1032\n0\nENDSEC\n0\nEOF\n"


def _case_truncated_entities() -> bytes:
    # ENTITIES 段写到一半戛然而止：缺坐标值、无 ENDSEC/EOF。
    return b"0\nSECTION\n2\nENTITIES\n0\nLINE\n8\n0\n10\n0.0\n20\n"


def _case_bad_acadver() -> bytes:
    return b"0\nSECTION\n2\nHEADER\n9\n$ACADVER\n1\nAC0000\n0\nENDSEC\n0\nEOF\n"


def _case_invalid_group_code() -> bytes:
    return b"0\nSECTION\n2\nENTITIES\nXYZ\n0\nLINE\n0\nENDSEC\n0\nEOF\n"


# 顺序即报告展示顺序。
CORRUPT_CASES: list[tuple[str, Callable[[], bytes]]] = [
    ("空文件", _case_empty),
    ("ASCII 垃圾", _case_ascii_garbage),
    ("二进制垃圾", _case_binary_garbage),
    ("仅表头无实体", _case_header_only),
    ("截断的 ENTITIES", _case_truncated_entities),
    ("非法 $ACADVER", _case_bad_acadver),
    ("非法组码", _case_invalid_group_code),
]


def gen_corrupt(directory: Union[str, Path]) -> list[tuple[str, str]]:
    """把全部损坏样本落盘，返回 (路径, 样本名) 列表。"""
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    out: list[tuple[str, str]] = []
    for i, (name, fn) in enumerate(CORRUPT_CASES):
        p = directory / f"corrupt_{i:02d}_{name}.dxf"
        p.write_bytes(fn())
        out.append((str(p), name))
    return out


def check_corrupt(path: Union[str, Path], name: str) -> CorruptCheck:
    """对单个损坏文件调用 `load_dxf`，分类结果（任何异常也不向上抛）。"""
    try:
        loaded = load_dxf(path)
        return CorruptCheck(
            name=name,
            outcome="loaded",
            recovered=loaded.recovered,
            warning_count=len(loaded.warnings),
        )
    except LoadError as exc:
        return CorruptCheck(name=name, outcome="load_error",
                            exception=type(exc).__name__, message=str(exc))
    except FileNotFoundError:
        return CorruptCheck(name=name, outcome="file_not_found",
                            exception="FileNotFoundError")
    except Exception as exc:  # noqa: BLE001 —— 记录崩溃证据，测试据此判失败
        return CorruptCheck(name=name, outcome="crashed",
                            exception=type(exc).__name__, message=str(exc))


def run_corrupt(directory: Union[str, Path]) -> CorruptReport:
    """生成损坏样本并逐一检查，返回 CorruptReport。"""
    checks = [check_corrupt(p, name) for p, name in gen_corrupt(directory)]
    return CorruptReport(checks=checks)


__all__ = [
    "CORRUPT_CASES",
    "CorruptCheck",
    "CorruptReport",
    "gen_corrupt",
    "check_corrupt",
    "run_corrupt",
]
