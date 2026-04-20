"""Typed command builders and response parsers for the KWin JS bridge.

The JS script and Python side exchange JSON-encoded strings (see
``docs/05-backend-kwin.md`` — KWin bug 486024 makes typed variadic callDBus
marshalling unreliable). The helpers here centralise the shape of each
payload so the backend body can stay readable and a single module is
responsible for keeping JS and Python in sync.
"""

from __future__ import annotations

import json
from typing import Any

from perch.backend.types import (
    DesktopIndex,
    Geometry,
    OutputName,
    WindowId,
    WindowInfo,
    WindowState,
    WindowType,
)

# ── Command builders ───────────────────────────────────────────────────────
#
# Every command becomes a dict with {"op": "<name>", ...}. The dispatcher in
# main.js switches on "op". Sequence numbers are stamped on by the service
# at enqueue time — see ``service.py``.


def op_set_frame_geometry(
    wid: WindowId,
    geom: Geometry,
    *,
    output: OutputName | None = None,
    preplace: bool = False,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "op": "setFrameGeometry",
        "id": wid,
        "x": int(geom.x),
        "y": int(geom.y),
        "w": int(geom.w),
        "h": int(geom.h),
    }
    if output is not None:
        payload["output"] = output
    if preplace:
        payload["preplace"] = True
    return payload


def op_set_full_screen(wid: WindowId, value: bool) -> dict[str, Any]:
    return {"op": "setFullScreen", "id": wid, "value": bool(value)}


def op_set_minimized(wid: WindowId, value: bool) -> dict[str, Any]:
    return {"op": "setMinimized", "id": wid, "value": bool(value)}


def op_set_maximize_mode(wid: WindowId, vertical: bool, horizontal: bool) -> dict[str, Any]:
    return {
        "op": "setMaximizeMode",
        "id": wid,
        "vertical": bool(vertical),
        "horizontal": bool(horizontal),
    }


def op_set_desktop(wid: WindowId, desktop: DesktopIndex) -> dict[str, Any]:
    return {"op": "setDesktop", "id": wid, "desktop": int(desktop)}


def op_close_window(wid: WindowId) -> dict[str, Any]:
    return {"op": "closeWindow", "id": wid}


def op_query_windows() -> dict[str, Any]:
    return {"op": "queryWindows"}


def op_query_outputs() -> dict[str, Any]:
    return {"op": "queryOutputs"}


def op_query_window(wid: WindowId) -> dict[str, Any]:
    return {"op": "queryWindow", "id": wid}


def op_query_current_desktop() -> dict[str, Any]:
    return {"op": "queryCurrentDesktop"}


def op_query_desktop_count() -> dict[str, Any]:
    return {"op": "queryDesktopCount"}


def op_batch(ops: list[dict[str, Any]]) -> dict[str, Any]:
    """Wrap a list of ops for one-tick execution inside KWin.

    The JS runtime applies every sub-op before yielding, so a whole layout
    apply lands in one compositor frame.
    """
    return {"batch": list(ops)}


def encode_command(seq: int, cmd: dict[str, Any]) -> str:
    """Stamp a sequence number on a command and serialise it for the wire."""
    payload = dict(cmd)
    payload["seq"] = int(seq)
    return json.dumps(payload, separators=(",", ":"))


def encode_nop(reason: str | None = None) -> str:
    """A no-op PollCommand reply — the script re-arms without dispatching."""
    payload: dict[str, Any] = {"nop": True}
    if reason is not None:
        payload["reason"] = reason
    return json.dumps(payload, separators=(",", ":"))


# ── Response / event parsing ───────────────────────────────────────────────


def decode_window_info(payload: dict[str, Any]) -> WindowInfo:
    """Build a :class:`WindowInfo` from a JS-side window snapshot.

    See ``describeWindow`` in ``main.js``.
    """
    try:
        wtype = WindowType(payload.get("type", "unknown"))
    except ValueError:
        wtype = WindowType.UNKNOWN
    try:
        wstate = WindowState(payload.get("state", "normal"))
    except ValueError:
        wstate = WindowState.NORMAL
    pid_raw = payload.get("pid")
    pid: int | None = pid_raw if isinstance(pid_raw, int) and pid_raw > 0 else None
    return WindowInfo(
        id=str(payload["id"]),
        app_id=str(payload.get("app_id", "")),
        wm_class=str(payload.get("wm_class", "")),
        title=str(payload.get("title", "")),
        pid=pid,
        type=wtype,
        state=wstate,
        geometry=Geometry(
            x=int(payload.get("x", 0)),
            y=int(payload.get("y", 0)),
            w=int(payload.get("w", 0)),
            h=int(payload.get("h", 0)),
        ),
        monitor=str(payload.get("output", "")),
        desktop=int(payload.get("desktop", -1)),
        role=str(payload.get("role", "")),
    )


def decode_output_entry(payload: dict[str, Any]) -> dict[str, Any]:
    """Normalise a JS-side output dict; full :class:`OutputInfo` assembly
    happens in ``backend.py`` where we also know primary / work-area.
    """
    return {
        "name": str(payload.get("name", "")),
        "geometry": Geometry(
            x=int(payload.get("x", 0)),
            y=int(payload.get("y", 0)),
            w=int(payload.get("w", 0)),
            h=int(payload.get("h", 0)),
        ),
        "scale": float(payload.get("scale", 1.0)),
        "refresh_mhz": int(payload.get("refresh_mhz", 0)),
    }


# ── Command-result helpers ─────────────────────────────────────────────────


class CommandError(RuntimeError):
    """A ``CommandDone`` reply from the JS script carried ``ok:false``."""

    def __init__(self, kind: str, detail: dict[str, Any]) -> None:
        super().__init__(f"kwin script error: {kind} ({detail!r})")
        self.kind = kind
        self.detail = detail


def unwrap_ok(result: dict[str, Any]) -> dict[str, Any]:
    """Raise :class:`CommandError` unless ``result['ok']`` is truthy."""
    if not isinstance(result, dict):
        raise CommandError("malformed_result", {"result": result})
    if not result.get("ok"):
        kind = str(result.get("error", "unknown"))
        raise CommandError(kind, result)
    return result
