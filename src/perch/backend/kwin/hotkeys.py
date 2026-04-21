"""Global hotkey registration for the KWin backend.

Two providers, picked by :func:`choose_provider` at start:

* :class:`PortalGlobalShortcutsProvider` — preferred when the XDG
  Desktop Portal's GlobalShortcuts interface is reachable (Flatpak
  installs, modern Plasma with xdg-desktop-portal-kde ≥ 6, GNOME with
  xdg-desktop-portal-gnome). Routes through the portal so a sandboxed
  app has the same rebinding UX as a native one.
* :class:`KGlobalAccelProvider` — the fallback for non-Flatpak Plasma
  installs where the portal isn't wired or kdeneon-lean sessions where
  only KGlobalAccel is present. Hotkeys show up in KDE System Settings
  → Shortcuts under the "Perch" component.

Both paths share the :class:`HotkeyProvider` protocol and the
:class:`ParsedAccel` parser. Unit tests use :class:`MockHotkeyProvider`;
the live path is exercised in the ``@pytest.mark.kwin`` integration
suite.
"""

from __future__ import annotations

import asyncio
import logging
import os
import secrets
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any, Protocol

from sdbus import (
    DbusInterfaceCommonAsync,
    dbus_method_async,
    dbus_signal_async,
)

log = logging.getLogger("perch.backend.kwin.hotkeys")


#: Name of the component KGlobalAccel uses to group Perch's hotkeys. The
#: string appears in KDE System Settings; keep it human-readable.
KGLOBAL_ACCEL_COMPONENT = "perch"
KGLOBAL_ACCEL_COMPONENT_FRIENDLY = "Perch"


class HotkeyParseError(ValueError):
    """Raised when a portable accelerator string cannot be parsed."""


class HotkeyBusyError(RuntimeError):
    """Raised when the compositor refuses to bind a hotkey.

    Surfaces as a user-facing "hotkey unavailable" message. The backend
    translates this into a ``backend_error`` signal per docs/03 rather
    than letting it propagate out of ``register_hotkey``.
    """


class HotkeyProvider(Protocol):
    """Pluggable hotkey backend.

    Providers own their own lifecycle; :meth:`start` wires the signal
    subscription needed before :meth:`register` / :meth:`unregister` can
    be called. Concrete implementations: :class:`KGlobalAccelProvider`
    and :class:`MockHotkeyProvider` (for tests).
    """

    async def start(self, on_fired: Callable[[str], None]) -> None: ...
    async def stop(self) -> None: ...
    async def register(self, callback_id: str, accel: str, *, description: str = "") -> None: ...
    async def unregister(self, callback_id: str) -> None: ...


# ── Portable accelerator parsing ───────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class ParsedAccel:
    """Normalised form of a portable accelerator string.

    Split into modifiers and a single key. Providers re-render to their
    native form via :meth:`kglobalaccel_trigger` (and, in a future
    milestone, :meth:`portal_trigger`).
    """

    modifiers: tuple[str, ...]
    key: str

    def kglobalaccel_trigger(self) -> str:
        """KGlobalAccel-style, e.g. ``'Ctrl+Shift+Q'``."""
        return "+".join([*self.modifiers, self.key])


_MODIFIER_ALIASES: dict[str, str] = {
    "CTRL": "Ctrl",
    "CONTROL": "Ctrl",
    "SHIFT": "Shift",
    "ALT": "Alt",
    "META": "Meta",
    "SUPER": "Meta",
    "WIN": "Meta",
}


