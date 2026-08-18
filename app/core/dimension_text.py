# -*- coding: utf-8 -*-
"""M3.2 尺寸值与公差解析。

T3.2 —— 提取尺寸值、文字与公差（见 ARCHITECTURE.md §5.3）：

    1. 尺寸值：优先 `dim.get_measurement()`（组码 42）；若存在文字覆盖
       （组码 1 非空且含实际数字，非 `<>`），则解析覆盖文本。
    2. 文本解码：`%%C`→⌀、`%%D`→°、`%%P`→±、`%%%`→%；MTEXT 栈式
       `\\S上^下;`（极限/偏差叠写）、`\\A1;` 等控制标记。
    3. 公差来源：a) 覆盖文本内 `%%P`（对称）/`\\S`（偏差或极限）显式公差；
       b) 无显式则读 DIMSTYLE 的 `dimtol`(DIMTOL)/`dimlim`(DIMLIM)/
          `dimtp`(DIMTP)/`dimtm`(DIMTM)。
    4. 输出：`mode` 枚举（symmetrical/deviation/limits/basic/none）
       + `nominal/upper/lower`。
    5. 兜底：解析失败记 `raw` 原文、`mode=none`，**绝不抛异常**。

模式判定规则（与 CAD 语义对齐）：
    - 对称：`%%P0.1`，或 dimstyle `dimtol` 且 `dimtp == dimtm`。
    - 偏差：栈式上下带显式符号（`\\S+0.1^-0.2;`），或 `dimtol` 且 tp≠tm。
    - 极限：栈式上下为绝对值（`\\S28.1^27.8;`），或 dimstyle `dimlim`。
    - 基本：带框尺寸（GD&T 理论正确值）——DXF 无标准组码，本文件不支持
      可靠检测，故不产生 `basic`，仅在模式名里保留该枚举待后续扩展。
"""
from __future__ import annotations

import re
from typing import Optional

from ezdxf.entities import DXFEntity

from app.models import Tolerance

# —— 数字提取：匹配带符号浮点/科学计数 ——
_NUM_RE = re.compile(r"[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?")

# —— 栈式叠写 \S上^下; ——
_STACK_RE = re.compile(r"\\S([^^;\\]*)\^([^;]*);")
# —— \A1; 等 MTEXT 控制标记 ——
_CTRL_RE = re.compile(r"\\[A-Za-z][A-Za-z0-9]*;")


def _first_number(s: str) -> Optional[float]:
    """取字符串第一个数字；无数字返回 None。"""
    m = _NUM_RE.search(s)
    if not m:
        return None
    try:
        return float(m.group())
    except ValueError:
        return None


def _number_after(raw: str, marker: str) -> Optional[float]:
    """取 `marker` 之后第一个数字（如 `%%P` 后的对称公差值）。"""
    idx = raw.find(marker)
    if idx < 0:
        return None
    return _first_number(raw[idx + len(marker):])


def decode_text(raw: str) -> str:
    """解码尺寸文字：`%%` 转义、栈式叠写、控制标记 → 可读字符串。"""
    if not raw:
        return ""
    s = raw
    # 1. 栈式 \S上^下; → 「上/下」（极限/偏差叠写）
    s = _STACK_RE.sub(lambda m: f"{m.group(1)}/{m.group(2)}", s)
    # 2. 丢弃 \A1; 等控制标记
    s = _CTRL_RE.sub("", s)
    # 3. %% 转义（先 %%% → %，再 %%C/%%D/%%P，含小写）
    s = s.replace("%%%", "%")
    s = s.replace("%%C", "⌀").replace("%%c", "⌀")
    s = s.replace("%%D", "°").replace("%%d", "°")
    s = s.replace("%%P", "±").replace("%%p", "±")
    return s


# —— 坐标标注类型位：0x40 置位为 Y 型（测 Y 分量），清零为 X 型（测 X 分量） ——
_DIM_ORDINATE_TYPE = 0x40


def _measurement_to_float(dim: DXFEntity, m) -> Optional[float]:
    """把 `get_measurement()` 的结果统一成 float。

    线性/角度/直径/半径返回 float；坐标标注返回「原点→特征点」向量（Vec3），
    需按类型位取测量轴分量（X 型取 x、Y 型取 y，实测见 ARCHITECTURE.md §3.1）。
    """
    if m is None:
        return None
    if isinstance(m, (int, float)):
        return float(m)
    # 向量 / 序列（仅坐标标注会走到这里）
    try:
        x, y = float(m[0]), float(m[1])
    except Exception:  # noqa: BLE001
        return None
    if int(getattr(dim.dxf, "dimtype", 0)) & _DIM_ORDINATE_TYPE:
        return y  # Y 型坐标标注
    return x      # X 型坐标标注


