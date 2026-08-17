# -*- coding: utf-8 -*-
"""定义点提取单测（T2.1 尺寸类型判定 + T2.2 定义点提取）。

覆盖：
    T2.1 —— `dim_type_code` 只用「实体类 + 组码 70 & 0x07」，ARC_DIMENSION 单独判弧长；
    T2.2 —— `extract_defpoints` 按类型返回正确 role/组码，且坐标经 OCS→WCS。

说明：本文件测试**本项目校准后的映射契约**（见 `app/core/defpoints.py`
`_DEFPOINT_SPECS` 注释——实测测试文件的组码语义与 DXF 规范有三处出入，
已在模块注释标注）。故测试直接设置各 defpoint 属性，验证「读哪个组码」，
不依赖 ezdxf 尺寸工厂的默认组码。
"""
from __future__ import annotations

import ezdxf

from app.core.defpoints import (
    DIM_TYPE_NAMES,
    diameter_center,
    dim_type_code,
    dim_type_name,
    extract_defpoints,
)


def _linear_dim(doc: ezdxf.document.Drawing):
    """新建一个 DIMENSION（线性），返回实体；测试里再改 dimtype / defpoints。"""
    return doc.modelspace().add_linear_dim(
        base=(0, 0), p1=(0, 0), p2=(10, 0)
    ).dimension


def _set_all_defpoints(dim) -> None:
    """把 10/11/13/14/15 都设成互不相同的坐标，便于断言提取到了哪几个。"""
    dim.dxf.defpoint = (10, 10, 0)     # 组码 10
    dim.dxf.defpoint2 = (11, 11, 0)    # 组码 11
    dim.dxf.defpoint3 = (13, 13, 0)    # 组码 13
    dim.dxf.defpoint4 = (14, 14, 0)    # 组码 14
    dim.dxf.defpoint5 = (15, 15, 0)    # 组码 15


def test_dim_type_code_masks():
    """0~6 直接返回；带标志位仍 &0x07 得 0~6。"""
    doc = ezdxf.new("R2018")
    dim = _linear_dim(doc)
    for code in range(7):
        dim.dxf.dimtype = code
        assert dim_type_code(dim) == code
    dim.dxf.dimtype = 32   # 0x20 = linear | BLOCK_EXCLUSIVE
    assert dim_type_code(dim) == 0
    dim.dxf.dimtype = 37   # 0x25 = angular_3p(5) | BLOCK_EXCLUSIVE(32)
    assert dim_type_code(dim) == 5


def test_dim_type_code_arc_dimension():
    """ARC_DIMENSION 实体类直接判弧长(8)，而不是按 37&0x07=5 误判三点角度。"""
    doc = ezdxf.new("R2018")
    arc = doc.modelspace().new_entity(
        "ARC_DIMENSION", dxfattribs={"dimtype": 37, "layer": "0"}
    )
    assert arc.dxftype() == "ARC_DIMENSION"
    assert dim_type_code(arc) == 8
    assert dim_type_name(arc) == "arc"


def test_dim_type_name():
    doc = ezdxf.new("R2018")
    dim = _linear_dim(doc)
    for code, name in DIM_TYPE_NAMES.items():
        if code == 8:
            continue  # 8 由 ARC_DIMENSION 实体类给出，见上一条
        dim.dxf.dimtype = code
        assert dim_type_name(dim) == name


def test_extract_defpoints_roles_per_type():
    """各类型提取的 (role, 组码) 与校准后契约一致。"""
    doc = ezdxf.new("R2018")
    dim = _linear_dim(doc)
    _set_all_defpoints(dim)
    expected = {
        0: [("origin1", 13), ("origin2", 11)],                      # linear
        1: [("origin1", 13), ("origin2", 11)],                      # aligned
        2: [("vertex", 10), ("origin1", 13), ("origin2", 14)],      # angular
        3: [("endpoint1", 10), ("endpoint2", 14)],                  # diameter
        4: [("center", 10), ("arc_point", 14)],                     # radius
        5: [("vertex", 10), ("origin1", 13), ("origin2", 14)],      # angular_3p
        6: [("feature", 11)],                                       # ordinate
    }
    for code, roles in expected.items():
        dim.dxf.dimtype = code
        got = [(mp.role, mp.group_code) for mp in extract_defpoints(dim)]
        assert got == roles, f"type {code}: 期望 {roles}，实际 {got}"


def test_extract_defpoints_xy():
    """提取的坐标按 WCS 输出（测试文件 Z=0、拉伸 (0,0,1)，OCS=WCS）。"""
    doc = ezdxf.new("R2018")
    dim = _linear_dim(doc)
    dim.dxf.dimtype = 0
    dim.dxf.defpoint3 = (1, 2, 0)
    dim.dxf.defpoint2 = (3, 4, 0)
    pts = {mp.role: (mp.x, mp.y) for mp in extract_defpoints(dim)}
    assert pts["origin1"] == (1.0, 2.0)
    assert pts["origin2"] == (3.0, 4.0)


def test_extract_arc_dimension_center():
    """弧长标注（ARC_DIMENSION）提取圆心(组码 10)；该实体缺 defpoint5 也不影响。"""
    doc = ezdxf.new("R2018")
    arc = doc.modelspace().new_entity(
        "ARC_DIMENSION", dxfattribs={"dimtype": 37, "layer": "0"}
    )
    arc.dxf.defpoint = (3, 4, 0)  # 圆心
    pts = extract_defpoints(arc)
    assert [(mp.role, mp.group_code) for mp in pts] == [("center", 10)]
    assert pts[0].x == 3.0 and pts[0].y == 4.0


def test_diameter_center():
    """直径圆心 = 两对端点(10,14)中点。"""
    doc = ezdxf.new("R2018")
    dim = _linear_dim(doc)
    dim.dxf.dimtype = 3
    dim.dxf.defpoint = (0, 0, 0)    # endpoint1
    dim.dxf.defpoint4 = (10, 0, 0)  # endpoint2
    assert diameter_center(dim) == (5.0, 0.0)
    # 非直径类型返回 None
    dim.dxf.dimtype = 4
    assert diameter_center(dim) is None
