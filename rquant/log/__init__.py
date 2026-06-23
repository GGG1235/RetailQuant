"""
rquant.log — 统一日志模块（基于 loguru）

用法：
    from rquant.log import info, warning, error, debug, init_logging, get_recent_logs

    init_logging()                         # 应用启动时调用一次
    info("mq", "启动 worker")             # 模块名 + 消息
    warning("pool", "迁移失败")
    error("strategy", f"异常: {e}")
    get_recent_logs(50)                   # 获取最近 N 条日志（Web 展示用）

设计：
  - 仅本模块直接 import loguru，其他模块通过本模块的简单函数打日志
  - 三输出：stderr（控制台/waitress） + 落盘文件（自动轮转） + 内存 ring buffer（Web 展示）
  - init_logging 幂等，可多次调用
"""

from __future__ import annotations

import sys
import threading
from collections import deque
from pathlib import Path
from typing import TYPE_CHECKING

from loguru import logger

if TYPE_CHECKING:
    from loguru import Message

from config import config

# ============================================================
# 路径
# ============================================================

_LOG_DIR: Path = config.project_root / "logs"
_LOG_FILE: Path = _LOG_DIR / "rquant.log"

# ============================================================
# 内存 Ring Buffer（Web 前端消费）
# ============================================================

_MAX_LOG_ENTRIES: int = config.business.max_log_entries
_log_buffer: deque[dict] = deque(maxlen=_MAX_LOG_ENTRIES)
_log_lock = threading.Lock()

# ============================================================


def _ring_sink(message: Message) -> None:
    """loguru sink：从 Message 提取结构化数据写入 ring buffer"""
    try:
        record = message.record
        entry = {
            "ts": record["time"].strftime("%H:%M:%S"),
            "level": record["level"].name,
            "logger": record["extra"].get("module", record["name"]),
            "module": record["extra"].get("module", record["name"]),
            "message": record["message"],
        }
        with _log_lock:
            _log_buffer.append(entry)
    except Exception:
        pass  # 日志系统自身不能崩


# ============================================================
# 初始化状态
# ============================================================

_initialized = False
_init_lock = threading.Lock()


# ============================================================
# 公开 API
# ============================================================


def init_logging(level: str = "INFO") -> None:
    """初始化日志系统（幂等）

    应在应用启动早期调用一次（如 app_factory.create_app() 中）。
    """
    global _initialized
    with _init_lock:
        if _initialized:
            return

        # 移除 loguru 默认 handler
        logger.remove()

        # 确保日志目录存在
        _LOG_DIR.mkdir(parents=True, exist_ok=True)

        # sink 1: stderr（控制台 / waitress 可见，带颜色）
        logger.add(
            sys.stderr,
            format=(
                "<green>{time:HH:mm:ss}</green> | "
                "<level>{level}</level> | "
                "<cyan>{extra[module]}</cyan> | "
                "<level>{message}</level>"
            ),
            level=level,
            colorize=True,
        )

        # sink 2: 落盘文件（纯文本，自动轮转 + 压缩 + 清理）
        logger.add(
            _LOG_FILE,
            format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level} | {extra[module]} | {message}",
            level=level,
            rotation="10 MB",  # 单文件超过 10 MB 轮转
            retention="30 days",  # 保留 30 天
            compression="zip",  # 轮转后压缩为 zip
            encoding="utf-8",
            enqueue=True,  # 多进程/线程安全写入
        )

        # sink 3: 内存 ring buffer
        logger.add(_ring_sink, level=level)

        _initialized = True


def info(module: str, msg: str) -> None:
    """INFO 级别日志"""
    logger.bind(module=module).info(msg)


def warning(module: str, msg: str) -> None:
    """WARNING 级别日志"""
    logger.bind(module=module).warning(msg)


def error(module: str, msg: str) -> None:
    """ERROR 级别日志"""
    logger.bind(module=module).error(msg)


def debug(module: str, msg: str) -> None:
    """DEBUG 级别日志"""
    logger.bind(module=module).debug(msg)


def get_recent_logs(limit: int = 50) -> list[dict]:
    """返回最近 limit 条日志（最新在前），供 Web 前端消费"""
    with _log_lock:
        items = list(_log_buffer)
    items.reverse()
    return items[:limit]
