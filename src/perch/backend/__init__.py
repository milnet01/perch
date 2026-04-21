"""Backend boundary for Perch.

The core talks to every compositor through :class:`WindowBackend`. Concrete
backends live as siblings of :mod:`perch.backend.base` and all respect the
same data shapes defined in :mod:`perch.backend.types`:

* :mod:`perch.backend.mock` — in-memory, used by the compliance suite
* :mod:`perch.backend.x11` — any EWMH WM via python-xlib (M4)
* :mod:`perch.backend.kwin` — Plasma 6 Wayland via KWin scripting (M5)
* :mod:`perch.backend.sway`, :mod:`perch.backend.hyprland`,
  :mod:`perch.backend.mutter` — v1 stubs (M6). See
  :file:`docs/06-backend-stubs.md`.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

from .base import (
    BackendDisconnected,
    BackendError,
    BackendUnavailable,
    BackendUnsupported,
    UnknownOutput,
    UnknownWindow,
    WindowBackend,
)
from .types import (
    Capabilities,
    DesktopIndex,
    Geometry,
    OutputInfo,
    OutputName,
    WindowId,
    WindowInfo,
    WindowState,
    WindowType,
)

if TYPE_CHECKING:
    # Import paths for documentation/IDE only; runtime selection uses the
    # lazy dotted path below so importing perch.backend doesn't drag sdbus,
    # python-xlib, and i3ipc in at module load.
    from .hyprland import HyprlandBackend as HyprlandBackend
    from .kwin import KWinBackend as KWinBackend
    from .mock import MockBackend as MockBackend
    from .mutter import MutterBackend as MutterBackend
    from .sway import SwayBackend as SwayBackend
    from .x11 import X11Backend as X11Backend

#: Probe order for :func:`select`. The first backend whose
#: :meth:`WindowBackend.is_available` returns ``True`` wins, with one
#: exception — X11 is a fallback for any X11 / XWayland session when no
#: Wayland-native backend matches. See ``docs/03-backend-interface.md``
#: §Backend selection.
_BACKEND_MODULES: tuple[tuple[str, str, str], ...] = (
    # (probe-name, import path, class name)
    ("kwin",     "perch.backend.kwin",     "KWinBackend"),
    ("mutter",   "perch.backend.mutter",   "MutterBackend"),
    ("sway",     "perch.backend.sway",     "SwayBackend"),
    ("hyprland", "perch.backend.hyprland", "HyprlandBackend"),
    ("x11",      "perch.backend.x11",      "X11Backend"),
)


def select(override: str | None = None) -> type[WindowBackend]:
    """Choose a backend class based on the current session environment.

    Probes in :data:`_BACKEND_MODULES` order, calling
    :meth:`WindowBackend.is_available` (cheap, env-only) on each class.
    Returns the first class that reports available. On a plain X11 /
    XWayland session where no Wayland-native backend matches, falls
    through to :class:`~perch.backend.x11.X11Backend`.

    Args:
        override: If set, look up the matching entry in :data:`_BACKEND_MODULES`
            by name (``"kwin"``, ``"mutter"``, ``"sway"``, ``"hyprland"``,
            ``"x11"``, ``"mock"``) and return that class without probing. Used
            by tests and by the ``PERCH_BACKEND`` environment variable
            (documented in ``docs/03-backend-interface.md``).

    Raises:
        BackendUnavailable: No backend's transport is detectable on the
            current host.
    """
    explicit = override or os.environ.get("PERCH_BACKEND")
    if explicit:
        if explicit == "mock":
            from .mock import MockBackend

            return MockBackend
        for probe_name, module_path, class_name in _BACKEND_MODULES:
            if probe_name == explicit:
                return _import_backend(module_path, class_name)
        raise BackendUnavailable(f"unknown PERCH_BACKEND value {explicit!r}")

    for _probe_name, module_path, class_name in _BACKEND_MODULES:
        cls = _import_backend(module_path, class_name)
        if cls.is_available():
            return cls
    raise BackendUnavailable(
        "no backend is available on this session "
        "(no KWin / Mutter / Sway / Hyprland / X11 transport detected)"
    )


def _import_backend(module_path: str, class_name: str) -> type[WindowBackend]:
    """Import a backend class by dotted path. Kept out of the top-level imports
    so ``import perch.backend`` doesn't require sdbus / python-xlib / i3ipc to
    be present on the host.
    """
    from importlib import import_module
    from typing import cast

    module = import_module(module_path)
    cls = getattr(module, class_name)
    # mypy can't see through getattr; the cast is safe because every entry
    # in _BACKEND_MODULES names a WindowBackend subclass.
    assert issubclass(cls, WindowBackend), (
        f"{module_path}.{class_name} is not a WindowBackend subclass"
    )
    return cast(type[WindowBackend], cls)


__all__ = [
    "BackendDisconnected",
    "BackendError",
    "BackendUnavailable",
    "BackendUnsupported",
    "Capabilities",
    "DesktopIndex",
    "Geometry",
    "OutputInfo",
    "OutputName",
    "UnknownOutput",
    "UnknownWindow",
    "WindowBackend",
    "WindowId",
    "WindowInfo",
    "WindowState",
    "WindowType",
    "select",
]
