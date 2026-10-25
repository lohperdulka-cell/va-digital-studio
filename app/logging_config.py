"""Structured logging setup: rotating file handler plus console output."""

from __future__ import annotations

import logging
import logging.handlers
import sys

from app.config import settings

_CONFIGURED = False

_LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def setup_logging() -> None:
    """Idempotently configure the root logger (5 MB x 5 files, per requirements)."""
    global _CONFIGURED
    if _CONFIGURED:
        return

    settings.log_path.mkdir(parents=True, exist_ok=True)
    log_file = settings.log_path / "app.log"

    formatter = logging.Formatter(_LOG_FORMAT, datefmt=_DATE_FORMAT)

    file_handler = logging.handlers.RotatingFileHandler(
        log_file,
        maxBytes=settings.log_max_bytes,
        backupCount=settings.log_backup_count,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)

    root = logging.getLogger()
    root.setLevel(settings.log_level.upper())
    root.handlers.clear()
    root.addHandler(file_handler)
    root.addHandler(console_handler)

    # Uvicorn access logs duplicate our own request logging.
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    # httpx logs every OAuth request at INFO; keep it quieter.
    logging.getLogger("httpx").setLevel(logging.WARNING)

    _CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
