"""Hyprland backend (stub — see ``docs/06-backend-stubs.md`` §Hyprland).

Talks to the running Hyprland compositor through ``hyprctl`` for queries
and the ``.socket2.sock`` event stream for subscriptions. Requires
Hyprland ≥ 0.40; the stub refuses to run on older versions rather than
dispatching to an unknown event format.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .backend import HyprlandBackend as HyprlandBackend

__all__ = ["HyprlandBackend"]


def __getattr__(name: str) -> object:
    if name == "HyprlandBackend":
        from .backend import HyprlandBackend

        return HyprlandBackend
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
