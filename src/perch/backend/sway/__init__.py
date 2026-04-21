"""Sway / wlroots backend (stub — see ``docs/06-backend-stubs.md`` §Sway).

Talks to the running Sway compositor through the i3-IPC socket at
``$SWAYSOCK`` using the async ``i3ipc.aio.Connection`` client. The "stub"
label in this package's status file means: the interface is implemented
honestly (compliance suite passes with the declared capabilities), but
certain features — notably pre-paint placement and backend-registered
hotkeys — are explicitly not supported because Sway's protocol doesn't
expose them.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .backend import SwayBackend as SwayBackend

__all__ = ["SwayBackend"]


def __getattr__(name: str) -> object:
    # Lazy re-export: importing this package shouldn't drag i3ipc in when
    # callers only want to check ``SwayBackend.is_available()``.
    if name == "SwayBackend":
        from .backend import SwayBackend

        return SwayBackend
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