def parse_accel(accel: str) -> ParsedAccel:
    """Parse ``"Ctrl+Alt+Q"`` → :class:`ParsedAccel`.

    Accepts any case for modifier tokens; the key token's case is
    preserved (KGlobalAccel is case-sensitive for keysym names like
    ``F12`` vs ``f12``).
    """
    if not accel or not accel.strip():
        raise HotkeyParseError("empty accelerator")
    trimmed = accel.strip()
    if trimmed.startswith("+") or trimmed.endswith("+"):
        raise HotkeyParseError(f"leading or trailing '+' in {accel!r}")
    raw_parts = [p.strip() for p in trimmed.split("+")]
    if any(not p for p in raw_parts):
        raise HotkeyParseError(f"empty token in {accel!r}")
    key_token = raw_parts[-1]
    mod_tokens = raw_parts[:-1]
    # Reject "Ctrl" (a bare modifier) — the user forgot the key.
    if key_token.upper() in _MODIFIER_ALIASES:
        raise HotkeyParseError(f"missing key in {accel!r} (key must not be a modifier)")
    modifiers: list[str] = []
    for tok in mod_tokens:
        canonical = _MODIFIER_ALIASES.get(tok.upper())
        if canonical is None:
            raise HotkeyParseError(f"unknown modifier {tok!r} in {accel!r}")
        if canonical in modifiers:
            raise HotkeyParseError(f"duplicate modifier {tok!r} in {accel!r}")
        modifiers.append(canonical)
    if not key_token:
        raise HotkeyParseError(f"missing key in {accel!r}")
    # Deterministic modifier order: Ctrl, Alt, Shift, Meta — matches
    # what KGlobalAccel and most docs render.
    order = {"Ctrl": 0, "Alt": 1, "Shift": 2, "Meta": 3}
    modifiers.sort(key=lambda m: order.get(m, 99))
    return ParsedAccel(modifiers=tuple(modifiers), key=key_token)


# ── Mock provider (for tests + the "never start" case) ─────────────────────


@dataclass
class MockHotkeyProvider:
    """In-memory hotkey provider. Used by unit tests and when there's no
    session bus (e.g. running ``pytest`` outside a desktop session).
    """

    bindings: dict[str, ParsedAccel] = field(default_factory=dict)
    started: bool = False
    on_fired: Callable[[str], None] | None = None
    busy: set[str] = field(default_factory=set)  # accels that should fail to bind

    async def start(self, on_fired: Callable[[str], None]) -> None:
        self.started = True
        self.on_fired = on_fired

    async def stop(self) -> None:
        self.started = False
        self.on_fired = None
        self.bindings.clear()

    async def register(
        self, callback_id: str, accel: str, *, description: str = ""
    ) -> None:
        parsed = parse_accel(accel)
        if parsed.kglobalaccel_trigger() in self.busy:
            raise HotkeyBusyError(f"{accel} is already grabbed")
        self.bindings[callback_id] = parsed

    async def unregister(self, callback_id: str) -> None:
        self.bindings.pop(callback_id, None)

    def fire(self, callback_id: str) -> None:
        """Test helper: simulate the compositor firing a hotkey."""
        if self.on_fired is not None and callback_id in self.bindings:
            self.on_fired(callback_id)


# ── KGlobalAccel provider ──────────────────────────────────────────────────


class KGlobalAccelProxy(
    DbusInterfaceCommonAsync,
    interface_name="org.kde.KGlobalAccel",
):
    """Proxy for ``/kglobalaccel`` on ``org.kde.kglobalaccel``.

    KF 5.90+ API: :meth:`set_shortcut_keys` replaces the deprecated
    :meth:`setShortcut`. ``loading`` is a bool-shaped int: ``False``
    (``Explicit``) for user registration, ``True`` (``Autoloading``) to
    read stored user overrides.
    """

    @dbus_method_async(
        input_signature="asaib", result_signature="ai", method_name="setShortcutKeys"
    )
    async def set_shortcut_keys(  # type: ignore[empty-body]
        self,
        action_id: list[str],
        keys: list[int],
        loading: bool,
    ) -> list[int]: ...

    @dbus_method_async(
        input_signature="as", result_signature="", method_name="unregister"
    )
    async def unregister(self, action_id: list[str]) -> None: ...

    @dbus_signal_async(signal_name="globalShortcutPressed")
    def global_shortcut_pressed(  # type: ignore[empty-body]
        self,
    ) -> tuple[str, str, int]: ...


