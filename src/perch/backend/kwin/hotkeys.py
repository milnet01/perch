"""Global hotkey registration for the KWin backend.

v1 ships **KGlobalAccel direct** (``org.kde.kglobalaccel``). It's present
on every current Plasma install and Perch's hotkeys show up in KDE
System Settings → Shortcuts under the "Perch" component, letting the
user rebind them.

The XDG Desktop Portal GlobalShortcuts path (``org.freedesktop.portal.
GlobalShortcuts``) is the future primary, tied to Flatpak packaging — it
works sandboxed and falls through to KGlobalAccel on KDE. That support
lands alongside the Flatpak manifest in the M8 milestone (see
``docs/11-roadmap.md``). Until then Perch uses KGlobalAccel directly,
which is the correct answer for every RPM / AUR / dev install anyway.

Both paths will share the :class:`HotkeyProvider` protocol and the
:class:`ParsedAccel` parser. Unit tests use :class:`MockHotkeyProvider`;
the real KGlobalAccel path is exercised in the live ``@pytest.mark.kwin``
integration suite.
"""

from __future__ import annotations

import asyncio
import logging
import os
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Protocol

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


# ── Provider selection ─────────────────────────────────────────────────────


_ProviderFactory = Callable[[], "HotkeyProvider"]


async def choose_provider(
    on_fired: Callable[[str], None],
    *,
    kglobal_factory: _ProviderFactory | None = None,
) -> HotkeyProvider:
    """Build and start the appropriate hotkey provider.

    For v1 this always returns :class:`KGlobalAccelProvider` (already
    started). The portal path (XDG Desktop Portal GlobalShortcuts) lands
    alongside Flatpak packaging in M8 and this function will probe it
    first at that point.

    Tests that don't want to hit the bus set
    ``PERCH_HOTKEY_PROVIDER=mock`` in the environment; this returns an
    already-started :class:`MockHotkeyProvider`.
    """
    if os.environ.get("PERCH_HOTKEY_PROVIDER") == "mock":
        mock = MockHotkeyProvider()
        await mock.start(on_fired)
        return mock

    provider: HotkeyProvider
    factory = kglobal_factory or KGlobalAccelProvider
    provider = factory()
    await provider.start(on_fired)
    log.info("hotkey provider: KGlobalAccel")
    return provider


def generate_callback_id() -> str:
    """Short opaque id for an internal hotkey registration."""
    return f"perch-{uuid.uuid4().hex[:8]}"


__all__ = [
    "KGLOBAL_ACCEL_COMPONENT",
    "KGLOBAL_ACCEL_COMPONENT_FRIENDLY",
    "HotkeyBusyError",
    "HotkeyParseError",
    "HotkeyProvider",
    "KGlobalAccelProvider",
    "MockHotkeyProvider",
    "ParsedAccel",
    "choose_provider",
    "generate_callback_id",
    "parse_accel",
]
