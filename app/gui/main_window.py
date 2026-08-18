# -*- coding: utf-8 -*-
"""M6 主窗口。

T6.1 —— 文件选择、容差 / 吸附半径参数、运行按钮、后台线程、结果表格、
详情面板、JSON/DXF 导出与「打开输出目录 / 查看日志」。布局对齐
ARCHITECTURE.md §7.1：顶部文件与参数行，中部「表格 | 详情」左右分栏，
底部汇总栏 + 进度条 + 日志流。

交互要点（§7.2）：
    - 点「开始处理」起 `PipelineWorker`（QThread），主线程进度条 / 日志流不卡；
    - 完成 → 表格展示全部尺寸、未挂靠行高亮、点行看详情；
    - 后台已自动另存 DXF + 写 JSON + 记日志，「导出 JSON」提供另存为副本。
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QCheckBox,
    QDoubleSpinBox,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from app.config import DETACH_TOLERANCE, LOG_DIR, SNAP_RADIUS
from app.gui.dialogs import show_error
from app.gui.presentation import WorkerConfig, render_detail
from app.gui.result_view import SummaryTableView
from app.gui.worker import PipelineWorker
from app.io import json_export


class MainWindow(QMainWindow):
    """应用主窗口：装配控件、起后台 worker、回填结果。"""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("未挂靠尺寸标注识别与测量点位重构系统")
        self.resize(1120, 720)

        self._worker: PipelineWorker | None = None
        self._report = None
        self._infos: dict[str, object] = {}

        self._build_ui()
        self.table.selectionModel().currentRowChanged.connect(self._on_row_selected)

    # —— UI 构建 ——
    def _build_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)

        root.addLayout(self._build_file_row())
        root.addWidget(self._build_param_group())

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(self._build_table_group())
        splitter.addWidget(self._build_detail_group())
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)
        root.addWidget(splitter, 1)

        root.addLayout(self._build_status_row())
        root.addWidget(self._build_log_area())

    def _build_file_row(self) -> QHBoxLayout:
        row = QHBoxLayout()
        self.path_edit = QLineEdit()
        self.path_edit.setPlaceholderText("选择要检测的 .dxf 文件…")
        browse_btn = QPushButton("浏览…")
        browse_btn.clicked.connect(self._on_browse)
        self.run_btn = QPushButton("开始处理")
        self.run_btn.clicked.connect(self._on_run)
        row.addWidget(self.path_edit, 1)
        row.addWidget(browse_btn)
        row.addWidget(self.run_btn)
        return row

    def _build_param_group(self) -> QGroupBox:
        group = QGroupBox("参数")
        row = QHBoxLayout(group)

        row.addWidget(QLabel("判定阈值(mm)"))
        self.tol_spin = QDoubleSpinBox()
        self.tol_spin.setDecimals(3)
        self.tol_spin.setRange(0.0001, 100.0)
        self.tol_spin.setSingleStep(0.001)
        self.tol_spin.setValue(DETACH_TOLERANCE)
        row.addWidget(self.tol_spin)

        row.addSpacing(16)
        row.addWidget(QLabel("吸附半径(mm)"))
        self.snap_spin = QDoubleSpinBox()
        self.snap_spin.setDecimals(1)
        self.snap_spin.setRange(0.0, 100000.0)
        self.snap_spin.setSingleStep(1.0)
        self.snap_spin.setValue(SNAP_RADIUS)
        row.addWidget(self.snap_spin)

        row.addSpacing(16)
        self.expand_check = QCheckBox("展开块内几何")
        self.blockify_check = QCheckBox("执行块标准化")
        self.blockify_check.setChecked(True)
        self.clean_check = QCheckBox("清理孤儿 *D 块")
        self.clean_check.setToolTip("默认关，严格保留块定义；勾选后仅删除无引用的 *D 匿名块")
        row.addWidget(self.expand_check)
        row.addWidget(self.blockify_check)
        row.addWidget(self.clean_check)
        row.addStretch(1)
        return group

    def _build_table_group(self) -> QGroupBox:
        group = QGroupBox("检测结果")
        lay = QVBoxLayout(group)
        self.table = SummaryTableView()
        lay.addWidget(self.table)
        return group

    def _build_detail_group(self) -> QGroupBox:
        group = QGroupBox("详情")
        lay = QVBoxLayout(group)
        self.detail = QPlainTextEdit()
        self.detail.setReadOnly(True)
        self.detail.setPlaceholderText("点击左侧结果行查看该尺寸的 bbox / 测量点位 / 纠偏坐标…")
        lay.addWidget(self.detail)
        return group

    def _build_status_row(self) -> QHBoxLayout:
        row = QHBoxLayout()
        self.summary_label = QLabel("就绪")
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setTextVisible(False)

        self.export_json_btn = QPushButton("导出 JSON…")
        self.export_json_btn.clicked.connect(self._on_export_json)
        self.open_dir_btn = QPushButton("打开输出目录")
        self.open_dir_btn.clicked.connect(self._on_open_output_dir)
        self.log_btn = QPushButton("查看日志")
        self.log_btn.clicked.connect(self._on_open_log_dir)
        self._set_export_buttons_enabled(False)

        row.addWidget(self.summary_label, 1)
        row.addWidget(self.export_json_btn)
        row.addWidget(self.open_dir_btn)
        row.addWidget(self.log_btn)
        row.addWidget(self.progress)
        return row

    def _build_log_area(self) -> QPlainTextEdit:
        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setMaximumHeight(90)
        self.log_view.setPlaceholderText("运行日志…")
        return self.log_view

    # —— 槽函数 ——
    def _on_browse(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "选择 DXF 文件", "", "DXF 文件 (*.dxf);;所有文件 (*)"
        )
        if path:
            self.path_edit.setText(path)

    def _on_run(self) -> None:
        path = self.path_edit.text().strip()
        if not path:
            show_error(self, "未选择文件", "请先选择一个 .dxf 文件。")
            return
        if not Path(path).exists():
            show_error(self, "文件不存在", f"文件不存在：\n{path}")
            return

        config = WorkerConfig(
            path=path,
            tolerance=self.tol_spin.value(),
            snap_radius=self.snap_spin.value(),
            expand_insert=self.expand_check.isChecked(),
            do_blockify=self.blockify_check.isChecked(),
            clean_orphan=self.clean_check.isChecked(),
        )

        self._worker = PipelineWorker(config)
        self._worker.log_message.connect(self._append_log)
        self._worker.succeeded.connect(self._on_succeeded)
        self._worker.failed.connect(self._on_failed)
        self._worker.finished.connect(self._on_finished)

        self.run_btn.setEnabled(False)
        self._set_export_buttons_enabled(False)
        self.summary_label.setText("处理中…")
        self.progress.setRange(0, 0)  # 不确定态 busy
        self.log_view.clear()
        self._worker.start()

    def _append_log(self, message: str) -> None:
        self.log_view.appendPlainText(message)

    def _on_succeeded(self, report) -> None:
        self._report = report
        result = report.result
        self._infos = {d.handle: d for d in result.dimensions}

        self.table.set_result(result)
        self.summary_label.setText(
            f"尺寸 {result.total_dimensions} | 未挂靠 {result.unattached_count} | "
            f"警告 {len(result.warnings)} | 耗时 {report.elapsed_sec:.2f}s"
        )
        self._set_export_buttons_enabled(True)

    def _on_failed(self, message: str) -> None:
        show_error(self, "处理失败", message)

    def _on_finished(self) -> None:
        self.run_btn.setEnabled(True)
        self.progress.setRange(0, 100)
        self.progress.setValue(0)

    def _on_row_selected(self, current, _previous) -> None:
        if current is None or not current.isValid():
            return
        handle = self.table.handle_at(current.row())
        info = self._infos.get(handle)
        if info is None:
            self.detail.setPlainText("")
            return
        self.detail.setPlainText(render_detail(info))

    def _on_export_json(self) -> None:
        if self._report is None:
            return
        default_name = Path(self._report.json_path).name
        path, _ = QFileDialog.getSaveFileName(
            self, "导出 JSON", default_name, "JSON 文件 (*.json)"
        )
        if path:
            json_export.dump(self._report.result, path)

    def _on_open_output_dir(self) -> None:
        if self._report is None:
            return
        folder = Path(self._report.dxf_path).parent
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))

    def _on_open_log_dir(self) -> None:
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(Path(LOG_DIR).resolve())))

    def _set_export_buttons_enabled(self, enabled: bool) -> None:
        self.export_json_btn.setEnabled(enabled)
        self.open_dir_btn.setEnabled(enabled)


def run() -> int:
    """启动 GUI（供 main.py 调用）。"""
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    window = MainWindow()
    window.show()
    return app.exec()


__all__ = ["MainWindow", "run"]
