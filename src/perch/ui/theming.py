"""Palette + style application for Perch's dark/light theming (M7.f).

Per ``[general].theme`` (``"auto" | "light" | "dark"`` — see
:file:`docs/08-ui.md` §Config dialog):

* ``"auto"`` (default) defers to the platform: no palette override, no
  style override, whatever ``colorScheme()`` reports. Plasma 6 and GNOME
  report Dark or Light rather than Unknown, so reading the scheme and
  forcing a matching palette would replace Breeze and any high-contrast
  scheme the user chose. Leaving it alone is what lets both through.
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

from PySide6.QtGui import QColor, QPalette
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

    ``"auto"`` always resolves to ``"system"`` — leave the platform's
    style and palette in charge (see the module docstring for why the
    reported colour scheme is not consulted).
    """
    if theme == "light":
        return "light"
    if theme == "dark":
        return "dark"
    return "system"


#: The style the platform chose, recorded before Perch first forces Fusion,
#: so a live switch back to ``"auto"`` can hand it back.
_platform_style: str | None = None
_overridden = False


def apply_theme(app: QApplication, theme: Theme) -> None:
    """Apply ``theme`` to ``app``'s palette and style.

    * ``"auto"`` → leave the platform alone; if an earlier call forced a
      theme, restore the platform style and palette.
    * ``"light"`` / ``"dark"`` → Fusion + matching palette.

    Fusion is chosen because it looks identical everywhere, so a user's
    explicit ``theme = "dark"`` produces the same dialog on KDE, GNOME
    and Xfce — the whole point of the override.
    """
    global _platform_style, _overridden
    if _platform_style is None:
        _platform_style = app.style().name()

    effective = resolve_effective_theme(theme)
    if effective == "system":
        if _overridden:
            platform = QStyleFactory.create(_platform_style)
            if platform is not None:
                app.setStyle(platform)
            # An empty palette resolves back to the platform's own.
            app.setPalette(QPalette())
            _overridden = False
            log.debug("apply_theme: restored platform style %s", _platform_style)
        return

    style = QStyleFactory.create("Fusion")
    if style is not None:
        app.setStyle(style)

    palette = _dark_palette() if effective == "dark" else _light_palette()
    app.setPalette(palette)
    _overridden = True
    log.debug("apply_theme: applied %s palette via Fusion style", effective)
