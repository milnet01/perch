"""Window identity — the key used to index :file:`state.json`.

Authoritative spec: ``docs/02-state-format.md`` §Identity keying. The base
form is ``app:<app_id>`` with ``app:<wm_class>`` as an X11 fallback when
``app_id`` is unknown. Extra segments (``::title:<regex>``, ``::role:<X>``,
``::pid:<N>``) are reserved for v1.x when rules start pinning on those
fields; M2.d only implements the base form so the reducer can correlate
last-seen entries across sessions.

The function is intentionally tiny and pure: identity computation happens
on every window event, so overhead matters.
"""

from __future__ import annotations

from perch.backend.types import WindowInfo


def compute_identity(window: WindowInfo) -> str:
    """Return the stable identity string for this window.

    Prefers ``app_id`` (Wayland and modern X11 clients); falls back to
    ``wm_class`` (older X11 clients that never set ``_NET_WM_PID`` /
    ``app_id`` — Signal's Electron build, some legacy Java/Swing apps).
    Returns ``"app:unknown"`` if neither is set, which only happens when a
    backend misbehaves; the reducer will log and skip the entry rather
    than persist a garbage key.
    """
    if window.app_id:
        return f"app:{window.app_id}"
    if window.wm_class:
        return f"app:{window.wm_class}"
    return "app:unknown"
