"""Backend boundary for Perch.

The core talks to every compositor through :class:`WindowBackend`. Concrete
backends (``mock`` in M2, ``x11`` in M4, ``kwin`` in M5, stubs in M6) live as
siblings of :mod:`perch.backend.base` and all respect the same data shapes
defined in :mod:`perch.backend.types`.
"""

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
]
