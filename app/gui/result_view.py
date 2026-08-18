# -*- coding: utf-8 -*-
"""M6 结果视图（QTableView + model）。

T6.2 —— 展示全部尺寸（961 行），未挂靠行淡红高亮；点击行经信号通知主窗口
刷新详情面板。展示字符串全部来自 `app.gui.presentation`，本模块只负责
Qt 模型-视图的装配与高亮（BackgroundRole），不自行拼格式。
"""
from __future__ import annotations

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import QAbstractItemView, QTableView

from app.gui.presentation import (
    SUMMARY_COLUMNS,
    SUMMARY_HEADERS,
    build_summary_rows,
)

# —— 未挂靠行的淡红高亮色（贴近 CAD 审图「异常标注」直觉） ——
_UNATTACHED_BG = QColor("#ffd9d9")


class SummaryTableModel(QAbstractTableModel):
    """summary 表格模型：行来自 `build_summary_rows`，列见 SUMMARY_HEADERS。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._rows: list[dict] = []

    def set_rows(self, rows: list[dict]) -> None:
        self.beginResetModel()
        self._rows = list(rows)
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()) -> int:  # noqa: N802
        return 0 if parent.isValid() else len(self._rows)

    def columnCount(self, parent=QModelIndex()) -> int:  # noqa: N802
        return 0 if parent.isValid() else len(SUMMARY_COLUMNS)

    def headerData(self, section, orientation, role=Qt.DisplayRole):  # noqa: N802
        if role == Qt.DisplayRole and orientation == Qt.Orientation.Horizontal:
            return SUMMARY_HEADERS[section]
        return None

    def data(self, index, role=Qt.DisplayRole):  # noqa: N802
        if not index.isValid():
            return None
        row = self._rows[index.row()]
        col = SUMMARY_COLUMNS[index.column()]
        if role == Qt.DisplayRole:
            return row[col]
        if role == Qt.BackgroundRole and row.get("unattached"):
            return QBrush(_UNATTACHED_BG)
        return None

    def handle_at(self, row: int) -> str:
        """返回第 `row` 行对应的尺寸句柄（供主窗口查详情）。"""
        return self._rows[row]["handle"]


class SummaryTableView(QTableView):
    """结果表格视图：整行选中、禁止编辑、隔行变色、未挂靠高亮。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._model = SummaryTableModel(self)
        self.setModel(self._model)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.setAlternatingRowColors(True)
        self.verticalHeader().setVisible(False)
        self.horizontalHeader().setStretchLastSection(True)

    def set_result(self, result) -> None:
        """载入 Result，构建表格行并自动列宽。"""
        self._model.set_rows(build_summary_rows(result))
        self.resizeColumnsToContents()

    def handle_at(self, row: int) -> str:
        return self._model.handle_at(row)

    def row_count(self) -> int:
        return self._model.rowCount()


__all__ = ["SummaryTableModel", "SummaryTableView"]
