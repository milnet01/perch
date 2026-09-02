"""Logging configuration for Perch.

Wires a :class:`~logging.handlers.RotatingFileHandler` at
``$XDG_STATE_HOME/perch/perch.log`` (1 MB per file, two backups — matches
``docs/02-state-format.md`` §Log file) and bridges Qt's own logger into the
Python logging tree via ``qInstallMessageHandler``.

``PERCH_DEBUG=1`` bumps the console level to DEBUG. It does not relax
redaction: window titles are redacted unconditionally, and there is no
switch that turns that off — see :mod:`perch.logging_privacy`.
"""

from __future__ import annotations

import logging
import os
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

from . import paths

LOG_FORMAT = "%(asctime)s %(levelname)-7s %(name)s: %(message)s"
LOG_MAX_BYTES = 1 * 1024 * 1024
LOG_BACKUP_COUNT = 2


def _log_level() -> int:
    return logging.DEBUG if os.environ.get("PERCH_DEBUG") == "1" else logging.INFO


def configure_logging(log_path: Path | None = None) -> logging.Logger:
    """Install Perch's root logger. Idempotent — safe to call multiple times."""
    root = logging.getLogger("perch")
    root.setLevel(_log_level())

    for handler in list(root.handlers):
        root.removeHandler(handler)

    destination = log_path if log_path is not None else paths.log_file()
    paths.ensure_dir(destination.parent)

    file_handler = RotatingFileHandler(
        destination,
        maxBytes=LOG_MAX_BYTES,
        backupCount=LOG_BACKUP_COUNT,
        encoding="utf-8",
    )
    file_handler.setFormatter(logging.Formatter(LOG_FORMAT))
    root.addHandler(file_handler)

    console = logging.StreamHandler(sys.stderr)
    console.setFormatter(logging.Formatter(LOG_FORMAT))
    root.addHandler(console)

    root.propagate = False
    return root


def install_qt_bridge() -> None:
    """Forward Qt log messages into the ``perch.qt`` logger.

    Imported lazily so pure-config unit tests don't pull PySide6 in at
    collection time; this keeps ``pytest -k config`` fast on machines that
    don't yet have Qt installed globally (dev extras still install it).
    """
    from PySide6.QtCore import QtMsgType, qInstallMessageHandler

    qt_logger = logging.getLogger("perch.qt")
    level_map = {
        QtMsgType.QtDebugMsg: logging.DEBUG,
        QtMsgType.QtInfoMsg: logging.INFO,
        QtMsgType.QtWarningMsg: logging.WARNING,
        QtMsgType.QtCriticalMsg: logging.ERROR,
        QtMsgType.QtFatalMsg: logging.CRITICAL,
    }

    def handler(msg_type: QtMsgType, context: object, message: str) -> None:
        qt_logger.log(level_map.get(msg_type, logging.INFO), "%s", message)

    qInstallMessageHandler(handler)
