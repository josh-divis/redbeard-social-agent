"""
Centralized logging for the agent.

Uses rotating file handlers so a Pi's SD/NVMe disk does not fill from logs,
plus a console handler for interactive CLI use.
"""

from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

from agent.config import AppConfig


_CONFIGURED = False


def setup_logging(cfg: AppConfig, *, name: str = "redbeard") -> logging.Logger:
    """
    Configure root app logger once. Safe to call multiple times.
    Returns a child logger for the caller.
    """
    global _CONFIGURED

    logger = logging.getLogger(name)
    if _CONFIGURED:
        return logger

    level_name = (cfg.log_level or "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)
    logger.setLevel(level)

    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Console
    console = logging.StreamHandler(sys.stdout)
    console.setLevel(level)
    console.setFormatter(formatter)
    logger.addHandler(console)

    # Rotating file
    log_path = Path(cfg.log_file)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    file_handler = RotatingFileHandler(
        log_path,
        maxBytes=cfg.log_max_bytes,
        backupCount=cfg.log_backup_count,
        encoding="utf-8",
    )
    file_handler.setLevel(level)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    # Quiet noisy libraries
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("openai").setLevel(logging.WARNING)
    logging.getLogger("werkzeug").setLevel(logging.INFO)

    _CONFIGURED = True
    logger.debug("Logging configured → file=%s level=%s", log_path, level_name)
    return logger


def get_logger(name: str = "redbeard") -> logging.Logger:
    """Get a named logger (call setup_logging first in entrypoints)."""
    return logging.getLogger(name)
