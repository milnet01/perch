"""Tray status-icon loader.

Per :file:`docs/08-ui.md` §Tray icon the tray has three visual states:

* normal   — ``perch-tray-symbolic``
* warning  — ``perch-tray-warning-symbolic`` (backend disconnected, extension missing)
* error    — ``perch-tray-error-symbolic`` (no compatible compositor)

The icon theme lookup via :meth:`QIcon.fromTheme` is tried first, so the
panel can recolour the symbolic glyph to match the user's theme. It is
not relied on: measured on a live Plasma session with ``breeze-dark``,
:meth:`QIcon.hasThemeIcon` returns ``False`` for all three names even
where the SVGs are installed under ``share/icons/hicolor/symbolic/status/``.
The bundled SVGs are therefore the load-bearing path, and they are looked
for under the install prefix as well as in a dev checkout — Qt's SVG
renderer handles every HiDPI scale factor without raster variants.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtGui import QIcon


@dataclass(frozen=True, slots=True)
class TrayIcons:
    """Bundle of the three tray-state icons."""

    normal: QIcon
    warning: QIcon
    error: QIcon


#: Where the status SVGs sit under any icon-theme root.
_ICON_SUBPATH = "share/icons/hicolor/symbolic/status"


def _dev_icon_dir() -> Path:
    """Dev-checkout path: ``src/perch/ui`` up to the repo root."""
    return (
        Path(__file__).resolve().parents[3]
        / "data/icons/hicolor/symbolic/status"
    )


def _prefix_icon_dir() -> Path:
    """Installed path — ``/app`` under Flatpak, ``/usr`` under an RPM.

    Every packaging recipe installs the three SVGs here, so this is the
    candidate that works once Perch is no longer being run from its
    source tree.
    """
    return Path(sys.prefix) / _ICON_SUBPATH


def _bundled_icon_dirs() -> tuple[Path, ...]:
    """Fallback search order: installed first, dev checkout second."""
    return (_prefix_icon_dir(), _dev_icon_dir())


def _load_fallback(basename: str) -> QIcon:
    for directory in _bundled_icon_dirs():
        path = directory / f"{basename}.svg"
        if path.is_file():
            return QIcon(str(path))
    return QIcon()


def load_tray_icons() -> TrayIcons:
    """Load the three tray-state icons with ``fromTheme`` → bundled fallback.

    The theme lookup is best-effort and usually misses, so the bundled
    SVG is what normally renders. It is searched for under the install
    prefix first and the dev checkout second, which is what keeps the
    tray icon from coming out null on a Flatpak or RPM install.
    """
    return TrayIcons(
        normal=QIcon.fromTheme(
            "perch-tray-symbolic", _load_fallback("perch-tray-symbolic")
        ),
        warning=QIcon.fromTheme(
            "perch-tray-warning-symbolic",
            _load_fallback("perch-tray-warning-symbolic"),
        ),
        error=QIcon.fromTheme(
            "perch-tray-error-symbolic",
            _load_fallback("perch-tray-error-symbolic"),
        ),
    )
