"""Shared pytest fixtures.

Each test gets its own XDG tree under ``tmp_path`` so the real user's
``~/.config/perch`` is never touched.
"""

from __future__ import annotations

import logging
import os
from collections.abc import Iterator
from pathlib import Path

import pytest

# Force Qt's offscreen QPA platform before any pytest-qt fixture creates a
# QApplication. Without this, every test using qtbot/QApplication briefly
# composites a real top-level window — visible to whatever desktop is hosting
# the runner. `setdefault` lets a CI override (e.g. QT_QPA_PLATFORM=minimal)
# still win. This runs at conftest import (collection time), before any
# fixture constructs QApplication — none of the imports above pull in Qt.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture
def xdg_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    """Point ``$XDG_*_HOME`` at a fresh tmp tree.

    Yields the tmp root; individual subdirs are created lazily on use.
    """
    (tmp_path / "config").mkdir()
    (tmp_path / "state").mkdir()
    (tmp_path / "cache").mkdir()
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    # Never let a test pick up DEBUG from the host environment.
    monkeypatch.delenv("PERCH_DEBUG", raising=False)
    yield tmp_path


@pytest.fixture(autouse=True)
def _restore_perch_logger(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Put the process-wide ``perch`` logger back after every test.

    ``configure_logging`` (directly, or through ``cli()``) swaps its
    handlers, raises its level and stops it propagating. Left in place,
    that silences ``caplog`` for every later test and keeps an earlier
    test's log file open. ``cli()`` also installs a process-wide Qt
    message handler, which no test here asks about.
    """
    logger = logging.getLogger("perch")
    handlers, level, propagate = list(logger.handlers), logger.level, logger.propagate
    monkeypatch.setattr("perch.__main__.install_qt_bridge", lambda: None)
    yield
    for handler in logger.handlers:
        if handler not in handlers:
            handler.close()
    logger.handlers[:] = handlers
    logger.setLevel(level)
    logger.propagate = propagate
