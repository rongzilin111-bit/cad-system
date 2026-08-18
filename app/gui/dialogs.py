# -*- coding: utf-8 -*-
"""M6 对话框：损坏文件友好提示 / 信息弹窗。

T6.1 —— 参数设置走主窗口内联控件（容差 / 吸附半径 spin + 复选框，见
ARCHITECTURE.md §7.1 布局），无需模态参数对话框；进度条走主窗口状态栏的
`QProgressBar`（不确定态 busy）。本模块只提供错误 / 信息两类弹窗封装，
统一「友好提示、不崩溃」的交互口径（§6.2）。
"""
from __future__ import annotations

from PySide6.QtWidgets import QMessageBox, QWidget


def show_error(parent: QWidget | None, title: str, message: str) -> None:
    """错误弹窗（损坏文件 / 加载失败 / 运行异常）。"""
    QMessageBox.critical(parent, title, message)


def show_info(parent: QWidget | None, title: str, message: str) -> None:
    """信息弹窗（如「处理完成」摘要）。"""
    QMessageBox.information(parent, title, message)


__all__ = ["show_error", "show_info"]
