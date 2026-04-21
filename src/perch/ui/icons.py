"""Tray status-icon loader.

Per :file:`docs/08-ui.md` §Tray icon the tray has three visual states:

* normal   — ``perch-tray-symbolic``
* warning  — ``perch-tray-warning-symbolic`` (backend disconnected, extension missing)
* error    — ``perch-tray-error-symbolic`` (no compatible compositor)

When Perch is installed into a system prefix the icon theme lookup via
:meth:`QIcon.fromTheme` is authoritative; the panel recolours the
symbolic glyph to match the user's theme. The bundled SVGs under
``data/icons/hicolor/symbolic/status/`` ship as the last-resort fallback
so a dev checkout still renders a sensible tray icon — Qt's SVG
renderer handles every HiDPI scale factor without raster variants.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PySide6.QtGui import QIcon


@dataclass(frozen=True, slots=True)
class TrayIcons:
    """Bundle of the three tray-state icons."""

    normal: QIcon
    warning: QIcon
    error: QIcon


def _bundled_icon_dir() -> Path:
    """Return the dev-checkout path for the bundled status icons.

    The wheel ships ``data/`` alongside the package via Hatch's sdist
    include list (see :file:`pyproject.toml`); the dev path here resolves
    relative to the package root so tests and ``python -m perch`` pick
    the same SVGs whether the project is installed or run in place.
    """
    return (
        Path(__file__).resolve().parents[3]
        / "data/icons/hicolor/symbolic/status"
    )


def _load_fallback(basename: str) -> QIcon:
    path = _bundled_icon_dir() / f"{basename}.svg"
    if path.is_file():
        return QIcon(str(path))
    return QIcon()


def load_tray_icons() -> TrayIcons:
    """Load the three tray-state icons with ``fromTheme`` → bundled fallback.

    On packaged installs the theme lookup succeeds once the icons land at
    ``<prefix>/share/icons/hicolor/symbolic/status/``. On a dev checkout
    the ``fromTheme`` call returns a null ``QIcon`` (no theme entry) and
    we fall through to the bundled SVG next to the source tree.
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
