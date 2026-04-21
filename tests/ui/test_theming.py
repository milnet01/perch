"""Tests for the dark / light theming bridge (M7.f).

Covers :mod:`perch.ui.theming`. The palette construction is deterministic
and unit-testable; the ``auto`` path is exercised with a monkey-patched
style-hints color-scheme so tests don't depend on the host desktop.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication, QPalette
from PySide6.QtWidgets import QApplication

from perch.ui.theming import apply_theme, resolve_effective_theme

if TYPE_CHECKING:
    from pytestqt.qtbot import QtBot


def _app() -> QApplication:
    app = QApplication.instance()
    assert isinstance(app, QApplication)
    return app


# ── resolve_effective_theme ────────────────────────────────────────────


def test_resolve_effective_theme_light_is_literal(qtbot: QtBot) -> None:
    del qtbot
    assert resolve_effective_theme("light") == "light"


def test_resolve_effective_theme_dark_is_literal(qtbot: QtBot) -> None:
    del qtbot
    assert resolve_effective_theme("dark") == "dark"


def test_resolve_effective_theme_auto_reads_color_scheme(
    qtbot: QtBot, monkeypatch: pytest.MonkeyPatch
) -> None:
    del qtbot
    hints = QGuiApplication.styleHints()
    monkeypatch.setattr(hints, "colorScheme", lambda: Qt.ColorScheme.Dark)
    assert resolve_effective_theme("auto") == "dark"
    monkeypatch.setattr(hints, "colorScheme", lambda: Qt.ColorScheme.Light)
    assert resolve_effective_theme("auto") == "light"


def test_resolve_effective_theme_auto_unknown_is_system(
    qtbot: QtBot, monkeypatch: pytest.MonkeyPatch
) -> None:
    del qtbot
    hints = QGuiApplication.styleHints()
    monkeypatch.setattr(hints, "colorScheme", lambda: Qt.ColorScheme.Unknown)
    assert resolve_effective_theme("auto") == "system"


# ── apply_theme ────────────────────────────────────────────────────────


def test_apply_theme_dark_sets_dark_palette(qtbot: QtBot) -> None:
    del qtbot
    app = _app()
    original = QPalette(app.palette())
    try:
        apply_theme(app, "dark")
        window = app.palette().color(QPalette.ColorRole.Window)
        # The dark palette's Window role is the Breeze-dark grey
        # (47, 52, 63). An untouched Fusion palette is much lighter.
        assert window.red() < 80 and window.green() < 80 and window.blue() < 80
    finally:
        app.setPalette(original)


def test_apply_theme_light_sets_light_palette(qtbot: QtBot) -> None:
    del qtbot
    app = _app()
    original = QPalette(app.palette())
    try:
        apply_theme(app, "light")
        window = app.palette().color(QPalette.ColorRole.Window)
        # Light palette's Window role is (239, 240, 241) — well above
        # 200 on every channel.
        assert window.red() > 200 and window.green() > 200 and window.blue() > 200
    finally:
        app.setPalette(original)


def test_apply_theme_auto_with_unknown_scheme_is_noop(
    qtbot: QtBot, monkeypatch: pytest.MonkeyPatch
) -> None:
    del qtbot
    app = _app()
    hints = QGuiApplication.styleHints()
    monkeypatch.setattr(hints, "colorScheme", lambda: Qt.ColorScheme.Unknown)
    original = QPalette(app.palette())
    try:
        apply_theme(app, "auto")
        # Palette unchanged — every role matches the pre-apply snapshot.
        assert app.palette().color(QPalette.ColorRole.Window) == original.color(
            QPalette.ColorRole.Window
        )
    finally:
        app.setPalette(original)


def test_apply_theme_auto_dark_applies_dark_palette(
    qtbot: QtBot, monkeypatch: pytest.MonkeyPatch
) -> None:
    del qtbot
    app = _app()
    hints = QGuiApplication.styleHints()
    monkeypatch.setattr(hints, "colorScheme", lambda: Qt.ColorScheme.Dark)
    original = QPalette(app.palette())
    try:
        apply_theme(app, "auto")
        window = app.palette().color(QPalette.ColorRole.Window)
        assert window.red() < 80
    finally:
        app.setPalette(original)


def test_apply_theme_sets_fusion_style(qtbot: QtBot) -> None:
    """An explicit light/dark override forces Fusion for cross-desktop parity.

    Skipping the post-test style restore: Qt takes ownership of the style
    object the application currently holds, so calling ``app.setStyle(new)``
    destroys the previous wrapper. Tests that care about the starting style
    snapshot the name, not the object.
    """
    del qtbot
    app = _app()
    apply_theme(app, "dark")
    assert app.style().objectName().lower() == "fusion"
