"""Tests for the dark / light theming bridge (M7.f).

Covers :mod:`perch.ui.theming`. The palette construction is deterministic
and unit-testable; the ``auto`` path is exercised with a monkey-patched
style-hints color-scheme so tests don't depend on the host desktop.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import TYPE_CHECKING

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication, QPalette
from PySide6.QtWidgets import QApplication

from perch.ui import theming
from perch.ui.theming import apply_theme, resolve_effective_theme

if TYPE_CHECKING:
    from pytestqt.qtbot import QtBot


def _app() -> QApplication:
    app = QApplication.instance()
    assert isinstance(app, QApplication)
    return app


@pytest.fixture(autouse=True)
def _restore_theme(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Start each test from the platform theme and leave it there.

    ``apply_theme`` keeps module state (``_platform_style``,
    ``_overridden``) and changes the session QApplication's style and
    palette, so without this each test inherits the last one's theme.
    """
    app = _app()
    style, palette = app.style().name(), QPalette(app.palette())
    monkeypatch.setattr(theming, "_platform_style", None)
    monkeypatch.setattr(theming, "_overridden", False)
    yield
    app.setStyle(style)
    app.setPalette(palette)


# ── resolve_effective_theme ────────────────────────────────────────────


def test_resolve_effective_theme_light_is_literal(qtbot: QtBot) -> None:
    del qtbot
    assert resolve_effective_theme("light") == "light"


def test_resolve_effective_theme_dark_is_literal(qtbot: QtBot) -> None:
    del qtbot
    assert resolve_effective_theme("dark") == "dark"


@pytest.mark.parametrize(
    "scheme",
    [Qt.ColorScheme.Dark, Qt.ColorScheme.Light, Qt.ColorScheme.Unknown],
)
def test_resolve_effective_theme_auto_is_always_system(
    qtbot: QtBot, monkeypatch: pytest.MonkeyPatch, scheme: Qt.ColorScheme
) -> None:
    """PERC-0058: Plasma 6 and GNOME report Dark or Light, never Unknown,
    so reading the scheme meant ``auto`` overrode Breeze and any
    high-contrast palette. ``auto`` now always defers to the platform."""
    del qtbot
    hints = QGuiApplication.styleHints()
    monkeypatch.setattr(hints, "colorScheme", lambda: scheme)
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


def test_apply_theme_auto_with_dark_scheme_leaves_platform_alone(
    qtbot: QtBot, monkeypatch: pytest.MonkeyPatch
) -> None:
    del qtbot
    app = _app()
    hints = QGuiApplication.styleHints()
    monkeypatch.setattr(hints, "colorScheme", lambda: Qt.ColorScheme.Dark)
    style_before = app.style().name()
    original = QPalette(app.palette())
    apply_theme(app, "auto")
    assert app.style().name() == style_before
    assert app.palette().color(QPalette.ColorRole.Window) == original.color(
        QPalette.ColorRole.Window
    )


def test_apply_theme_auto_after_dark_restores_platform_palette(
    qtbot: QtBot,
) -> None:
    """A live dark → auto switch on Apply must hand the desktop back its
    palette, not leave the forced one in place until a restart."""
    del qtbot
    app = _app()
    platform_window = QPalette(app.palette()).color(QPalette.ColorRole.Window)
    apply_theme(app, "dark")
    assert app.palette().color(QPalette.ColorRole.Window) != platform_window
    apply_theme(app, "auto")
    assert app.palette().color(QPalette.ColorRole.Window) == platform_window


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
