"""
统一日志模块
基于 structlog 风格，支持控制台 + 文件双输出
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from datetime import datetime

from config import PROJECT_ROOT


# 日志目录
LOG_DIR = PROJECT_ROOT / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)

# 日志格式
CONSOLE_FORMAT = "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s"
FILE_FORMAT = "%(asctime)s | %(levelname)-7s | %(name)s | %(filename)s:%(lineno)d | %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def setup_logging(
    level: str = "INFO",
    log_to_file: bool = True,
) -> logging.Logger:
    """初始化日志系统"""
    root_logger = logging.getLogger("multi_agent")
    root_logger.setLevel(getattr(logging, level.upper(), logging.INFO))
    root_logger.handlers.clear()

    # 控制台处理器
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.DEBUG)
    console_handler.setFormatter(logging.Formatter(CONSOLE_FORMAT, DATE_FORMAT))
    root_logger.addHandler(console_handler)

    # 文件处理器
    if log_to_file:
        today = datetime.now().strftime("%Y%m%d")
        file_handler = logging.FileHandler(
            LOG_DIR / f"agent_{today}.log",
            encoding="utf-8",
        )
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(logging.Formatter(FILE_FORMAT, DATE_FORMAT))
        root_logger.addHandler(file_handler)

    # 降低第三方库日志级别
    for lib in ("httpx", "httpcore", "openai", "urllib3", "asyncio", "websockets"):
        logging.getLogger(lib).setLevel(logging.WARNING)

    return root_logger


def get_logger(name: str) -> logging.Logger:
    """获取模块级 logger"""
    return logging.getLogger(f"multi_agent.{name}")


# ── 以下为 v2 增强工具函数 ──────────────────────────
# ============================================================
# @REAL_CODE: ensure_directory 是纯工具函数，无需替换
# 来自: multi_agent_system_2.0/utils/logger.py
# 优先级: LOW (已完成)
# ============================================================


def ensure_directory(path: str) -> str:
    """确保目录存在，递归创建"""
    directory = Path(path)
    directory.mkdir(parents=True, exist_ok=True)
    return str(directory)


# 模块初始化时自动 setup
_default_logger = setup_logging()
