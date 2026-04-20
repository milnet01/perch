"""KWin backend for Plasma 6 Wayland.

Two halves:

* **Python** (this package) — owns the ``io.github.milnet01.Perch`` D-Bus
  service, drives ``org.kde.KWin`` to load the bundled JS script, and
  translates commands / events across the boundary.
* **JS** (``script/``) — runs inside KWin, subscribes to workspace signals,
  dispatches long-poll commands.

Authoritative design: ``docs/05-backend-kwin.md``.
"""

from __future__ import annotations

from pathlib import Path

#: Directory containing the bundled KWin script (``metadata.json`` +
#: ``contents/code/main.js``). Shipped inside the wheel; installers mirror
#: this tree into ``$XDG_DATA_HOME/kwin/scripts/org.milnet01.perch/`` at
#: runtime — KWin on Wayland runs on the host and cannot read Flatpak's
#: ``/app/`` or a dev checkout's ``src/`` path directly.
BUNDLED_SCRIPT_DIR: Path = Path(__file__).resolve().parent / "script"

#: KPackage plugin id. Matches ``metadata.json`` ``KPlugin.Id``; passed to
#: ``org.kde.KWin.Scripting.loadScript(path, plugin_id)`` so
#: ``unloadScript(plugin_id)`` can find the same script later.
PLUGIN_ID: str = "org.milnet01.perch"

#: The script version that the Python half is wired to. Kept in one place
#: so drift between ``metadata.json`` and the installer can be checked.
BUNDLED_SCRIPT_VERSION: str = "1.0.0"

#: Session-bus name owned by the Python process.
SERVICE_NAME: str = "io.github.milnet01.Perch"

#: Object path exporting the ``KWin1`` interface the JS script calls out to.
OBJECT_PATH: str = "/KWin"

#: D-Bus interface name.
INTERFACE_NAME: str = "io.github.milnet01.Perch.KWin1"

__all__ = [
    "BUNDLED_SCRIPT_DIR",
    "BUNDLED_SCRIPT_VERSION",
    "INTERFACE_NAME",
    "OBJECT_PATH",
    "PLUGIN_ID",
    "SERVICE_NAME",
    "KWinBackend",
]


def __getattr__(name: str) -> object:
    # Lazy re-export so importing the package constants doesn't drag in
    # sdbus / asyncio / PySide6 until someone actually uses the backend.
    if name == "KWinBackend":
        from .backend import KWinBackend

        return KWinBackend
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
