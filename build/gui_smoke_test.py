# -*- coding: utf-8 -*-
"""M6 GUI 冒烟测试（offscreen 自动化驱动）。

在无显示器环境下用 `QT_QPA_PLATFORM=offscreen` 真实驱动 Qt 主窗口，验证：
    U1 界面装配 / U2 未选·不存在 / U3 真实大图端到端 / U4 点行详情 /
    U5 导出落盘 / U7 损坏文件友好提示。

用法：
    QT_QPA_PLATFORM=offscreen python build/gui_smoke_test.py <测试文件.dxf>

不是 pytest 用例（pytest 在无 Qt 环境也需跑），而是独立冒烟脚本，结果打印
到 stdout 并写 `build/gui_smoke_result.txt`，非零退出码 = 有失败项。
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

# 必须在导入任何 PySide6 之前设 offscreen，避免在无显示器机器上崩溃。
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

# 项目根加入 sys.path，保证 `app.*` 可导入。
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from PySide6.QtCore import QEventLoop, QTimer  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from app.gui import dialogs, main_window  # noqa: E402
from app.gui.main_window import MainWindow  # noqa: E402

# —— 收集器：拦截模态弹窗与文件对话框，避免 offscreen 下阻塞 ——
_error_calls: list[tuple[str, str]] = []
_info_calls: list[tuple[str, str]] = []


def _fake_error(_parent, title, message):
    _error_calls.append((title, message))


def _fake_info(_parent, title, message):
    _info_calls.append((title, message))


def _wait_worker(window: MainWindow, timeout_ms: int = 120000) -> None:
    """起事件循环，直到 worker 的 finished 信号（跨线程 queued 信号需要泵循环）。"""
    loop = QEventLoop()
    window._worker.finished.connect(loop.quit)
    QTimer.singleShot(timeout_ms, loop.quit)
    loop.exec()


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print("用法：python build/gui_smoke_test.py <测试文件.dxf>")
        return 2
    dxf_path = argv[1]

    # 拦截模态弹窗（真实驱动控件逻辑，但不真弹框）。
    # 注意：main_window 用 `from app.gui.dialogs import show_error` 直接绑定，
    # 必须 patch main_window 命名空间里的名字，否则 _on_run/_on_failed 仍弹真模态框。
    dialogs.show_error = _fake_error
    dialogs.show_info = _fake_info
    main_window.show_error = _fake_error
    main_window.show_info = _fake_info

    app = QApplication.instance() or QApplication([])
    results: list[tuple[str, bool, str]] = []

    def check(name: str, ok: bool, note: str = "") -> None:
        results.append((name, ok, note))

    # ---- U1 界面装配 ----
    w = MainWindow()
    check("U1 窗口标题", w.windowTitle() == "未挂靠尺寸标注识别与测量点位重构系统")
    check("U1 路径输入框+浏览+开始处理",
          hasattr(w, "path_edit") and hasattr(w, "run_btn"))
    check("U1 阈值默认 0.01", abs(w.tol_spin.value() - 0.01) < 1e-9)
    check("U1 吸附半径默认 50", abs(w.snap_spin.value() - 50.0) < 1e-9)
    check("U1 三个复选框存在",
          hasattr(w, "expand_check") and hasattr(w, "blockify_check") and hasattr(w, "clean_check"))
    check("U1 块标准化默认勾选", w.blockify_check.isChecked())
    check("U1 清理孤儿块默认不勾选", not w.clean_check.isChecked())
    check("U1 表格/详情/日志/进度存在",
          hasattr(w, "table") and hasattr(w, "detail")
          and hasattr(w, "log_view") and hasattr(w, "progress"))
    check("U1 导出/打开目录初始灰",
          not w.export_json_btn.isEnabled() and not w.open_dir_btn.isEnabled())

    # ---- U2 未选文件 / 文件不存在 ----
    _error_calls.clear()
    w.path_edit.setText("")
    w._on_run()
    check("U2 未选文件弹错", len(_error_calls) == 1 and "未选择文件" in _error_calls[0][0],
          str(_error_calls))

    _error_calls.clear()
    w.path_edit.setText(str(Path(dxf_path).parent / "不存在的文件.dxf"))
    w._on_run()
    check("U2 不存在弹错", len(_error_calls) == 1 and "文件不存在" in _error_calls[0][0],
          str(_error_calls))

    # ---- U3 真实大图端到端 ----
    _error_calls.clear()
    w.path_edit.setText(dxf_path)
    w._on_run()
    _wait_worker(w)
    check("U3 处理无错误弹框", len(_error_calls) == 0, str(_error_calls))
    rows = w.table.row_count()
    summary = w.summary_label.text()
    check("U3 表格 961 行", rows == 961, f"实际 {rows} 行")
    check("U3 汇总含 961/181", "尺寸 961" in summary and "未挂靠 181" in summary, summary)
    check("U3 导出按钮变亮", w.export_json_btn.isEnabled() and w.open_dir_btn.isEnabled())
    log_text = w.log_view.toPlainText()
    check("U3 日志含完成", "完成" in log_text and "已另存 DXF" in log_text
          and "已导出 JSON" in log_text, log_text[-200:])
    report = w._report
    check("U3 结果报告存在", report is not None)
    if report is not None:
        check("U3 另存 DXF 落盘", Path(report.dxf_path).exists(), report.dxf_path)
        check("U3 JSON 落盘", Path(report.json_path).exists(), report.json_path)
        check("U3 未挂靠数=181", report.result.unattached_count == 181,
              str(report.result.unattached_count))

    # ---- U4 点行看详情 ----
    # 找第一行未挂靠的 handle，点选后应渲染详情。
    model_rows = w.table._model._rows
    unattached_handle = next((r["handle"] for r in model_rows if r["unattached"]), None)
    if unattached_handle is not None:
        row_idx = [r["handle"] for r in model_rows].index(unattached_handle)
        w.table.selectRow(row_idx)
        app.processEvents()
        detail = w.detail.toPlainText()
        check("U4 详情含句柄", unattached_handle in detail)
        check("U4 详情含未挂靠:是", "未挂靠: 是" in detail)
        check("U4 详情含块名", "Dim_Reconstruct_" in detail)
    else:
        check("U4 存在未挂靠行", False, "无未挂靠行")

    # ---- U7 损坏文件友好提示 ----
    bad_path = Path(dxf_path).with_name("bad_smoke.dxf")
    bad_path.write_text("this is not a dxf file at all\n", encoding="utf-8")
    _error_calls.clear()
    w.path_edit.setText(str(bad_path))
    w._on_run()
    _wait_worker(w)
    check("U7 损坏文件弹错", len(_error_calls) == 1 and "处理失败" in _error_calls[0][0],
          str(_error_calls))
    check("U7 窗口仍在/运行按钮恢复", w.run_btn.isEnabled())
    bad_path.unlink(missing_ok=True)

    # ---- 汇总输出 ----
    failed = [r for r in results if not r[1]]
    lines = ["=" * 62, "M6 GUI 冒烟测试结果（offscreen 自动化）", "=" * 62]
    for name, ok, note in results:
        mark = "通过" if ok else "失败"
        suffix = f"  —— {note}" if note and not ok else ""
        lines.append(f"  [{mark}] {name}{suffix}")
    lines.append("-" * 62)
    lines.append(f"  通过 {len(results) - len(failed)} / {len(results)}")
    lines.append("=" * 62)
    report_text = "\n".join(lines)
    print(report_text)
    (PROJECT_ROOT / "build" / "gui_smoke_result.txt").write_text(
        report_text + "\n", encoding="utf-8")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