def _accel_to_qt_key(parsed: ParsedAccel) -> int:
    """Convert a :class:`ParsedAccel` into Qt's compact ``int`` key encoding.

    Qt encodes "modifiers | key" as a single int; KGlobalAccel takes that
    encoding for the second argument to ``setShortcutKeys``. Supported
    keys: single printable characters (letters / digits) and ``F1``..``F35``.
    Named special keys (``Return``, ``Escape``, …) raise
    :class:`HotkeyParseError` — the portal path will take over in M8 and
    cover the full Qt::Key enum; KGlobalAccel-only installs can rebind
    via System Settings if the user needs a named key.
    """
    # Qt modifier flags (Qt::KeyboardModifier in qnamespace.h):
    #   ShiftModifier    = 0x02000000
    #   ControlModifier  = 0x04000000
    #   AltModifier      = 0x08000000
    #   MetaModifier     = 0x10000000
    mod_flags = 0
    for m in parsed.modifiers:
        if m == "Shift":
            mod_flags |= 0x02000000
        elif m == "Ctrl":
            mod_flags |= 0x04000000
        elif m == "Alt":
            mod_flags |= 0x08000000
        elif m == "Meta":
            mod_flags |= 0x10000000
    key_upper = parsed.key.upper()
    # F-keys: Qt::Key_F1 = 0x01000030, Key_F35 = 0x01000052.
    if key_upper.startswith("F") and key_upper[1:].isdigit():
        n = int(key_upper[1:])
        if 1 <= n <= 35:
            return mod_flags | (0x01000030 + (n - 1))
    # Single printable character: Qt uses the Unicode codepoint directly
    # for letters/digits (A=0x41, 0=0x30, …).
    if len(key_upper) == 1:
        return mod_flags | ord(key_upper)
    raise HotkeyParseError(
        f"KGlobalAccel doesn't know how to encode key {parsed.key!r}; "
        "use a letter, digit, or Fn key until portal support lands"
    )


@dataclass
class KGlobalAccelProvider:
    """KGlobalAccel-backed hotkey provider. The v1 path."""

    _proxy: KGlobalAccelProxy | None = None
    _actions: dict[str, list[str]] = field(default_factory=dict)
    _signal_task: asyncio.Task[None] | None = None
    _on_fired: Callable[[str], None] | None = None

    async def start(self, on_fired: Callable[[str], None]) -> None:
        self._on_fired = on_fired
        self._proxy = KGlobalAccelProxy.new_proxy(
            "org.kde.kglobalaccel", "/kglobalaccel"
        )
        self._signal_task = asyncio.create_task(self._pump_signals())

    async def stop(self) -> None:
        if self._signal_task is not None:
            self._signal_task.cancel()
            try:
                await self._signal_task
            except asyncio.CancelledError:
                pass
            except Exception as exc:
                log.debug("signal pump stop raised: %s", exc)
            self._signal_task = None
        if self._proxy is not None:
            for action_id in list(self._actions.values()):
                try:
                    await self._proxy.unregister(action_id)
                except Exception as exc:
                    log.debug("KGlobalAccel unregister during stop: %s", exc)
            self._proxy = None
        self._actions.clear()
        self._on_fired = None

    async def register(
        self, callback_id: str, accel: str, *, description: str = ""
    ) -> None:
        if self._proxy is None:
            raise RuntimeError("provider not started")
        parsed = parse_accel(accel)
        key_int = _accel_to_qt_key(parsed)
        action_id = [
            KGLOBAL_ACCEL_COMPONENT,
            callback_id,
            KGLOBAL_ACCEL_COMPONENT_FRIENDLY,
            description or callback_id,
        ]
        try:
            granted = await self._proxy.set_shortcut_keys(action_id, [key_int], False)
        except Exception as exc:
            raise HotkeyBusyError(
                f"KGlobalAccel refused to bind {accel!r}: {exc}"
            ) from exc
        if not granted or key_int not in granted:
            # KGlobalAccel returned a different keysym — a conflicting
            # binding was already in place.
            raise HotkeyBusyError(f"{accel!r} is already grabbed")
        self._actions[callback_id] = action_id

    async def unregister(self, callback_id: str) -> None:
        if self._proxy is None:
            return
        action_id = self._actions.pop(callback_id, None)
        if action_id is None:
            return
        try:
            await self._proxy.unregister(action_id)
        except Exception as exc:
            log.debug("KGlobalAccel unregister: %s", exc)

    async def _pump_signals(self) -> None:
        """Long-lived task: deliver every ``globalShortcutPressed`` signal."""
        assert self._proxy is not None
        async for signal in self._proxy.global_shortcut_pressed.catch():
            component, action_id, _timestamp = signal
            if component != KGLOBAL_ACCEL_COMPONENT:
                continue
            if self._on_fired is not None:
                self._on_fired(action_id)


