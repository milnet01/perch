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
for across the XDG data directories as well as in a dev checkout — Qt's
SVG renderer handles every HiDPI scale factor without raster variants.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtGui import QIcon


@dataclass(frozen=True, slots=True)
class TrayIcons:
    """Bundle of the three tray-state icons."""

    normal: QIcon
    warning: QIcon
    error: QIcon


#: Where the status SVGs sit under any XDG data root.
_ICON_SUBPATH = "icons/hicolor/symbolic/status"


def _dev_icon_dir() -> Path:
    """Dev-checkout path: ``src/perch/ui`` up to the repo root."""
    return (
        Path(__file__).resolve().parents[3]
        / "data/icons/hicolor/symbolic/status"
    )


def _xdg_icon_dirs() -> tuple[Path, ...]:
    """Installed paths, taken from the XDG data-directory search path.

    This is where every packaging recipe puts the SVGs, and it is the one
    lookup that is right in all of them. ``sys.prefix`` is not: inside a
    Flatpak the interpreter comes from the runtime, so ``sys.prefix`` is
    ``/usr`` while Perch's data is under ``/app`` — which
    ``XDG_DATA_DIRS`` lists and ``sys.prefix`` cannot see.
    """
    raw = os.environ.get("XDG_DATA_DIRS") or "/usr/local/share:/usr/share"
    roots = [Path(entry) for entry in raw.split(":") if entry]
    home = os.environ.get("XDG_DATA_HOME")
    roots.insert(0, Path(home) if home else Path.home() / ".local" / "share")
    return tuple(root / _ICON_SUBPATH for root in roots)


def _bundled_icon_dirs() -> tuple[Path, ...]:
    """Fallback search order: installed locations first, dev checkout last."""
    return (*_xdg_icon_dirs(), _dev_icon_dir())


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
