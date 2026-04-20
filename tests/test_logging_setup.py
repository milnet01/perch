"""Logging wiring: rotating file handler and PERCH_DEBUG."""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

import pytest

from perch.logging_setup import LOG_BACKUP_COUNT, LOG_MAX_BYTES, configure_logging


def test_configure_logging_installs_rotating_file_handler(tmp_path: Path) -> None:
    log_path = tmp_path / "perch.log"
    logger = configure_logging(log_path=log_path)

    file_handlers = [h for h in logger.handlers if isinstance(h, RotatingFileHandler)]
    assert len(file_handlers) == 1
    handler = file_handlers[0]
    assert handler.maxBytes == LOG_MAX_BYTES == 1 * 1024 * 1024
    assert handler.backupCount == LOG_BACKUP_COUNT == 2


def test_configure_logging_is_idempotent(tmp_path: Path) -> None:
    log_path = tmp_path / "perch.log"
    configure_logging(log_path=log_path)
    logger = configure_logging(log_path=log_path)
    # Exactly one file handler + one stream handler, not doubled.
    assert sum(isinstance(h, RotatingFileHandler) for h in logger.handlers) == 1


def test_configure_logging_creates_parent_dir(tmp_path: Path) -> None:
    log_path = tmp_path / "nested" / "perch.log"
    assert not log_path.parent.exists()
    configure_logging(log_path=log_path)
    assert log_path.parent.is_dir()


def test_logs_written_to_file(tmp_path: Path) -> None:
    log_path = tmp_path / "perch.log"
    logger = configure_logging(log_path=log_path)
    logger.info("hello from test")
    for handler in logger.handlers:
        handler.flush()
    assert "hello from test" in log_path.read_text(encoding="utf-8")


def test_perch_debug_env_sets_level(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("PERCH_DEBUG", "1")
    logger = configure_logging(log_path=tmp_path / "perch.log")
    assert logger.level == logging.DEBUG