# ── Portal GlobalShortcuts provider ────────────────────────────────────────
#
# XDG Desktop Portal interface: ``org.freedesktop.portal.GlobalShortcuts``.
# Reference: https://flatpak.github.io/xdg-desktop-portal/docs/#gdbus-org.freedesktop.portal.GlobalShortcuts
#
# Protocol flow:
#   1. CreateSession(options) → Request path (o). Caller pre-subscribes
#      to Request.Response on that path; the response carries the
#      session_handle we use for every subsequent call.
#   2. BindShortcuts(session, shortcuts, parent_window, options) → Request
#      path. Response confirms the final accelerator assigned (the user
#      can override it in the portal's UI — so the bound trigger may
#      differ from preferred_trigger).
#   3. GlobalShortcuts.Activated(session, shortcut_id, timestamp, options)
#      fires when the user presses a bound shortcut. We dispatch to the
#      registered on_fired callback via the shortcut_id.
#
# All accel values are XDG-format (``LOGO+q``, ``CTRL+SHIFT+f12``). The
# translator from portable form lives inline so this module doesn't
# import UI code.


#: Small map used by :func:`_portable_to_xdg_accel` — it's deliberately
#: inline (not imported from ``perch.ui.widgets``) so the backend layer
#: stays free of a UI module import.
_PORTABLE_TO_XDG_MODS: dict[str, str] = {
    "meta": "LOGO",
    "ctrl": "CTRL",
    "alt": "ALT",
    "shift": "SHIFT",
}


def _portable_to_xdg_accel(accel: str) -> str:
    """Translate a portable-text accel ("Ctrl+Shift+Q") to XDG form
    ("CTRL+SHIFT+q"). Modifiers map; the final key name is preserved.
    """
    if not accel:
        return ""
    parts = [p for p in accel.split("+") if p != ""]
    out: list[str] = []
    for part in parts:
        lowered = part.lower()
        if lowered in _PORTABLE_TO_XDG_MODS:
            out.append(_PORTABLE_TO_XDG_MODS[lowered])
        else:
            out.append(part)
    return "+".join(out)


#: Portal service name / object path. The GlobalShortcuts interface lives
#: on the same root portal object as all other portal interfaces.
PORTAL_SERVICE = "org.freedesktop.portal.Desktop"
PORTAL_OBJECT = "/org/freedesktop/portal/desktop"


#: Portal Request response codes (xdg-desktop-portal/docs §Request).
PORTAL_RESPONSE_SUCCESS = 0
PORTAL_RESPONSE_CANCELLED = 1
PORTAL_RESPONSE_OTHER_ERROR = 2


class PortalGlobalShortcutsProxy(
    DbusInterfaceCommonAsync,
    interface_name="org.freedesktop.portal.GlobalShortcuts",
):
    """Proxy for ``/org/freedesktop/portal/desktop`` on ``org.freedesktop.portal.Desktop``."""

    @dbus_method_async(
        input_signature="a{sv}", result_signature="o", method_name="CreateSession"
    )
    async def create_session(  # type: ignore[empty-body]
        self, options: dict[str, tuple[str, Any]]
    ) -> str: ...

    @dbus_method_async(
        input_signature="oa(sa{sv})sa{sv}",
        result_signature="o",
        method_name="BindShortcuts",
    )
    async def bind_shortcuts(  # type: ignore[empty-body]
        self,
        session_handle: str,
        shortcuts: list[tuple[str, dict[str, tuple[str, Any]]]],
        parent_window: str,
        options: dict[str, tuple[str, Any]],
    ) -> str: ...

    @dbus_method_async(
        input_signature="oa{sv}",
        result_signature="o",
        method_name="ListShortcuts",
    )
    async def list_shortcuts(  # type: ignore[empty-body]
        self, session_handle: str, options: dict[str, tuple[str, Any]]
    ) -> str: ...

    @dbus_signal_async(signal_name="Activated")
    def activated(  # type: ignore[empty-body]
        self,
    ) -> tuple[str, str, int, dict[str, tuple[str, Any]]]: ...


