"""Geometry math for the X11 backend.

Two things live here, deliberately separated from the EWMH protocol layer so
they can be unit-tested without a display connection:

1. **Frame-extents subtraction** — ``_NET_FRAME_EXTENTS`` reports the
   decoration thickness around a client window as a ``CARDINAL[4]`` in the
   order ``(left, right, top, bottom)``. Perch's stored geometry refers to
   the *client area*, matching what ``_NET_MOVERESIZE_WINDOW`` with
   ``StaticGravity`` expects to receive, so we subtract extents from the
   outer (frame) coordinates. See ``docs/04-backend-x11.md``.

2. **Monitor-of-window resolution** — once the core has a window's
   client-area rect, which :class:`~perch.backend.types.OutputInfo` does it
   sit on? We use the same "largest-overlap wins, tie-break on primary, then
   first-in-list" rule every compositor uses when it has to pick exactly
   one. Matches KWin's ``Workspace::clientArea`` and Mutter's
   ``meta_screen_get_monitor_index_for_rect``.

Everything here is pure; :class:`Xlib.display.Display` is only touched by
:func:`read_client_area` which is a thin wrapper around two ``ReplyRequest``
calls that the caller can mock.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from perch.backend.types import Geometry, OutputInfo

if TYPE_CHECKING:
    from Xlib.display import Display
    from Xlib.xobject.drawable import Window


@dataclass(frozen=True, slots=True)
class FrameExtents:
    """Decoration thickness around a client window (all non-negative)."""

    left: int
    right: int
    top: int
    bottom: int

    @classmethod
    def zero(cls) -> FrameExtents:
        return cls(0, 0, 0, 0)


def client_area_from_frame(
    frame_x: int,
    frame_y: int,
    frame_w: int,
    frame_h: int,
    extents: FrameExtents,
) -> Geometry:
    """Subtract decoration thickness to get the client-area :class:`Geometry`.

    Used when we have the outer (WM-frame) rect and need the inner rect
    Perch stores. Negative results are clamped to ``0`` because a frame
    cannot be smaller than its extents — a malformed ``_NET_FRAME_EXTENTS``
    with extents larger than the frame would otherwise surface as nonsense
    negatives to the rules engine.
    """
    x = frame_x + extents.left
    y = frame_y + extents.top
    w = max(0, frame_w - extents.left - extents.right)
    h = max(0, frame_h - extents.top - extents.bottom)
    return Geometry(x, y, w, h)


def monitor_for_geometry(
    geom: Geometry, outputs: list[OutputInfo]
) -> str | None:
    """Pick the output that best contains ``geom``.

    The rule is "largest overlap wins"; ties break on primary, then on the
    order the WM reports outputs. Windows that fall entirely off-screen
    (zero overlap with every output) return ``None`` — the caller typically
    uses the primary output as a fallback and surfaces a warning.

    Returns the :class:`OutputInfo.name` rather than the full object so the
    caller can pass it through the ``monitor: OutputName`` parameter used
    throughout the backend interface.
    """
    if not outputs:
        return None
    best_name: str | None = None
    best_area = -1
    for out in outputs:
        area = _overlap_area(geom, out.geometry)
        if area > best_area or (
            area == best_area
            and area > 0
            and out.is_primary
            and best_name is not None
        ):
            best_area = area
            best_name = out.name
    if best_area <= 0:
        return None
    return best_name


def _overlap_area(a: Geometry, b: Geometry) -> int:
    """Area of the axis-aligned intersection, or ``0`` if disjoint."""
    x0 = max(a.x, b.x)
    y0 = max(a.y, b.y)
    x1 = min(a.x + a.w, b.x + b.w)
    y1 = min(a.y + a.h, b.y + b.h)
    if x1 <= x0 or y1 <= y0:
        return 0
    return (x1 - x0) * (y1 - y0)


# ── Display-touching helpers (kept minimal) ────────────────────────────────

def translate_to_root(display: Display, window: Window) -> tuple[int, int]:
    """Translate ``(0, 0)`` of ``window`` into root coordinates.

    ``python-xlib``'s ``translate_coords`` is called on the *destination*
    window with the *source* window as an argument — i.e.
    ``root.translate_coords(window, 0, 0)`` translates ``(0, 0)`` given in
    ``window``'s coordinate system into root coordinates. The inverse form
    (``window.translate_coords(root, 0, 0)``) is a common mis-translation
    from the underlying X11 ``TranslateCoordinates`` request name and
    returns nonsense negative offsets for any reparented window.

    Being a :class:`ReplyRequest`, ``BadWindow`` / ``BadMatch`` surface
    *inline* as ``Xlib.error`` exceptions — the caller handles them.
    """
    root = display.screen().root
    reply = root.translate_coords(window, 0, 0)
    return int(reply.x), int(reply.y)


def read_frame_extents(
    window: Window, frame_extents_atom: int
) -> FrameExtents:
    """Read ``_NET_FRAME_EXTENTS`` from ``window``; default to zeros if absent.

    The zero default is what Openbox / KWin / Mutter / GTK use when a window
    has no decoration (client-side decorations, borderless, override-redirect
    that slipped through). ``python-xlib``'s ``get_full_property`` returns
    ``None`` when the property is missing or of a different type than
    requested, hence the short-circuit.
    """
    from Xlib import X as _X

    prop = window.get_full_property(frame_extents_atom, _X.AnyPropertyType)
    if prop is None or prop.format != 32 or len(prop.value) < 4:
        return FrameExtents.zero()
    left, right, top, bottom = (int(v) for v in prop.value[:4])
    return FrameExtents(
        left=max(0, left),
        right=max(0, right),
        top=max(0, top),
        bottom=max(0, bottom),
    )
