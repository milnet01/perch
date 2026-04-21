"""Mutter / GNOME Shell backend (stub — see ``docs/06-backend-stubs.md`` §Mutter).

Two halves:

* **Python** (this package) — :class:`MutterBackend` talks to the bundled
  GNOME Shell extension over the session bus at
  ``io.github.milnet01.Perch.Mutter``.
* **GJS** (``extension/``) — the bundled extension itself runs inside
  ``gnome-shell`` and drives ``Meta.Window.move_resize_frame`` + workspace
  / monitor management. Shipped in the wheel; installers mirror it into
  ``~/.local/share/gnome-shell/extensions/perch@milnet01.github.io/``
  because a Flatpak Perch cannot install the extension itself (no portal
  for that).
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .backend import MutterBackend as MutterBackend

#: Directory containing the bundled GNOME Shell extension
#: (``metadata.json`` + ``extension.js``). Shipped inside the wheel;
#: installers mirror this tree into
#: ``$XDG_DATA_HOME/gnome-shell/extensions/perch@milnet01.github.io/``
#: at setup time.
BUNDLED_EXTENSION_DIR: Path = Path(__file__).resolve().parent / "extension"

#: GNOME Shell extension UUID. Matches ``extension/metadata.json``'s
#: ``uuid`` field. Used by ``gnome-extensions enable/disable`` and the
#: `user-theme`-style config key.
EXTENSION_UUID: str = "perch@milnet01.github.io"

#: Session-bus name the Shell extension exports.
SERVICE_NAME: str = "io.github.milnet01.Perch.Mutter"

#: Object path exporting the ``Mutter1`` interface.
OBJECT_PATH: str = "/Mutter"

#: D-Bus interface name.
INTERFACE_NAME: str = "io.github.milnet01.Perch.Mutter1"

#: Minimum GNOME version we target. Raised from 45 to 48 during Phase 2
#: research — see ``docs/06-backend-stubs.md`` §Minimum GNOME version.
MIN_GNOME_VERSION: tuple[int, int] = (48, 0)

__all__ = [
    "BUNDLED_EXTENSION_DIR",
    "EXTENSION_UUID",
    "INTERFACE_NAME",
    "MIN_GNOME_VERSION",
    "OBJECT_PATH",
    "SERVICE_NAME",
    "MutterBackend",
]


def __getattr__(name: str) -> object:
    if name == "MutterBackend":
        from .backend import MutterBackend

        return MutterBackend
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
