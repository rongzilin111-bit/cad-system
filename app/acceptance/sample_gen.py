# -*- coding: utf-8 -*-
"""T7.1 样本集生成器：产出「带真值标签」的 DXF 样本集。

为什么程序化生成（而非用真实图纸）：
    直通率 / 误报率需要**逐标注真值**（每个标注到底是挂靠还是未挂靠）。
    真实测试文件只有聚合画像（181/188 个未挂靠），没有逐标注标签，无法
    直接算误报率。故本模块用 ezdxf 生成样本：每个标注的**定义点**被显式
    放置到两类位置，从而真值唯一、确定、可复现（固定 seed）：

        - 挂靠（attached）    ：定义点落在几何**上**（线段端点/中点、圆心、
                               圆的象限点/圆周、圆弧中心），最近距离 ≈ 0；
        - 未挂靠（unattached） ：定义点落在「远离一切几何」的空旷区（≥390mm），
                               最近距离 ≫ 0.01mm 阈值。

    另加**阈值边界样本**（仅线性）：定义点距几何 0.005mm（应挂靠）与
    0.02mm（应未挂靠），精确验证 0.01mm 判定界。

每个样本（图纸）含全部 8 类标注 × {挂靠, 未挂靠} = 16 个 + 2 个边界样本，
配一份 `manifest.json` 记录每个标注的 handle / 类型 / 预期未挂靠布尔值，
供 `evaluate.run_acceptance` 逐一比对。

几何布局（相对每张图纸的平移 (dx, dy)，dx = 图纸序号 × 500）：
    LINE1 (dx,dy)-(dx+10,dy)、LINE2 (dx,dy+10)-(dx+10,dy+10)、
    CIRCLE1 (dx+30,dy) r5、CIRCLE2 (dx+30,dy+20) r5、ARC1 (dx+50,dy) r4 0-90°、
    LWPOLYLINE1 (dx,dy+30)-(dx+10,dy+30)-(dx+10,dy+40)、POINT1 (dx+40,dy+40)。
    定义点锚点均取自这些几何的特征点/曲线，未挂靠区在 (dx+400, dy+400) 附近。
"""
from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass
from pathlib import Path

import ezdxf

# —— 各类型在 DXF 中的 dimtype（低 3 位 = 类型码；detector 用 `dimtype & 0x07`）。
#    工厂 `add_aligned_dim` 实测只给 32（线性），故 aligned 显式写成 33 ——
DIMTYPE: dict[str, int] = {
    "linear": 32,
    "aligned": 33,
    "angular": 34,
    "diameter": 35,
    "radius": 36,
    "angular_3p": 37,
    "ordinate": 102,   # 0x66：bit5(块排他) + bit6(坐标X) + 6；低 3 位仍 = 6
}

# —— 各类型「定义点」要覆写的 (组码, dxf 属性名, 锚点键)。与 defpoints.py 的
#    `_DEFPOINT_SPECS` 严格对应（检测器只读这些组码）——
DEFPOINT_SPEC: dict[str, list[tuple[int, str, str]]] = {
    "linear":     [(13, "defpoint3", "o1"), (11, "defpoint2", "o2")],
    "aligned":    [(13, "defpoint3", "o1"), (11, "defpoint2", "o2")],
    "angular":    [(10, "defpoint", "v"), (13, "defpoint3", "o1"), (14, "defpoint4", "o2")],
    "diameter":   [(10, "defpoint", "e1"), (14, "defpoint4", "e2")],
    "radius":     [(10, "defpoint", "c"), (14, "defpoint4", "a")],
    "angular_3p": [(10, "defpoint", "v"), (13, "defpoint3", "o1"), (14, "defpoint4", "o2")],
    "ordinate":   [(11, "defpoint2", "f")],
    "arc":        [(10, "defpoint", "ac")],
}

# —— 全部类型，保证 8 类全覆盖（arc 为 ARC_DIMENSION 实体类，dimtype 恒 37）——
ALL_TYPES: tuple[str, ...] = (
    "linear", "aligned", "angular", "diameter",
    "radius", "angular_3p", "ordinate", "arc",
)