class PortalRequestProxy(
    DbusInterfaceCommonAsync,
    interface_name="org.freedesktop.portal.Request",
):
    """Proxy for per-request objects (``/org/freedesktop/portal/desktop/request/...``)."""

    @dbus_signal_async(signal_name="Response")
    def response(  # type: ignore[empty-body]
        self,
    ) -> tuple[int, dict[str, tuple[str, Any]]]: ...


def _unwrap_variant(value: Any) -> Any:
    """Unwrap a sdbus-python variant tuple ``(sig, value)`` to its value.

    Portal dicts are ``a{sv}`` — every value arrives as ``(signature, v)``.
    This is a narrow helper; callers that know the exact shape decode
    specific fields directly.
    """
    if isinstance(value, tuple) and len(value) == 2 and isinstance(value[0], str):
        return value[1]
    return value


#: Factory type for a portal proxy — tests inject fakes here.
PortalProxyFactory = Callable[[], "PortalGlobalShortcutsProxy"]
#: Factory type for a per-request proxy — tests inject fakes here.
RequestProxyFactory = Callable[[str], "PortalRequestProxy"]


def _default_portal_factory() -> PortalGlobalShortcutsProxy:
    return PortalGlobalShortcutsProxy.new_proxy(PORTAL_SERVICE, PORTAL_OBJECT)


def _default_request_factory(path: str) -> PortalRequestProxy:
    return PortalRequestProxy.new_proxy(PORTAL_SERVICE, path)


