# -*- coding: utf-8 -*-
"""M5 轮转日志单测（T5.2）。

覆盖：按日轮转 + 保留 180 天配置、概要写盘（中文文件名）、configure 幂等
可重入、get_logger 缓存单例。
"""
from __future__ import annotations

from logging.handlers import TimedRotatingFileHandler

from app.config import LOG_RETENTION_DAYS
from app.io.logger import configure, get_logger, log_summary


def test_configure_retention_config(tmp_path):
    """配置正确：TimedRotatingFileHandler、按日轮转、保留 180 天。"""
    logger = configure(tmp_path, retention_days=LOG_RETENTION_DAYS)
    assert len(logger.handlers) == 1
    h = logger.handlers[0]
    assert isinstance(h, TimedRotatingFileHandler)
    assert h.when == "D"
    assert h.backupCount == LOG_RETENTION_DAYS == 180


def test_log_summary_writes_file(tmp_path):
    """log_summary 写盘，含中文文件名与问题统计。"""
    logger = configure(tmp_path)
    log_summary(logger, "图纸.dxf", 961, 181, ["警告1", "警告2"], 6.29)
    for h in logger.handlers:
        h.flush()

    files = list(tmp_path.glob("app.log*"))
    assert files, "日志文件未落盘"
    content = files[0].read_text(encoding="utf-8")
    assert "图纸.dxf" in content
    assert "尺寸 961" in content
    assert "未挂靠 181" in content
    assert "警告 2" in content


def test_configure_idempotent_replaces_handler(tmp_path):
    """重配到新目录：旧 handler 被替换，不累积重复输出。"""
    logger = configure(tmp_path)
    first = logger.handlers[0]
    configure(tmp_path / "sub")
    assert len(logger.handlers) == 1
    assert logger.handlers[0] is not first


def test_get_logger_cached_after_configure(tmp_path):
    """get_logger 返回已配置的单例，不重复初始化。"""
    logger = configure(tmp_path)
    assert get_logger() is logger
    assert len(logger.handlers) == 1
