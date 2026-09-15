"""Central logging setup: console handler + rotating file handler."""

from __future__ import annotations

import logging
import os
from logging.handlers import RotatingFileHandler

_LOGGER_NAME = "ssc_scraper"


def setup_logging(logs_dir: str = "logs", level: int = logging.INFO) -> logging.Logger:
    """Configure the root package logger once; return it."""
    os.makedirs(logs_dir, exist_ok=True)
    logger = logging.getLogger(_LOGGER_NAME)
    if logger.handlers:  # already configured
        return logger
    logger.setLevel(level)
    fmt = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    console = logging.StreamHandler()
    console.setFormatter(fmt)
    logger.addHandler(console)

    file_handler = RotatingFileHandler(
        os.path.join(logs_dir, "ssc_bot.log"),
        maxBytes=5_000_000,
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setFormatter(fmt)
    logger.addHandler(file_handler)
    logger.propagate = False
    return logger


def get_logger(child: str) -> logging.Logger:
    """Get a namespaced child logger (e.g. ssc_scraper.http)."""
    return logging.getLogger(f"{_LOGGER_NAME}.{child}")