@dataclass
class PortalGlobalShortcutsProvider:
    """GlobalShortcuts-portal hotkey provider.

    Parameters are all injection seams for tests; production callers let
    them default. The factories let tests drop in an in-memory fake
    portal without reaching for sdbus internals.
    """

    parent_window: str = ""
    portal_factory: PortalProxyFactory = field(default=_default_portal_factory)
    request_factory: RequestProxyFactory = field(default=_default_request_factory)
    response_timeout_s: float = 10.0

    _portal: PortalGlobalShortcutsProxy | None = None
    _session_handle: str | None = None
    _activated_task: asyncio.Task[None] | None = None
    _bindings: dict[str, ParsedAccel] = field(default_factory=dict)
    _on_fired: Callable[[str], None] | None = None

    async def start(self, on_fired: Callable[[str], None]) -> None:
        self._on_fired = on_fired
        self._portal = self.portal_factory()
        self._session_handle = await self._create_session()
        self._activated_task = asyncio.create_task(self._pump_activated())

    async def stop(self) -> None:
        if self._activated_task is not None:
            self._activated_task.cancel()
            try:
                await self._activated_task
            except asyncio.CancelledError:
                pass
            except Exception as exc:
                log.debug("portal activated pump stop: %s", exc)
            self._activated_task = None
        # Portal sessions have a Close method too, but sdbus-python's
        # stateless proxies aren't ideal for per-session cleanup — the
        # session auto-closes when the client disconnects from the bus.
        # For our purposes letting the session die with the bus is the
        # safer default than a per-session proxy at this layer.
        self._session_handle = None
        self._portal = None
        self._bindings.clear()
        self._on_fired = None

    async def register(
        self, callback_id: str, accel: str, *, description: str = ""
    ) -> None:
        if self._portal is None or self._session_handle is None:
            raise RuntimeError("provider not started")
        parsed = parse_accel(accel)
        trigger = _portable_to_xdg_accel(parsed.kglobalaccel_trigger())
        shortcut = (
            callback_id,
            {
                "description": ("s", description or callback_id),
                "preferred_trigger": ("s", trigger),
            },
        )
        request_path = await self._portal.bind_shortcuts(
            self._session_handle, [shortcut], self.parent_window, {}
        )
        response = await self._await_response(request_path)
        if response is None:
            raise HotkeyBusyError(
                f"portal refused to bind {accel!r}: no response"
            )
        status, _results = response
        if status == PORTAL_RESPONSE_CANCELLED:
            raise HotkeyBusyError(
                f"user cancelled portal binding for {accel!r}"
            )
        if status != PORTAL_RESPONSE_SUCCESS:
            raise HotkeyBusyError(
                f"portal refused to bind {accel!r} (status={status})"
            )
        self._bindings[callback_id] = parsed

    async def unregister(self, callback_id: str) -> None:
        # The GlobalShortcuts portal doesn't expose UnbindShortcuts in
        # the current spec — the only way to drop a binding is to rebind
        # the session with the remaining set or close the session. We
        # evict from our local map so the Activated signal ignores
        # future presses of this id; the portal continues to show the
        # shortcut in its list until session close, which is the expected
        # lifecycle under the spec today.
        self._bindings.pop(callback_id, None)

    async def _create_session(self) -> str:
        assert self._portal is not None
        handle_token = _secure_token()
        session_token = _secure_token()
        options: dict[str, tuple[str, Any]] = {
            "handle_token": ("s", handle_token),
            "session_handle_token": ("s", session_token),
        }
        request_path = await self._portal.create_session(options)
        response = await self._await_response(request_path)
        if response is None:
            raise BackendDisconnectedProvider(
                "portal CreateSession: no response"
            )
        status, results = response
        if status != PORTAL_RESPONSE_SUCCESS:
            raise BackendDisconnectedProvider(
                f"portal CreateSession failed (status={status})"
            )
        handle = _unwrap_variant(results.get("session_handle"))
        if not isinstance(handle, str) or not handle:
            raise BackendDisconnectedProvider(
                f"portal CreateSession returned no session_handle: {results!r}"
            )
        return handle

    async def _await_response(
        self, request_path: str
    ) -> tuple[int, dict[str, Any]] | None:
        """Subscribe to Request.Response on ``request_path`` and return the
        first signal received, unwrapped.

        Returns ``None`` on timeout so callers can surface a clean
        :class:`HotkeyBusyError` instead of a bare ``TimeoutError``.
        """
        request = self.request_factory(request_path)
        iterator = request.response.catch()
        try:
            payload = await asyncio.wait_for(
                iterator.__anext__(), timeout=self.response_timeout_s
            )
        except TimeoutError:
            return None
        status, results = payload
        # Variant-unwrap the dict values so the caller sees raw Python types.
        unwrapped = {k: _unwrap_variant(v) for k, v in results.items()}
        return int(status), unwrapped

    async def _pump_activated(self) -> None:
        """Long-lived task: fan ``Activated`` signals into ``on_fired``."""
        assert self._portal is not None
        async for signal in self._portal.activated.catch():
            session_handle, shortcut_id, _timestamp, _opts = signal
            if session_handle != self._session_handle:
                continue
            if self._on_fired is not None and shortcut_id in self._bindings:
                self._on_fired(shortcut_id)


class BackendDisconnectedProvider(RuntimeError):
    """Raised when the portal path can't establish a session.

    Separate from :class:`BackendDisconnected` in ``perch.backend.base``
    because this layer doesn't import backend types. :func:`choose_provider`
    catches it and falls back to KGlobalAccel.
    """


def _secure_token() -> str:
    """Return a portal-safe handle token.

    Portal tokens must match ``^[a-zA-Z0-9_]+$``. :mod:`secrets.token_hex`
    already satisfies this and gives us 16 hex chars of entropy.
    """
    return secrets.token_hex(8)


def _is_portal_available(factory: PortalProxyFactory) -> Awaitable[bool]:
    """Return True when the portal exposes GlobalShortcuts.

    Probes by creating a session and closing it immediately. This is
    heavier than a pure interface-introspection probe but uniquely
    tells us the backing portal impl actually supports GlobalShortcuts
    (xdg-desktop-portal-kde before 6 advertises the interface but fails
    every call).
    """

    async def _probe() -> bool:
        try:
            portal = factory()
            handle_token = _secure_token()
            session_token = _secure_token()
            options: dict[str, tuple[str, Any]] = {
                "handle_token": ("s", handle_token),
                "session_handle_token": ("s", session_token),
            }
            # CreateSession returns a Request path; if the portal method
            # is missing we see an sdbus DbusUnknownMethodError here.
            # We don't actually wait for the response — its existence
            # proves GlobalShortcuts is wired.
            await portal.create_session(options)
            return True
        except Exception as exc:
            log.debug("portal GlobalShortcuts probe failed: %s", exc)
            return False

    return _probe()


