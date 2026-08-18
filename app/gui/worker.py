# -*- coding: utf-8 -*-
"""M6 后台处理线程（QThread）。

T6.1 —— 在后台线程执行 `run_pipeline`，避免 UI 冻结；进度以日志文本流信号
`log_message` 回主线程，完成 / 失败分别以 `succeeded` / `failed` 回主线程。

流程（全部在后台，不阻塞主线程）：
    run_pipeline → 另存 DXF → 写 JSON → 记日志 → 发出 `RunReport`（只含
    纯 dataclass 的 `Result`，**不**携带 ezdxf `doc`/`LoadedDrawing` 大对象，
    跨线程搬运开销小）；处理结束 `del` 大对象 + `gc.collect()` 释放内存（§9.2）。

异常一律捕获，转为 `failed(str)` 信号，绝不导致程序崩溃（§6.2/§9.2）。
"""
from __future__ import annotations

import gc
import time

from PySide6.QtCore import QThread, Signal

from app.core.pipeline import run_pipeline
from app.gui.presentation import RunReport, WorkerConfig, output_json_path
from app.io import dxf_export, json_export
from app.io import logger as app_logger


class PipelineWorker(QThread):
    """后台执行一条文件流水线（判定 → 提取 → 重构 → 标准化 → 输出）。"""

    log_message = Signal(str)      # 进度日志文本（回主线程日志区）
    succeeded = Signal(object)     # 完成，携带 RunReport
    failed = Signal(str)           # 失败，携带错误描述

    def __init__(self, config: WorkerConfig, parent=None):
        super().__init__(parent)
        self._config = config

    def run(self) -> None:  # noqa: D401 —— QThread 约定入口
        try:
            self.log_message.emit(f"开始处理：{self._config.path}")
            t0 = time.perf_counter()

            out = run_pipeline(
                self._config.path,
                tolerance=self._config.tolerance,
                snap_radius=self._config.snap_radius,
                expand_insert=self._config.expand_insert,
                layer=self._config.layer,
                do_blockify=self._config.do_blockify,
                clean_orphan=self._config.clean_orphan,
            )
            result = out.result
            self.log_message.emit(
                f"检测完成：尺寸 {result.total_dimensions} / "
                f"未挂靠 {result.unattached_count} / 警告 {len(result.warnings)}"
            )

            # 另存 DXF（GBK 无损；输出路径由 pipeline 派生，不覆盖原文件）。
            dxf_path = result.output_dxf
            dxf_export.save_document(out.doc, dxf_path)
            self.log_message.emit(f"已另存 DXF：{dxf_path}")

            # 导出 JSON。
            json_path = output_json_path(self._config.path)
            json_export.dump(result, json_path)
            self.log_message.emit(f"已导出 JSON：{json_path}")

            elapsed = time.perf_counter() - t0
            app_logger.log_summary(
                app_logger.get_logger(),
                result.file,
                result.total_dimensions,
                result.unattached_count,
                result.warnings,
                elapsed,
            )
            self.log_message.emit(f"完成，耗时 {elapsed:.2f}s")

            self.succeeded.emit(
                RunReport(
                    result=result,
                    dxf_path=dxf_path,
                    json_path=json_path,
                    elapsed_sec=elapsed,
                )
            )
        except Exception as exc:  # noqa: BLE001 —— 任何异常转失败信号，不崩溃
            self.failed.emit(f"{type(exc).__name__}: {exc}")
        finally:
            # 释放 ezdxf 大对象（§9.2「每文件处理完 del doc + gc.collect()」）。
            gc.collect()


__all__ = ["PipelineWorker"]
