"""Reusable config-dialog widgets.

Each widget round-trips through a typed core dataclass:

* :class:`~perch.ui.widgets.match_editor.MatchEditor` —
  :class:`~perch.core.matching.MatchPattern`
* :class:`~perch.ui.widgets.geometry_editor.GeometryEditor` —
  :class:`~perch.core.actions.GeometryExpr`
  (absolute / percent / preset variants)
* :class:`~perch.ui.widgets.key_capture.HotkeyEdit` — a single-chord
  :class:`PySide6.QtGui.QKeySequence` in Portable Text form. Includes
  :func:`~perch.ui.widgets.key_capture.portable_to_xdg` for the
  ``org.freedesktop.portal.GlobalShortcuts`` boundary.

Widgets emit ``valueChanged`` when their exposed value is modified so
hosting dialogs can dirty-track. See ``docs/08-ui.md`` §Rules,
§Hotkeys, §Key-capture widget for the UI spec.
"""

from __future__ import annotations

from .geometry_editor import GeometryEditor
from .key_capture import HotkeyEdit, portable_to_xdg, xdg_to_portable
from .match_editor import MatchEditor

__all__ = [
    "GeometryEditor",
    "HotkeyEdit",
    "MatchEditor",
    "portable_to_xdg",
    "xdg_to_portable",
]