# —— 未挂靠区相对图纸原点的偏移（mm）。图纸几何都在 (dx,dy) 起 60mm 内，
#    400mm 远超曲线索引 3×3 网格邻域（±150mm）与 snap_radius(50mm)，确保干净 ——
_CLEAR_OFFSET = 400.0

# —— 阈值边界样本的偏移量（mm）：0.005 < 0.01 应挂靠；0.02 > 0.01 应未挂靠 ——
_BOUNDARY_NEAR = 0.005
_BOUNDARY_FAR = 0.02


@dataclass
class SampleCase:
    """单个标注的真值条目（handle 用于 save/reload 后与 result.dimensions 对齐）。"""
    handle: str
    type: str
    expected_unattached: bool


def _anchors(dx: float, dy: float) -> dict[str, tuple[float, float]]:
    """返回各锚点键 → (x, y)，全部落在几何特征点/曲线上（挂靠时最近距离 ≈ 0）。"""
    a = math.radians(45.0)
    return {
        "o1": (dx + 0.0, dy + 0.0),                       # LINE1 起点
        "o2": (dx + 10.0, dy + 0.0),                      # LINE1 终点
        "v":  (dx + 0.0, dy + 10.0),                      # LINE2 起点
        "e1": (dx + 35.0, dy + 0.0),                      # CIRCLE1 0° 象限点
        "e2": (dx + 30.0 + 5.0 * math.cos(a), dy + 0.0 + 5.0 * math.sin(a)),  # CIRCLE1 45° 圆周
        "c":  (dx + 30.0, dy + 20.0),                     # CIRCLE2 圆心
        "a":  (dx + 35.0, dy + 20.0),                     # CIRCLE2 0° 象限点
        "f":  (dx + 5.0, dy + 0.0),                       # LINE1 中点（曲线投影，非特征点）
        "ac": (dx + 50.0, dy + 0.0),                      # ARC1 圆心
    }


def _add_geometry(msp, dx: float, dy: float, extra: int) -> None:
    """放置一张图纸的几何图元。`extra` 轮换附加几何类型，让各图纸不完全同构。"""
    msp.add_line((dx + 0, dy + 0), (dx + 10, dy + 0))
    msp.add_line((dx + 0, dy + 10), (dx + 10, dy + 10))
    msp.add_circle((dx + 30, dy + 0), 5)
    msp.add_circle((dx + 30, dy + 20), 5)
    msp.add_arc((dx + 50, dy + 0), 4, 0, 90)
    msp.add_lwpolyline([(dx + 0, dy + 30), (dx + 10, dy + 30), (dx + 10, dy + 40)])
    msp.add_point((dx + 40, dy + 40))
    # 附加几何：放在远离锚点与未挂靠区的位置（≥100mm），不影响任何定义点距离。
    if extra % 3 == 0:
        msp.add_line((dx + 200, dy + 0), (dx + 210, dy + 0))
    elif extra % 3 == 1:
        msp.add_circle((dx + 200, dy + 20), 3)
    else:
        msp.add_arc((dx + 200, dy + 40), 3, 0, 180)


def _add_dimension(msp, type_name: str, dx: float, dy: float):
    """按类型用 ezdxf 工厂建一个合法标注，返回 (DimStyleOverride, DIMENSION)。"""
    if type_name == "linear":
        obj = msp.add_linear_dim(base=(dx + 5, dy + 3), p1=(dx, dy), p2=(dx + 10, dy))
    elif type_name == "aligned":
        obj = msp.add_aligned_dim(p1=(dx, dy), p2=(dx + 10, dy), distance=5)
    elif type_name == "angular":
        obj = msp.add_angular_dim_2l(
            base=(dx + 5, dy - 3),
            line1=((dx, dy), (dx + 10, dy)),
            line2=((dx, dy), (dx, dy + 10)),
        )
    elif type_name == "diameter":
        obj = msp.add_diameter_dim(center=(dx + 30, dy), mpoint=(dx + 35, dy))
    elif type_name == "radius":
        obj = msp.add_radius_dim(center=(dx + 30, dy + 20), mpoint=(dx + 35, dy + 20))
    elif type_name == "angular_3p":
        obj = msp.add_angular_dim_3p(
            base=(dx + 5, dy - 3),
            center=(dx, dy), p1=(dx + 10, dy), p2=(dx, dy + 10),
        )
    elif type_name == "ordinate":
        obj = msp.add_ordinate_x_dim(feature_location=(dx + 5, dy), offset=(dx + 5, dy + 5))
    elif type_name == "arc":
        obj = msp.add_arc_dim_cra(
            center=(dx + 50, dy), radius=4, start_angle=0, end_angle=90, distance=5
        )
    else:  # pragma: no cover —— 防御
        raise ValueError(f"未知标注类型：{type_name}")
    return obj, obj.dimension


