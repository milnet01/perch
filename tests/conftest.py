"""Shared pytest fixtures.

Each test gets its own XDG tree under ``tmp_path`` so the real user's
``~/.config/perch`` is never touched.
"""

from __future__ import annotations

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
    # Never let a test accidentally enable DEBUG or title-logging from the
    # host environment.
    monkeypatch.delenv("PERCH_DEBUG", raising=False)
    monkeypatch.delenv("PERCH_LOG_TITLES", raising=False)
    yield tmp_path