# ── Provider selection ─────────────────────────────────────────────────────


_ProviderFactory = Callable[[], "HotkeyProvider"]
_PortalAvailabilityProbe = Callable[[], Awaitable[bool]]


async def choose_provider(
    on_fired: Callable[[str], None],
    *,
    kglobal_factory: _ProviderFactory | None = None,
    portal_factory: _ProviderFactory | None = None,
    portal_available: _PortalAvailabilityProbe | None = None,
) -> HotkeyProvider:
    """Build and start the appropriate hotkey provider.

    Selection priority:

    1. ``PERCH_HOTKEY_PROVIDER=mock`` → :class:`MockHotkeyProvider`.
    2. Environment signals a Flatpak sandbox **or** the caller passes an
       explicit ``portal_factory`` → probe GlobalShortcuts portal and
       use it if available.
    3. Fallback: :class:`KGlobalAccelProvider`.

    ``kglobal_factory`` / ``portal_factory`` are DI seams for tests.
    ``portal_available`` overrides the default "CreateSession-probe"
    availability check — tests wire a bool-returning callable so they
    don't need a real portal on the bus.
    """
    env_value = os.environ.get("PERCH_HOTKEY_PROVIDER", "").strip().lower()
    if env_value == "mock":
        mock = MockHotkeyProvider()
        await mock.start(on_fired)
        return mock
    if env_value == "kglobalaccel":
        return await _start_kglobalaccel(on_fired, kglobal_factory)
    if env_value == "portal":
        return await _start_portal(on_fired, portal_factory)

    # Default policy: probe portal whenever the environment either says
    # we're sandboxed or the caller gave us an explicit factory.
    from pathlib import Path as _Path

    in_sandbox = _Path("/.flatpak-info").is_file()
    should_probe_portal = in_sandbox or portal_factory is not None
    if should_probe_portal:
        probe = portal_available or (
            lambda: _is_portal_available(_default_portal_factory)
        )
        if await probe():
            return await _start_portal(on_fired, portal_factory)
        log.info(
            "portal GlobalShortcuts unavailable; falling back to KGlobalAccel"
        )
    return await _start_kglobalaccel(on_fired, kglobal_factory)


async def _start_kglobalaccel(
    on_fired: Callable[[str], None],
    kglobal_factory: _ProviderFactory | None,
) -> HotkeyProvider:
    factory = kglobal_factory or KGlobalAccelProvider
    provider = factory()
    await provider.start(on_fired)
    log.info("hotkey provider: KGlobalAccel")
    return provider


async def _start_portal(
    on_fired: Callable[[str], None],
    portal_factory: _ProviderFactory | None,
) -> HotkeyProvider:
    factory = portal_factory or PortalGlobalShortcutsProvider
    provider = factory()
    await provider.start(on_fired)
    log.info("hotkey provider: Portal GlobalShortcuts")
    return provider


def generate_callback_id() -> str:
    """Short opaque id for an internal hotkey registration."""
    return f"perch-{uuid.uuid4().hex[:8]}"


__all__ = [
    "KGLOBAL_ACCEL_COMPONENT",
    "KGLOBAL_ACCEL_COMPONENT_FRIENDLY",
    "PORTAL_OBJECT",
    "PORTAL_RESPONSE_CANCELLED",
    "PORTAL_RESPONSE_OTHER_ERROR",
    "PORTAL_RESPONSE_SUCCESS",
    "PORTAL_SERVICE",
    "BackendDisconnectedProvider",
    "HotkeyBusyError",
    "HotkeyParseError",
    "HotkeyProvider",
    "KGlobalAccelProvider",
    "MockHotkeyProvider",
    "ParsedAccel",
    "PortalGlobalShortcutsProvider",
    "choose_provider",
    "generate_callback_id",
    "parse_accel",
]
