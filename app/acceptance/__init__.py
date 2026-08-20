# -*- coding: utf-8 -*-
"""T7.1 自动化验收：样本集生成 + 实际输出 vs 预期结果比对。

模块划分：
    sample_gen   —— 程序化生成「带真值标签」的 DXF 样本集（8 类标注 × 挂靠/未挂靠
                    + 阈值边界样本）+ manifest.json 真值清单
    evaluate     —— 逐样本跑 pipeline，按 handle 比对「实际 unattached vs 预期」，
                    计算直通率 / 误报率 / 漏报率，并给出达标判定
    __main__     —— 命令行入口：`python -m app.acceptance` 一键生成 → 运行 → 出报告

设计动机见 ARCHITECTURE.md §8/M7：真实图纸无逐标注真值，故用固定 seed 程序化
生成「真值唯一、可复现」的样本集，作为直通率 / 误报率的可量化比对基准。
"""
