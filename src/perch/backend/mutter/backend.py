"""``MutterBackend`` — :class:`WindowBackend` over the bundled GNOME Shell extension.

Authoritative design: ``docs/06-backend-stubs.md`` §Mutter / GNOME Shell.

The extension (see ``extension/``) exports ``io.github.milnet01.Perch.Mutter1``
on the session bus. This class is the Python client for that interface. It
is deliberately a *thin* shim — all of the Meta.Window / global.display
work happens inside ``extension/extension.js``; the Python side just calls
methods and translates the JSON-shaped returns into our frozen dataclasses.

Until the extension lands in a user's ``~/.local/share/gnome-shell/extensions/``
and is enabled, ``start()`` raises :class:`BackendUnavailable` — matching
the "awaiting extension" state documented in docs/06.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

from sdbus import DbusInterfaceCommonAsync, dbus_method_async

from perch.backend.base import (
    BackendDisconnected,
    BackendError,
    BackendUnavailable,
    BackendUnsupported,
    UnknownOutput,
    UnknownWindow,
    WindowBackend,
)
from perch.backend.types import (
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

from . import INTERFACE_NAME, OBJECT_PATH, SERVICE_NAME

log = logging.getLogger("perch.backend.mutter")


_CAPABILITIES = Capabilities(
    can_set_position=True,
    can_set_size=True,
    can_set_monitor=True,
    can_set_desktop=True,
    can_set_state=True,
    can_enumerate_windows=True,
    can_observe_geometry=True,
    can_observe_outputs=True,
    can_register_hotkeys=True,
    can_preplace_windows=False,
    notes=(
        "GNOME ≥ 48 via bundled Shell extension. Pre-paint placement is "
        "not supported: windows appear at their default location and then "
        "snap to the target geometry. The extension must be installed "
        "outside the Flatpak (two-step install); see STATUS.md."
    ),
)


def _session_is_gnome() -> bool:
    """Cheap env-only probe — does this look like a GNOME Wayland session?"""
    current = os.environ.get("XDG_CURRENT_DESKTOP", "").upper()
    session = os.environ.get("XDG_SESSION_TYPE", "")
    return "GNOME" in current and session in ("wayland", "")


class MutterBackend(WindowBackend):
    """GNOME Shell backend (stub) — client side of the bundled extension.

    Cheap to construct. ``start()`` opens the session bus, instantiates a
    proxy for the extension's ``Mutter1`` interface, and awaits a
    ``Ready`` response before emitting ``backend_connected``. If the
    extension isn't installed / isn't enabled, the proxy's first call will
    fail and we surface :class:`BackendUnavailable` so the UI can display
    the "awaiting GNOME extension" state.
    """

    def __init__(self) -> None:
        super().__init__()
        self._connected: bool = False
        self._proxy: Any = None
        self._windows: dict[WindowId, WindowInfo] = {}
        self._outputs: dict[OutputName, OutputInfo] = {}

    @classmethod
    def is_available(cls) -> bool:
        return _session_is_gnome()

    # ── Lifecycle ──────────────────────────────────────────────────────────

    async def start(self) -> None:
        if not _session_is_gnome():
            raise BackendUnavailable(
                "MutterBackend requires a GNOME Wayland session "
                "(XDG_CURRENT_DESKTOP containing GNOME)"
            )
        from sdbus import sd_bus_open_user, set_default_bus

        try:
            set_default_bus(sd_bus_open_user())
        except Exception as exc:
            raise BackendUnavailable(f"cannot open session bus: {exc}") from exc

        proxy = _MutterProxy.new_proxy(SERVICE_NAME, OBJECT_PATH)
        try:
            version = await proxy.ping()
        except Exception as exc:
            raise BackendUnavailable(
                f"Perch GNOME Shell extension is not reachable on {SERVICE_NAME}: {exc}. "
                f"Install/enable 'perch@milnet01.github.io' — see STATUS.md."
            ) from exc

        log.info("MutterBackend: reached extension, reported version=%r", version)
        self._proxy = proxy
        self._connected = True
        self.backend_connected.emit()

    async def stop(self) -> None:
        if not self._connected:
            return
        self._connected = False
        self._proxy = None
        self._windows.clear()
        self._outputs.clear()
        self.backend_disconnected.emit("stopped")

    @property
    def capabilities(self) -> Capabilities:
        return _CAPABILITIES

    # ── Queries ────────────────────────────────────────────────────────────

    async def list_windows(self) -> list[WindowInfo]:
        self._require_connected()
        payload = await self._proxy.list_windows()
        return self._decode_windows(payload)

    async def get_window(self, wid: WindowId) -> WindowInfo:
        self._require_connected()
        payload = await self._proxy.get_window(wid)
        info = _decode_window(self._parse_json(payload, context="get_window"))
        if info is None:
            raise UnknownWindow(f"no GNOME window with id {wid!r}")
        self._windows[info.id] = info
        return info

    async def list_outputs(self) -> list[OutputInfo]:
        self._require_connected()
        payload = await self._proxy.list_outputs()
        outs = self._decode_outputs(payload)
        self._outputs = {o.name: o for o in outs}
        return outs

    async def current_desktop(self) -> DesktopIndex:
        self._require_connected()
        raw = await self._proxy.current_workspace()
        if isinstance(raw, int):
            return raw
        return 0

    async def desktop_count(self) -> int:
        self._require_connected()
        raw = await self._proxy.workspace_count()
        if isinstance(raw, int) and raw > 0:
            return raw
        return 1

    # ── Commands ───────────────────────────────────────────────────────────

    async def set_geometry(
        self,
        wid: WindowId,
        geom: Geometry,
        monitor: OutputName | None = None,
        desktop: DesktopIndex | None = None,
    ) -> None:
        self._require_connected()
        if monitor is not None and monitor not in self._outputs:
            await self.list_outputs()
            if monitor not in self._outputs:
                raise UnknownOutput(f"no GNOME output named {monitor!r}")

        # Bundle the three writes into a single extension call so the
        # extension can handle the unmaximize-then-move dance atomically
        # (see docs/06 §move_resize_frame caveats).
        request = {
            "id": wid,
            "x": geom.x,
            "y": geom.y,
            "w": geom.w,
            "h": geom.h,
            "monitor": monitor,
            "desktop": desktop,
        }
        result = await self._proxy.set_geometry(json.dumps(request))
        parsed = self._parse_json(result, context="set_geometry")
        _raise_for_error(parsed, wid=wid, monitor=monitor)

    async def set_state(self, wid: WindowId, state: WindowState) -> None:
        self._require_connected()
        # Every state forwards to the extension; the extension decides what
        # is supported on the current Mutter version and returns
        # ``{"ok": false, "error": "unsupported", ...}`` if not. We
        # translate that to :class:`BackendUnsupported` via _raise_for_error.
        result = await self._proxy.set_state(wid, state.value)
        parsed = self._parse_json(result, context="set_state")
        _raise_for_error(parsed, wid=wid)

    async def close_window(self, wid: WindowId) -> None:
        self._require_connected()
        result = await self._proxy.close_window(wid)
        parsed = self._parse_json(result, context="close_window")
        _raise_for_error(parsed, wid=wid)

    async def register_hotkey(self, accel: str, callback_id: str) -> None:
        self._require_connected()
        result = await self._proxy.register_hotkey(callback_id, accel)
        parsed = self._parse_json(result, context="register_hotkey")
        _raise_for_error(parsed, wid=callback_id)

    async def unregister_hotkey(self, callback_id: str) -> None:
        self._require_connected()
        await self._proxy.unregister_hotkey(callback_id)

    # ── Decoding helpers ───────────────────────────────────────────────────

    def _decode_windows(self, payload: Any) -> list[WindowInfo]:
        raw = self._parse_json(payload, context="list_windows")
        if not isinstance(raw, list):
            return []
        infos: list[WindowInfo] = []
        for entry in raw:
            info = _decode_window(entry)
            if info is not None:
                infos.append(info)
                self._windows[info.id] = info
        return infos

    def _decode_outputs(self, payload: Any) -> list[OutputInfo]:
        raw = self._parse_json(payload, context="list_outputs")
        if not isinstance(raw, list):
            return []
        outs: list[OutputInfo] = []
        for entry in raw:
            out = _decode_output(entry)
            if out is not None:
                outs.append(out)
        return outs

    @staticmethod
    def _parse_json(payload: Any, *, context: str) -> Any:
        """Parse a JSON string returned from the extension. Identity-cast dicts/lists."""
        if isinstance(payload, str):
            try:
                return json.loads(payload)
            except json.JSONDecodeError as exc:
                raise BackendError(
                    f"GNOME extension returned invalid JSON for {context}: {payload!r}"
                ) from exc
        return payload

    def _require_connected(self) -> None:
        if not self._connected or self._proxy is None:
            raise BackendDisconnected(
                "MutterBackend is not connected; call start() first"
            )


# ── D-Bus proxy (sdbus) ────────────────────────────────────────────────────

# The extension side returns JSON strings for the "shaped" replies
# (list_windows, list_outputs, get_window, set_* error envelopes) so we
# can evolve the schema without renumbering D-Bus signatures every
# release. Ping / desktop counts are plain integers.


class _MutterProxy(
    DbusInterfaceCommonAsync,
    interface_name=INTERFACE_NAME,
):
    """sdbus proxy for ``io.github.milnet01.Perch.Mutter1``.

    The ``# type: ignore[empty-body]`` markers are the standard pattern for
    sdbus proxy classes — the decorator supplies the runtime body but
    mypy still sees ``...``.
    """

    @dbus_method_async(result_signature="s")
    async def ping(self) -> str: ...  # type: ignore[empty-body]

    @dbus_method_async(result_signature="s")
    async def list_windows(self) -> str: ...  # type: ignore[empty-body]

    @dbus_method_async(input_signature="s", result_signature="s")
    async def get_window(self, wid: str) -> str: ...  # type: ignore[empty-body]

    @dbus_method_async(result_signature="s")
    async def list_outputs(self) -> str: ...  # type: ignore[empty-body]

    @dbus_method_async(result_signature="i")
    async def current_workspace(self) -> int: ...  # type: ignore[empty-body]

    @dbus_method_async(result_signature="i")
    async def workspace_count(self) -> int: ...  # type: ignore[empty-body]

    @dbus_method_async(input_signature="s", result_signature="s")
    async def set_geometry(self, request_json: str) -> str: ...  # type: ignore[empty-body]

    @dbus_method_async(input_signature="ss", result_signature="s")
    async def set_state(self, wid: str, state: str) -> str: ...  # type: ignore[empty-body]

    @dbus_method_async(input_signature="s", result_signature="s")
    async def close_window(self, wid: str) -> str: ...  # type: ignore[empty-body]

    @dbus_method_async(input_signature="ss", result_signature="s")
    async def register_hotkey(  # type: ignore[empty-body]
        self, callback_id: str, accel: str
    ) -> str: ...

    @dbus_method_async(input_signature="s")
    async def unregister_hotkey(self, callback_id: str) -> None: ...


# ── JSON decoders (shape: extension/extension.js emits these exactly) ──────


def _decode_window(entry: Any) -> WindowInfo | None:
    if not isinstance(entry, dict):
        return None
    try:
        geom = Geometry(
            x=int(entry["x"]),
            y=int(entry["y"]),
            w=int(entry["w"]),
            h=int(entry["h"]),
        )
    except (KeyError, TypeError, ValueError):
        return None
    state_raw = str(entry.get("state") or "normal").lower()
    try:
        state = WindowState(state_raw)
    except ValueError:
        state = WindowState.NORMAL
    type_raw = str(entry.get("type") or "normal").lower()
    try:
        wtype = WindowType(type_raw)
    except ValueError:
        wtype = WindowType.NORMAL
    pid = entry.get("pid")
    if not isinstance(pid, int) or pid <= 0:
        pid = None
    return WindowInfo(
        id=str(entry.get("id") or ""),
        app_id=str(entry.get("app_id") or "").lower(),
        wm_class=str(entry.get("wm_class") or ""),
        title=str(entry.get("title") or ""),
        pid=pid,
        type=wtype,
        state=state,
        geometry=geom,
        monitor=str(entry.get("monitor") or ""),
        desktop=int(entry.get("desktop", 0)),
    )


def _decode_output(entry: Any) -> OutputInfo | None:
    if not isinstance(entry, dict):
        return None
    try:
        geom = Geometry(
            x=int(entry["x"]),
            y=int(entry["y"]),
            w=int(entry["w"]),
            h=int(entry["h"]),
        )
    except (KeyError, TypeError, ValueError):
        return None
    work_raw = entry.get("work_area") or {}
    if isinstance(work_raw, dict):
        try:
            work = Geometry(
                x=int(work_raw.get("x", geom.x)),
                y=int(work_raw.get("y", geom.y)),
                w=int(work_raw.get("w", geom.w)),
                h=int(work_raw.get("h", geom.h)),
            )
        except (TypeError, ValueError):
            work = geom
    else:
        work = geom
    return OutputInfo(
        name=str(entry.get("name") or ""),
        geometry=geom,
        work_area=work,
        scale=float(entry.get("scale") or 1.0),
        refresh_mhz=int(entry.get("refresh_mhz") or 0),
        is_primary=bool(entry.get("is_primary", False)),
        is_connected=bool(entry.get("is_connected", True)),
    )


def _raise_for_error(
    parsed: Any,
    *,
    wid: WindowId | None = None,
    monitor: OutputName | None = None,
) -> None:
    """Translate the extension's error envelope to our taxonomy.

    The extension returns ``{"ok": true}`` on success and
    ``{"ok": false, "error": "<kind>", "message": "..."}`` on failure,
    where ``kind`` is one of ``unknown_window``, ``unknown_output``,
    ``unsupported``. Plain-truthy or non-dict replies are treated as
    success (the extension's ``ping()`` returns a version string, not an
    envelope).
    """
    if not isinstance(parsed, dict):
        return
    if parsed.get("ok"):
        return
    kind = str(parsed.get("error") or "")
    message = str(parsed.get("message") or "")
    if kind == "unknown_window":
        raise UnknownWindow(message or f"no GNOME window with id {wid!r}")
    if kind == "unknown_output":
        raise UnknownOutput(message or f"no GNOME output named {monitor!r}")
    if kind == "unsupported":
        raise BackendUnsupported(message or "operation unsupported by extension")
    if kind:
        raise BackendError(f"GNOME extension error {kind!r}: {message}")


__all__ = ["MutterBackend"]
