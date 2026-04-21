"""Palette + style application for Perch's dark/light theming (M7.f).

Per ``[general].theme`` (``"auto" | "light" | "dark"`` — see
:file:`docs/08-ui.md` §Config dialog):

* ``"auto"`` (default) defers to the platform. Qt 6.5+ reads
  ``QGuiApplication.styleHints().colorScheme()`` and we honour whatever
  it returns — no palette override, no style override. On Plasma with
  system dark mode this is the path that lets the Breeze-Dark style pass
  through untouched.
* ``"light"`` forces Fusion + a hand-built light palette so the dialog
  looks right on a host whose desktop defaulted to dark (GNOME on Wayland
  when the user has Adwaita-Dark, Plasma with a custom colour scheme).
* ``"dark"`` forces Fusion + a hand-built dark palette for the symmetric
  case.

The palettes are deliberately conservative: they match the colours
Plasma's Breeze-Dark / Breeze-Light ships with, which most users will
already have as muscle memory. Qt's default Fusion palette is too
washed-out for serious use, so we override every role explicitly.
"""

from __future__ import annotations

import logging
from typing import Literal

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QGuiApplication, QPalette
from PySide6.QtWidgets import QApplication, QStyleFactory

log = logging.getLogger(__name__)


Theme = Literal["auto", "light", "dark"]


def _dark_palette() -> QPalette:
    """Breeze-Dark inspired palette."""
    p = QPalette()
    p.setColor(QPalette.ColorRole.Window, QColor(47, 52, 63))
    p.setColor(QPalette.ColorRole.WindowText, QColor(239, 240, 241))
    p.setColor(QPalette.ColorRole.Base, QColor(35, 38, 46))
    p.setColor(QPalette.ColorRole.AlternateBase, QColor(47, 52, 63))
    p.setColor(QPalette.ColorRole.ToolTipBase, QColor(35, 38, 46))
    p.setColor(QPalette.ColorRole.ToolTipText, QColor(239, 240, 241))
    p.setColor(QPalette.ColorRole.Text, QColor(239, 240, 241))
    p.setColor(QPalette.ColorRole.Button, QColor(47, 52, 63))
    p.setColor(QPalette.ColorRole.ButtonText, QColor(239, 240, 241))
    p.setColor(QPalette.ColorRole.BrightText, QColor(255, 85, 85))
    p.setColor(QPalette.ColorRole.Highlight, QColor(61, 142, 201))
    p.setColor(QPalette.ColorRole.HighlightedText, QColor(255, 255, 255))
    p.setColor(QPalette.ColorRole.Link, QColor(41, 128, 185))
    p.setColor(QPalette.ColorRole.LinkVisited, QColor(127, 140, 141))
    # Disabled group — the Text and ButtonText roles are what the user
    # actually sees in disabled fields; the rest inherit.
    disabled = QPalette.ColorGroup.Disabled
    p.setColor(disabled, QPalette.ColorRole.Text, QColor(127, 140, 141))
    p.setColor(disabled, QPalette.ColorRole.ButtonText, QColor(127, 140, 141))
    p.setColor(disabled, QPalette.ColorRole.WindowText, QColor(127, 140, 141))
    return p


def _light_palette() -> QPalette:
    """Breeze-Light inspired palette."""
    p = QPalette()
    p.setColor(QPalette.ColorRole.Window, QColor(239, 240, 241))
    p.setColor(QPalette.ColorRole.WindowText, QColor(35, 38, 41))
    p.setColor(QPalette.ColorRole.Base, QColor(252, 252, 252))
    p.setColor(QPalette.ColorRole.AlternateBase, QColor(247, 247, 247))
    p.setColor(QPalette.ColorRole.ToolTipBase, QColor(35, 38, 41))
    p.setColor(QPalette.ColorRole.ToolTipText, QColor(239, 240, 241))
    p.setColor(QPalette.ColorRole.Text, QColor(35, 38, 41))
    p.setColor(QPalette.ColorRole.Button, QColor(239, 240, 241))
    p.setColor(QPalette.ColorRole.ButtonText, QColor(35, 38, 41))
    p.setColor(QPalette.ColorRole.BrightText, QColor(218, 68, 83))
    p.setColor(QPalette.ColorRole.Highlight, QColor(61, 142, 201))
    p.setColor(QPalette.ColorRole.HighlightedText, QColor(255, 255, 255))
    p.setColor(QPalette.ColorRole.Link, QColor(41, 128, 185))
    p.setColor(QPalette.ColorRole.LinkVisited, QColor(127, 140, 141))
    disabled = QPalette.ColorGroup.Disabled
    p.setColor(disabled, QPalette.ColorRole.Text, QColor(160, 160, 160))
    p.setColor(disabled, QPalette.ColorRole.ButtonText, QColor(160, 160, 160))
    p.setColor(disabled, QPalette.ColorRole.WindowText, QColor(160, 160, 160))
    return p


def resolve_effective_theme(theme: Theme) -> Literal["light", "dark", "system"]:
    """Map ``[general].theme`` to the concrete variant we should apply.

    ``"auto"`` resolves to ``"light"`` / ``"dark"`` by reading
    :meth:`QStyleHints.colorScheme` (Qt 6.5+). When the platform reports
    :attr:`Qt.ColorScheme.Unknown` we hand the caller ``"system"`` as a
    signal to leave the palette untouched — the platform style picks a
    palette on its own (this is the right call on KDE, where Breeze
    handles dark mode without help from Perch).
    """
    if theme == "light":
        return "light"
    if theme == "dark":
        return "dark"
    hints = QGuiApplication.styleHints()
    scheme = hints.colorScheme() if hints is not None else Qt.ColorScheme.Unknown
    if scheme == Qt.ColorScheme.Dark:
        return "dark"
    if scheme == Qt.ColorScheme.Light:
        return "light"
    return "system"


def apply_theme(app: QApplication, theme: Theme) -> None:
    """Apply ``theme`` to ``app``'s palette and style.

    * ``"auto"`` + platform scheme ``Unknown`` → no-op.
    * ``"auto"`` + ``Light`` / ``Dark`` → Fusion + matching palette.
    * ``"light"`` / ``"dark"`` → Fusion + matching palette unconditionally.

    Fusion is chosen because it looks identical everywhere, so a user's
    explicit ``theme = "dark"`` produces the same dialog on KDE, GNOME
    and Xfce — the whole point of the override.
    """
    effective = resolve_effective_theme(theme)
    if effective == "system":
        log.debug("apply_theme: leaving palette untouched (auto, scheme=Unknown)")
        return

    style = QStyleFactory.create("Fusion")
    if style is not None:
        app.setStyle(style)

    palette = _dark_palette() if effective == "dark" else _light_palette()
    app.setPalette(palette)
    log.debug("apply_theme: applied %s palette via Fusion style", effective)
