"""Application logging configuration."""

from __future__ import annotations

import logging
import os
import sys
from datetime import datetime
from pathlib import Path

LOG_FILENAME = "sha256_generator.log"


def get_log_dir() -> Path:
    """Return a writable directory for application log files."""
    if getattr(sys, "frozen", False):
        log_dir = Path(os.environ.get("APPDATA", str(Path.home()))) / "SHA256 Generator"
        log_dir.mkdir(parents=True, exist_ok=True)
        return log_dir
    return Path(__file__).resolve().parent


def setup_logging(log_dir: Path | None = None) -> logging.Logger:
    """Configure and return the application logger.

    Args:
        log_dir: Directory for the log file. Defaults to an app-appropriate path.

    Returns:
        Configured logger instance.
    """
    if log_dir is None:
        log_dir = get_log_dir()

    log_path = log_dir / LOG_FILENAME

    logger = logging.getLogger("sha256_generator")
    logger.setLevel(logging.DEBUG)

    if logger.handlers:
        return logger

    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    file_handler = logging.FileHandler(log_path, encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)

    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

    logger.info("Application started at %s", datetime.now().isoformat())
    logger.info("Log file: %s", log_path)

    return logger
