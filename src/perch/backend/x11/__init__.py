"""X11 / EWMH backend for Perch.

Implements :class:`~perch.backend.base.WindowBackend` against any EWMH-compliant
window manager (Openbox, Xfwm, Metacity, KWin-X11, Mutter-X11, i3, bspwm, …)
through a single ``python-xlib`` ``Display`` connection. Authoritative design
reference: ``docs/04-backend-x11.md``.

The module is split for testability:

- :mod:`perch.backend.x11.ewmh` — atom registry, client-message packing, and
  the small enum/property helpers that translate EWMH payloads into the core
  :mod:`perch.backend.types` shapes. Pure module, no ``Display`` required.
- :mod:`perch.backend.x11.geometry` — coordinate math (root translate, frame
  extents subtraction, monitor-of-window resolution). Pure module.

Public entry point (``X11Backend``) lands in M4.b.
"""

from __future__ import annotations

__all__: list[str] = []
