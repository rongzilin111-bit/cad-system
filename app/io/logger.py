# -*- coding: utf-8 -*-
"""M5 轮转日志（保留 ≥180 天）。

T5.2 —— `TimedRotatingFileHandler`（按日轮转）记录检测时间 / 文件名 / 问题
统计；`backupCount = LOG_RETENTION_DAYS`(180) 保证日志按日保留 ≥180 天。
本地写盘、不联网（ARCHITECTURE.md §9.2）。

用法：

    from app.io import logger as app_logger
    log = app_logger.get_logger()                 # 惰性初始化 + 缓存单例
    log.info("检测完成：%s | 未挂靠 %d", file, n)  # 或走 log_summary 快捷函数

约定：编码 UTF-8（中文文件名 / 图层无损）；`logger.propagate=False` 避免与根
logger 重复输出；`configure()` 幂等可重入（先清旧 handler 再挂新），供测试
与批量模式逐文件重定向日志目录。
"""
from __future__ import annotations

import logging
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path
from typing import Sequence, Union

from app.config import LOG_DIR, LOG_RETENTION_DAYS

_LOGGER_NAME = "dimension_reconstruct"
_LOG_FILENAME = "app.log"


def configure(
    log_dir: Union[str, Path] = LOG_DIR,
    retention_days: int = LOG_RETENTION_DAYS,
    name: str = _LOGGER_NAME,
) -> logging.Logger:
    """(重)配置应用 logger：按日轮转 + 保留 `retention_days` 天，返回 logger。

    幂等可重入：先清空旧 handler 再挂新 handler，避免重复输出；测试可传
    `tmp_path` 隔离日志目录。
    """
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    logger.propagate = False
    for h in list(logger.handlers):
        logger.removeHandler(h)
        try:
            h.close()
        except Exception:  # noqa: BLE001 —— 关闭失败不影响重配
            pass

    log_dir = Path(log_dir)
    log_dir.mkdir(parents=True, exist_ok=True)
    handler = TimedRotatingFileHandler(
        log_dir / _LOG_FILENAME,
        when="D",
        interval=1,
        backupCount=retention_days,
        encoding="utf-8",
    )
    handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
    logger.addHandler(handler)
    return logger


def get_logger() -> logging.Logger:
    """返回应用 logger（惰性初始化 + 缓存：首次调用按默认配置落 `logs/app.log`）。"""
    logger = logging.getLogger(_LOGGER_NAME)
    if not logger.handlers:
        configure()
    return logger


def log_summary(
    logger: logging.Logger,
    file: str,
    total: int,
    unattached: int,
    warnings: Sequence[str],
    elapsed_sec: float,
) -> None:
    """记录一次检测的概要（文件名 + 问题统计 + 耗时），供日志可查（§9.2）。"""
    logger.info(
        "检测完成 | 文件 %s | 尺寸 %d | 未挂靠 %d | 警告 %d | 耗时 %.2fs",
        file, total, unattached, len(warnings), elapsed_sec,
    )


__all__ = ["configure", "get_logger", "log_summary"]
