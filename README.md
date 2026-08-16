# 未挂靠尺寸标注的智能识别与测量点位重构系统

基于 Python + ezdxf + PySide6 的 GUI 应用，识别机械 CAD 图纸（DXF）中「未挂靠（游离）」的
尺寸标注，提取其坐标/数值/公差并结构化输出为 JSON，同时将标注标准化为块、归入专用图层
`Dim_Reconstruct_Layer`，并重构其与几何图元的测量点位。

## 功能概览

1. 解析 DXF（AutoCAD 2007–2025，GBK 编码），提取几何实体与尺寸标注。
2. 识别「定义点脱钩」的未挂靠尺寸标注（判定阈值默认 0.01mm）。
3. 提取每个未挂靠标注的轴对齐最小外接矩、尺寸值、公差。
4. 将脱钩定义点吸附回最近几何，记录纠偏后坐标。
5. 将原生 DIMENSION 重组为命名块并归入 `Dim_Reconstruct_Layer`。
6. 输出：另存 DXF（保留图层/颜色/线型/块定义）+ JSON + 轮转日志（≥180 天）。

## 目录结构

```
dimension-reconstruct/
├── main.py                  # 入口：启动 GUI
├── requirements.txt
├── app/
│   ├── config.py            # 常量：容差/吸附半径/图层名/块名前缀
│   ├── models.py            # dataclass 数据模型
│   ├── core/                # 核心管线：解析/判定/提取/块转换
│   ├── io/                  # JSON 导出 / DXF 另存 / 日志
│   └── gui/                 # PySide6 界面
├── tests/                   # pytest 单测
├── build/                   # PyInstaller 打包
└── logs/                    # 运行日志
```

## 快速开始

```bash
# 1. 创建虚拟环境并安装依赖（建议 Python 3.10/3.11）
python -m venv .venv
.venv\Scripts\activate          # Windows
pip install -r requirements.txt

# 2. 运行 GUI
python main.py
```

## 设计文档

- 需求依据：`../project/需求分析.md`
- 技术方案：`../project/ARCHITECTURE.md`
- 开发进度：`../project/plan.md`

## 备注

- 孤儿 `*D` 块默认**不删除**（满足需求「完整保留块定义」），可在 GUI 中显式开启清理。
- 测量点位重构采用「最近点吸附」口径（已与需求方确认）。