def _nominal_value(dim: DXFEntity) -> Optional[float]:
    """取尺寸名义值：优先组码 42（get_measurement），文字覆盖时解析覆盖文本。"""
    try:
        nominal = _measurement_to_float(dim, dim.get_measurement())
    except Exception:  # noqa: BLE001 —— 个别实体无测量值
        nominal = None
    raw = getattr(dim.dxf, "text", "") or ""
    if raw.strip() not in ("", "<>"):
        # 去掉栈式（极限/偏差部分）再解码取第一个数字，作为覆盖名义值
        base = _STACK_RE.sub("", raw)
        n = _first_number(decode_text(base))
        if n is not None:
            nominal = n
    return nominal


def _split_stack(stack: str) -> tuple[Optional[float], Optional[float]]:
    """解析 `\\S上^下;` → (上, 下)；非栈式返回 (None, None)。"""
    m = _STACK_RE.search(stack)
    if not m:
        return None, None
    return _first_number(m.group(1)), _first_number(m.group(2))


def _has_sign(s: str) -> bool:
    """是否带显式 +/- 符号（用于区分偏差 vs 极限栈式）。"""
    return s.lstrip().startswith(("+", "-"))


def _tolerance_from_style(dim: DXFEntity, doc, nominal: Optional[float]) -> Tolerance:
    """读 DIMSTYLE 的 dimtol/dimlim/dimtp/dimtm，换算公差；无则 mode=none。"""
    name = getattr(dim.dxf, "dimstyle", "") or ""
    if not name or doc is None:
        return Tolerance(mode="none", nominal=nominal)
    try:
        ds = doc.dimstyles.get(name)
    except Exception:  # noqa: BLE001
        return Tolerance(mode="none", nominal=nominal)

    dimlim = bool(getattr(ds.dxf, "dimlim", 0))
    dimtol = bool(getattr(ds.dxf, "dimtol", 0))
    tp = float(getattr(ds.dxf, "dimtp", 0.0) or 0.0)
    tm = float(getattr(ds.dxf, "dimtm", 0.0) or 0.0)

    if dimlim and nominal is not None:
        # 极限：上=nominal+tp，下=nominal−tm（DIMTM 存正值，含义为下偏差量）
        return Tolerance(
            mode="limits", nominal=nominal, upper=nominal + tp, lower=nominal - tm
        )
    if dimtol and (tp > 0.0 or tm > 0.0):
        if abs(tp - tm) < 1e-12:
            return Tolerance(mode="symmetrical", nominal=nominal, upper=tp, lower=tp)
        return Tolerance(mode="deviation", nominal=nominal, upper=tp, lower=-tm)
    return Tolerance(mode="none", nominal=nominal)


def parse_tolerance(
    dim: DXFEntity, raw_text: str, nominal: Optional[float], doc=None
) -> Tolerance:
    """解析公差：覆盖文本显式公差 > DIMSTYLE 变量 > none。绝不抛异常。"""
    raw = raw_text or ""
    # 1. 显式对称公差 %%P0.1
    if "%%P" in raw or "%%p" in raw:
        v = _number_after(raw, "%%P")
        if v is None:
            v = _number_after(raw, "%%p")
        if v is not None:
            return Tolerance(
                raw=raw, mode="symmetrical", nominal=nominal, upper=v, lower=v
            )
    # 2. 显式栈式偏差 / 极限
    m = _STACK_RE.search(raw)
    if m:
        up, down = _split_stack(raw)
        if up is not None and down is not None:
            up_s = m.group(1)
            down_s = m.group(2)
            if _has_sign(up_s) or _has_sign(down_s):
                return Tolerance(
                    raw=raw, mode="deviation", nominal=nominal, upper=up, lower=down
                )
            return Tolerance(
                raw=raw, mode="limits", nominal=nominal, upper=up, lower=down
            )
    # 3. DIMSTYLE 公差
    tol = _tolerance_from_style(dim, doc, nominal)
    if tol.mode != "none":
        tol.raw = raw
        return tol
    return Tolerance(raw=raw, mode="none", nominal=nominal)


def parse_dimension(
    dim: DXFEntity, doc=None
) -> tuple[Optional[float], str, Tolerance]:
    """尺寸信息解析主入口：返回 (名义值, 解码文字, 公差)。

    `doc` 用于读取 DIMSTYLE（公差兜底），缺省时回退 `dim.doc`。
    """
    if doc is None:
        doc = getattr(dim, "doc", None)
    nominal = _nominal_value(dim)
    raw = getattr(dim.dxf, "text", "") or ""
    text = decode_text(raw)
    # 占位符 `<>`（自动测量）/空 → 显示为格式化名义值（如 "28"）
    if text in ("", "<>") and nominal is not None:
        text = f"{nominal:g}"
    tol = parse_tolerance(dim, raw, nominal, doc)
    return nominal, text, tol


__all__ = [
    "decode_text",
    "parse_tolerance",
    "parse_dimension",
]
