"""XRandR enumeration: ``list_outputs()`` and refresh-rate math.

Kept in its own module so the backend can call it, the integration tests
can exercise it against Xvfb, and the refresh-rate arithmetic is unit-
testable without a live extension.

Module layout notes (confirmed 2026-04-20 against ``python-xlib`` 0.33):

- ``root.xrandr_get_screen_resources_current()`` returns a reply with
  ``.config_timestamp``, ``.outputs`` (int list), ``.modes`` (list of dicts
  with snake-case keys: ``id``, ``width``, ``height``, ``dot_clock``,
  ``h_total``, ``v_total``, …).
- ``display.xrandr_get_crtc_info(crtc, ts)`` lives on the display extension,
  not the root window (the call-site is ``d.xrandr_get_crtc_info``, not
  ``root.xrandr_get_crtc_info``).
- ``oi.connection`` uses module constants ``Connected=0``, ``Disconnected=1``,
  ``Unknown=2`` from ``Xlib.ext.randr``.
- Extension event codes (``ScreenChangeNotify``, ``CrtcChangeNotify``,
  ``OutputChangeNotify``) are assigned by ``d.init_extension('RANDR')`` and
  must be read from ``d.extension_event.*`` after initialisation — they are
  not static.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from perch.backend.types import Geometry, OutputInfo

if TYPE_CHECKING:
    from Xlib.display import Display


def refresh_mhz(dot_clock: int, h_total: int, v_total: int) -> int:
    """Compute refresh in mHz from a mode's ``dot_clock`` (Hz) and totals.

    Follows libXrandr's formula: ``round(dot_clock * 1000 / (h_total * v_total))``.
    A zero ``dot_clock`` or zero total means the CRTC is off or reporting
    an "unknown" mode; returning ``0`` is safer than raising, because
    list_outputs() must keep going when a single CRTC is misbehaving.
    """
    denom = h_total * v_total
    if denom == 0 or dot_clock == 0:
        return 0
    return round(dot_clock * 1000 / denom)


def list_outputs(display: Display) -> list[OutputInfo]:
    """Enumerate every XRandR output reachable from ``display``.

    Disconnected outputs are included with ``is_connected=False`` and a
    zero-rect :class:`Geometry` (Perch's UI filters them out but the compliance
    suite expects :meth:`list_outputs` to be exhaustive).

    ``scale`` is always ``1.0`` on native X11 — fractional scaling there is
    a toolkit trick, invisible from the protocol. Under XWayland the CRTC
    geometry is already in logical pixels.
    """
    from Xlib.ext import randr

    root = display.screen().root
    res = root.xrandr_get_screen_resources_current()
    config_ts = res.config_timestamp
    modes = {m["id"]: m for m in res.modes}
    primary = root.xrandr_get_output_primary().output

    outputs: list[OutputInfo] = []
    for oid in res.outputs:
        oi = display.xrandr_get_output_info(oid, config_ts)
        # ``python-xlib`` has historically flip-flopped between returning
        # ``bytes`` and pre-decoded ``str`` for output names across releases
        # (0.29 returned bytes; 0.33 on modern distros returns str). Normalise
        # to str without caring which branch we're on.
        raw_name = oi.name
        if isinstance(raw_name, bytes):
            name = raw_name.decode("ascii", errors="replace")
        else:
            name = str(raw_name)
        connected = oi.connection == randr.Connected
        is_primary = oid == primary

        if oi.crtc == 0 or not connected:
            outputs.append(
                OutputInfo(
                    name=name,
                    geometry=Geometry(0, 0, 0, 0),
                    work_area=Geometry(0, 0, 0, 0),
                    scale=1.0,
                    refresh_mhz=0,
                    is_primary=is_primary,
                    is_connected=connected,
                )
            )
            continue

        ci = display.xrandr_get_crtc_info(oi.crtc, config_ts)
        geom = Geometry(int(ci.x), int(ci.y), int(ci.width), int(ci.height))
        mode = modes.get(ci.mode)
        mhz = (
            refresh_mhz(
                int(mode["dot_clock"]),
                int(mode["h_total"]),
                int(mode["v_total"]),
            )
            if mode is not None
            else 0
        )
        # work_area computed later via _NET_WORKAREA intersection; default to
        # the full geometry so OutputInfo is valid in isolation.
        outputs.append(
            OutputInfo(
                name=name,
                geometry=geom,
                work_area=geom,
                scale=1.0,
                refresh_mhz=mhz,
                is_primary=is_primary,
                is_connected=True,
            )
        )
    return outputs


def apply_workarea(outputs: list[OutputInfo], workarea: Geometry) -> list[OutputInfo]:
    """Intersect every output's geometry with the root-level workarea rect.

    EWMH's ``_NET_WORKAREA`` is a per-virtual-desktop ``CARDINAL[4n]`` on
    root, but most WMs report the *current-desktop* workarea as the first
    4-tuple and don't vary it per output. Intersecting each output's
    geometry with that single rect is what KDE and GNOME do when asked
    "what's the working area on monitor N" — it's lossy across struts
    that only touch one monitor, but it's the best the EWMH spec supports
    without the newer per-monitor struts protocol.
    """
    out: list[OutputInfo] = []
    for o in outputs:
        if not o.is_connected or o.geometry.w == 0:
            out.append(o)
            continue
        wa = _intersect(o.geometry, workarea)
        out.append(
            OutputInfo(
                name=o.name,
                geometry=o.geometry,
                work_area=wa,
                scale=o.scale,
                refresh_mhz=o.refresh_mhz,
                is_primary=o.is_primary,
                is_connected=o.is_connected,
            )
        )
    return out


def _intersect(a: Geometry, b: Geometry) -> Geometry:
    x0 = max(a.x, b.x)
    y0 = max(a.y, b.y)
    x1 = min(a.x + a.w, b.x + b.w)
    y1 = min(a.y + a.h, b.y + b.h)
    if x1 <= x0 or y1 <= y0:
        return Geometry(a.x, a.y, 0, 0)
    return Geometry(x0, y0, x1 - x0, y1 - y0)