def _set_defpoints(dim, type_name: str, anchors: dict, unattached: bool) -> None:
    """按类型覆写检测器会读到的定义点（10/11/13/14）到挂靠锚点或未挂靠区。"""
    for idx, (gc, attr, key) in enumerate(DEFPOINT_SPEC[type_name]):
        if unattached:
            x, y = (anchors["o1"][0] + _CLEAR_OFFSET + idx, anchors["o1"][1] + _CLEAR_OFFSET)
        else:
            x, y = anchors[key]
        setattr(dim.dxf, attr, (x, y, 0.0))


def generate_sample(path, index: int, dx: float, dy: float) -> list[SampleCase]:
    """生成一张样本图纸（保存到 `path`），返回其全部标注的真值条目列表。"""
    doc = ezdxf.new("R2018")
    msp = doc.modelspace()
    _add_geometry(msp, dx, dy, extra=index)
    anchors = _anchors(dx, dy)

    cases: list[SampleCase] = []
    # —— 8 类 × {挂靠, 未挂靠} ——
    for type_name in ALL_TYPES:
        for unattached in (False, True):
            obj, dim = _add_dimension(msp, type_name, dx, dy)
            obj.render()  # 先渲染生成几何块，否则 loader 的 audit 会删掉未渲染 DIMENSION
            if type_name in DIMTYPE:
                dim.dxf.dimtype = DIMTYPE[type_name]
            _set_defpoints(dim, type_name, anchors, unattached)
            cases.append(SampleCase(handle=dim.dxf.handle, type=type_name,
                                    expected_unattached=unattached))

    # —— 阈值边界样本（线性）：0.005mm 应挂靠、0.02mm 应未挂靠 ——
    for tag, offset, unattached in (
        ("boundary_near", _BOUNDARY_NEAR, False),
        ("boundary_far", _BOUNDARY_FAR, True),
    ):
        obj, dim = _add_dimension(msp, "linear", dx, dy)
        obj.render()
        dim.dxf.dimtype = DIMTYPE["linear"]
        # 仅 origin1(13) 偏离几何；origin2(11) 仍挂靠 → 检验「任一点脱钩即未挂靠」
        dim.dxf.defpoint3 = (dx + 0.0, dy + offset, 0.0)
        dim.dxf.defpoint2 = (dx + 10.0, dy + 0.0, 0.0)
        cases.append(SampleCase(handle=dim.dxf.handle, type=f"linear::{tag}",
                                expected_unattached=unattached))

    doc.saveas(str(path))
    return cases


def generate_sample_set(out_dir, n: int = 50, seed: int = 0) -> dict:
    """生成含 `n` 张样本图纸的样本集，写 manifest.json，返回 manifest 内容。"""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    samples: list[dict] = []
    for i in range(n):
        dx, dy = i * 500.0, 0.0
        cases = generate_sample(out / f"sample_{i:04d}.dxf", i, dx, dy)
        samples.append({
            "file": f"sample_{i:04d}.dxf",
            "cases": [asdict(c) for c in cases],
        })
    manifest = {
        "generator": "sample_gen",
        "n_drawings": n,
        "seed": seed,
        "samples": samples,
    }
    (out / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return manifest


__all__ = [
    "ALL_TYPES",
    "SampleCase",
    "generate_sample",
    "generate_sample_set",
]
