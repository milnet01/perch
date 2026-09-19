"""Unit tests for the hotkey parser + MockHotkeyProvider + choose_provider.

The live ``KGlobalAccelProvider`` / ``PortalGlobalShortcutsProvider``
both need a session bus and a running service; they're covered in the
``@pytest.mark.kwin`` integration suite. Here we test the parser, the
mock provider's contract, the ``choose_provider`` selector, and the
portal path's protocol flow against an in-memory fake portal.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from perch.backend.kwin.hotkeys import (
    PORTAL_RESPONSE_CANCELLED,
    PORTAL_RESPONSE_SUCCESS,
    BackendDisconnectedProvider,
    HotkeyBusyError,
    HotkeyParseError,
    KGlobalAccelProvider,
    MockHotkeyProvider,
    ParsedAccel,
    PortalGlobalShortcutsProvider,
    _accel_to_qt_key,
    _portable_to_xdg_accel,
    choose_provider,
    generate_callback_id,
    parse_accel,
)
from perch.portal import request_path

# ── parse_accel ───────────────────────────────────────────────────────────


def test_parse_accel_single_key() -> None:
    assert parse_accel("F12") == ParsedAccel(modifiers=(), key="F12")


def test_parse_accel_with_modifiers() -> None:
    parsed = parse_accel("Ctrl+Alt+Q")
    assert parsed.modifiers == ("Ctrl", "Alt")
    assert parsed.key == "Q"


def test_parse_accel_is_case_insensitive_for_modifiers() -> None:
    parsed = parse_accel("ctrl+ALT+F5")
    assert parsed.modifiers == ("Ctrl", "Alt")
    assert parsed.key == "F5"


def test_parse_accel_preserves_key_case() -> None:
    p1 = parse_accel("F12")
    p2 = parse_accel("f12")
    assert p1.key == "F12"
    assert p2.key == "f12"


def test_parse_accel_deterministic_modifier_order() -> None:
    # The input order shouldn't affect the output order.
    a = parse_accel("Shift+Ctrl+F12")
    b = parse_accel("Ctrl+Shift+F12")
    assert a.modifiers == b.modifiers == ("Ctrl", "Shift")


def test_parse_accel_rejects_empty() -> None:
    with pytest.raises(HotkeyParseError):
        parse_accel("")
    with pytest.raises(HotkeyParseError):
        parse_accel("   ")


def test_parse_accel_rejects_duplicate_modifiers() -> None:
    with pytest.raises(HotkeyParseError, match="duplicate"):
        parse_accel("Ctrl+Ctrl+A")


def test_parse_accel_rejects_unknown_modifier() -> None:
    with pytest.raises(HotkeyParseError, match="unknown modifier"):
        parse_accel("Hyper+A")


def test_parse_accel_rejects_trailing_plus() -> None:
    with pytest.raises(HotkeyParseError):
        parse_accel("Ctrl+")


@pytest.mark.parametrize("alias,expected", [
    ("Super+A", "Meta"),
    ("Win+A", "Meta"),
    ("CONTROL+A", "Ctrl"),
])
def test_parse_accel_modifier_aliases(alias: str, expected: str) -> None:
    p = parse_accel(alias)
    assert p.modifiers == (expected,)


# ── kglobalaccel_trigger ──────────────────────────────────────────────────


def test_kglobalaccel_trigger_rendering() -> None:
    assert parse_accel("Ctrl+Alt+Q").kglobalaccel_trigger() == "Ctrl+Alt+Q"


# ── _accel_to_qt_key ──────────────────────────────────────────────────────


def test_qt_key_encodes_f12_with_ctrl_alt() -> None:
    parsed = parse_accel("Ctrl+Alt+F12")
    # Qt::Key_F12 = 0x01000030 + 11 = 0x0100003B
    # Ctrl = 0x04000000, Alt = 0x08000000
    expected = 0x04000000 | 0x08000000 | 0x0100003B
    assert _accel_to_qt_key(parsed) == expected


def test_qt_key_encodes_letter() -> None:
    parsed = parse_accel("Meta+Q")
    expected = 0x10000000 | ord("Q")
    assert _accel_to_qt_key(parsed) == expected


def test_qt_key_rejects_named_key() -> None:
    with pytest.raises(HotkeyParseError, match="doesn't know how to encode"):
        _accel_to_qt_key(parse_accel("Ctrl+Return"))


def test_qt_key_rejects_f0_and_f36() -> None:
    with pytest.raises(HotkeyParseError):
        _accel_to_qt_key(parse_accel("F0"))
    with pytest.raises(HotkeyParseError):
        _accel_to_qt_key(parse_accel("F36"))


# ── MockHotkeyProvider ────────────────────────────────────────────────────


async def test_mock_register_and_fire_round_trip() -> None:
    provider = MockHotkeyProvider()
    fired: list[str] = []
    await provider.start(fired.append)
    await provider.register("cb-1", "Ctrl+Alt+F12")
    provider.fire("cb-1")
    assert fired == ["cb-1"]


async def test_mock_unregistered_fire_is_dropped() -> None:
    provider = MockHotkeyProvider()
    fired: list[str] = []
    await provider.start(fired.append)
    provider.fire("never-registered")
    assert fired == []


async def test_mock_stop_clears_bindings() -> None:
    provider = MockHotkeyProvider()
    await provider.start(lambda _cid: None)
    await provider.register("cb-1", "Ctrl+A")
    await provider.stop()
    assert provider.bindings == {}
    assert provider.started is False


async def test_mock_busy_raises_hotkey_busy_error() -> None:
    provider = MockHotkeyProvider(busy={"Ctrl+Alt+F12"})
    await provider.start(lambda _cid: None)
    with pytest.raises(HotkeyBusyError):
        await provider.register("cb-1", "Ctrl+Alt+F12")


async def test_mock_register_rejects_invalid_accel() -> None:
    provider = MockHotkeyProvider()
    await provider.start(lambda _cid: None)
    with pytest.raises(HotkeyParseError):
        await provider.register("cb-1", "NotAMod+Q")


# ── choose_provider ───────────────────────────────────────────────────────


async def test_choose_provider_respects_mock_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PERCH_HOTKEY_PROVIDER", "mock")
    provider = await choose_provider(lambda _cid: None)
    assert isinstance(provider, MockHotkeyProvider)
    assert provider.started is True


async def test_choose_provider_uses_injected_factory(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("PERCH_HOTKEY_PROVIDER", raising=False)
    kglob = MockHotkeyProvider()
    # Use MockHotkeyProvider in place of KGlobalAccel so we never hit
    # the bus; the factory just returns it.
    def _factory() -> Any:
        return kglob

    provider = await choose_provider(lambda _cid: None, kglobal_factory=_factory)
    assert provider is kglob
    assert kglob.started is True


# ── KGlobalAccelProvider — no-bus checks ──────────────────────────────────


def test_kglobalaccel_provider_instantiable_without_start() -> None:
    # Construction alone must not hit the bus.
    provider = KGlobalAccelProvider()
    assert provider._proxy is None


async def test_kglobalaccel_provider_register_without_start_raises() -> None:
    provider = KGlobalAccelProvider()
    with pytest.raises(RuntimeError, match="not started"):
        await provider.register("cb-1", "Ctrl+A")


async def test_kglobalaccel_provider_stop_on_never_started_is_noop() -> None:
    provider = KGlobalAccelProvider()
    await provider.stop()  # must not raise


# ── generate_callback_id ─────────────────────────────────────────────────


def test_generate_callback_id_is_prefixed_and_unique() -> None:
    ids = {generate_callback_id() for _ in range(50)}
    assert len(ids) == 50
    assert all(i.startswith("perch-") for i in ids)


# ── Portal: accel translation ─────────────────────────────────────────────


def test_portable_to_xdg_letter_combo() -> None:
    assert _portable_to_xdg_accel("Ctrl+Shift+Q") == "CTRL+SHIFT+Q"


def test_portable_to_xdg_meta_becomes_logo() -> None:
    assert _portable_to_xdg_accel("Meta+Space") == "LOGO+Space"


def test_portable_to_xdg_preserves_special_keys() -> None:
    assert _portable_to_xdg_accel("Ctrl+Left") == "CTRL+Left"


def test_portable_to_xdg_empty_input() -> None:
    assert _portable_to_xdg_accel("") == ""


def test_portable_to_xdg_keeps_the_plus_key() -> None:
    """PERC-0058: "+" is both separator and key; Qt writes the key as a
    trailing "+", and splitting then dropping empty fields lost it."""
    assert _portable_to_xdg_accel("Ctrl++") == "CTRL+plus"
    assert _portable_to_xdg_accel("Ctrl+Shift++") == "CTRL+SHIFT+plus"
    assert _portable_to_xdg_accel("+") == "plus"


# ── Portal: PortalGlobalShortcutsProvider flow (fake portal) ──────────────


class _FakeAsyncIterator:
    def __init__(self, items: list[tuple[int, dict[str, tuple[str, Any]]]]) -> None:
        self._items = list(items)
        # Park a never-completing future after items run out so the
        # provider's long-lived Activated pump doesn't see StopIteration
        # and crash the background task before the test finishes.
        self._done = asyncio.Event()

    def __aiter__(self) -> _FakeAsyncIterator:
        return self

    async def __anext__(self) -> tuple[int, dict[str, tuple[str, Any]]]:
        if self._items:
            return self._items.pop(0)
        # Block until the test tears the iterator down — catch() on a
        # real signal does the same (never raises StopAsyncIteration).
        await self._done.wait()
        raise StopAsyncIteration


_FAKE_SENDER = ":1.42"


class _FakeWaiter:
    def __init__(self) -> None:
        self.queue: asyncio.Queue[tuple[int, dict[str, Any]]] = asyncio.Queue()
        self.closed = False

    async def wait(self, timeout_s: float) -> tuple[int, dict[str, Any]] | None:
        try:
            return await asyncio.wait_for(self.queue.get(), timeout=timeout_s)
        except TimeoutError:
            return None

    def close(self) -> None:
        self.closed = True


class _FakePortal:
    """Minimal GlobalShortcuts portal fake.

    Records every call the provider makes so tests can assert protocol
    shape. It answers the way a fast real portal can: the Response is
    emitted DURING the method call, at the path derived from the caller's
    handle_token, and reaches only a subscription already in place — a
    caller that subscribes afterwards never sees it.
    """

    def __init__(
        self,
        *,
        session_response: tuple[int, dict[str, tuple[str, Any]]] | None = None,
        bind_response: tuple[int, dict[str, tuple[str, Any]]] | None = None,
    ) -> None:
        self.create_session_calls: list[dict[str, tuple[str, Any]]] = []
        self.bind_calls: list[
            tuple[str, list[Any], str, dict[str, tuple[str, Any]]]
        ] = []
        self.events: list[str] = []
        self._subscriptions: dict[str, _FakeWaiter] = {}
        self._session_response = session_response or (
            PORTAL_RESPONSE_SUCCESS,
            {"session_handle": ("o", "/org/freedesktop/portal/desktop/session/abc")},
        )
        self._bind_response = bind_response or (PORTAL_RESPONSE_SUCCESS, {})
        self._activated = _FakeAsyncIterator([])

    async def sender(self) -> str:
        return _FAKE_SENDER

    async def subscribe(self, path: str) -> _FakeWaiter:
        self.events.append(f"subscribe {path}")
        waiter = _FakeWaiter()
        self._subscriptions[path] = waiter
        return waiter

    def _respond(
        self,
        options: dict[str, tuple[str, Any]],
        payload: tuple[int, dict[str, Any]],
    ) -> str:
        path = request_path(_FAKE_SENDER, options["handle_token"][1])
        self.events.append(f"call {path}")
        waiter = self._subscriptions.get(path)
        if waiter is not None and not waiter.closed:
            waiter.queue.put_nowait(payload)
        return path

    async def create_session(
        self, options: dict[str, tuple[str, Any]]
    ) -> str:
        self.create_session_calls.append(options)
        return self._respond(options, self._session_response)

    async def bind_shortcuts(
        self,
        session_handle: str,
        shortcuts: list[Any],
        parent_window: str,
        options: dict[str, tuple[str, Any]],
    ) -> str:
        self.bind_calls.append((session_handle, shortcuts, parent_window, options))
        return self._respond(options, self._bind_response)

    @property
    def activated(self) -> _FakeAsyncIterator:
        # Real sdbus returns the signal object; the provider code calls
        # .catch() on it. We short-circuit by making .catch() return the
        # iterator directly — see _FakeAsyncIterator.catch pattern.
        return self._activated

    def provider(self, **kwargs: Any) -> PortalGlobalShortcutsProvider:
        return PortalGlobalShortcutsProvider(
            portal_factory=lambda: self,  # type: ignore[arg-type,return-value]
            response_subscriber=self.subscribe,
            sender_name=self.sender,
            response_timeout_s=1.0,
            **kwargs,
        )


# Teach _FakeAsyncIterator to act as its own catch() return so the
# provider code's ``portal.activated.catch()`` chain finds a thing to
# iterate. Attaching via monkey-patching the class keeps the fake in one
# module without needing a separate wrapper layer.
_FakeAsyncIterator.catch = lambda self: self  # type: ignore[attr-defined]


async def test_portal_provider_happy_path_creates_session_and_binds() -> None:
    fake = _FakePortal()
    provider = fake.provider()
    await provider.start(on_fired=lambda _cid: None)
    assert provider._session_handle == "/org/freedesktop/portal/desktop/session/abc"
    assert len(fake.create_session_calls) == 1
    # Session creation options must carry both tokens per the portal spec.
    session_opts = fake.create_session_calls[0]
    assert "handle_token" in session_opts
    assert "session_handle_token" in session_opts

    await provider.register("perch-quit", "Ctrl+Shift+Q", description="Quit")
    assert len(fake.bind_calls) == 1
    session_handle, shortcuts, parent_window, _opts = fake.bind_calls[0]
    assert session_handle == "/org/freedesktop/portal/desktop/session/abc"
    assert parent_window == ""
    assert len(shortcuts) == 1
    shortcut_id, sc_opts = shortcuts[0]
    assert shortcut_id == "perch-quit"
    assert sc_opts["preferred_trigger"] == ("s", "CTRL+SHIFT+Q")
    assert sc_opts["description"] == ("s", "Quit")

    await provider.stop()


async def test_portal_provider_subscribes_before_each_call() -> None:
    """PERC-0048: a Response can arrive before the method returns, so the
    match must be installed first — at the path predicted from the
    handle_token — or the reply is lost and the call times out."""
    fake = _FakePortal()
    provider = fake.provider()
    await provider.start(on_fired=lambda _cid: None)
    await provider.register("perch-quit", "Ctrl+Q")
    assert len(fake.events) == 4
    for sub, call in (fake.events[0:2], fake.events[2:4]):
        assert sub.startswith("subscribe ")
        assert call == "call " + sub.removeprefix("subscribe ")
    # Both calls carry a handle_token, which is what makes the path known.
    assert "handle_token" in fake.bind_calls[0][3]
    await provider.stop()


async def test_portal_provider_bind_cancelled_raises_busy() -> None:
    fake = _FakePortal(bind_response=(PORTAL_RESPONSE_CANCELLED, {}))
    provider = fake.provider()
    await provider.start(on_fired=lambda _cid: None)
    with pytest.raises(HotkeyBusyError):
        await provider.register("perch-quit", "Ctrl+Q")
    await provider.stop()


async def test_portal_provider_unregister_drops_from_local_map() -> None:
    fake = _FakePortal()
    provider = fake.provider()
    await provider.start(on_fired=lambda _cid: None)
    await provider.register("perch-quit", "Ctrl+Q")
    assert "perch-quit" in provider._bindings
    await provider.unregister("perch-quit")
    assert "perch-quit" not in provider._bindings
    await provider.stop()


async def test_portal_provider_register_before_start_raises() -> None:
    provider = PortalGlobalShortcutsProvider()
    with pytest.raises(RuntimeError, match="not started"):
        await provider.register("cb", "Ctrl+Q")


# ── choose_provider: portal routing ───────────────────────────────────────


async def test_choose_provider_env_portal_forces_portal_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PERCH_HOTKEY_PROVIDER", "portal")
    fake_provider = MockHotkeyProvider()

    def _factory() -> Any:
        return fake_provider

    provider = await choose_provider(
        lambda _cid: None, portal_factory=_factory
    )
    assert provider is fake_provider
    assert fake_provider.started is True


async def test_choose_provider_portal_probe_success_picks_portal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """With a portal factory given AND the probe returning True, portal wins."""
    monkeypatch.delenv("PERCH_HOTKEY_PROVIDER", raising=False)
    portal_like = MockHotkeyProvider()
    kglob_like = MockHotkeyProvider()

    async def _probe_yes() -> bool:
        return True

    provider = await choose_provider(
        lambda _cid: None,
        kglobal_factory=lambda: kglob_like,
        portal_factory=lambda: portal_like,
        portal_available=_probe_yes,
    )
    assert provider is portal_like
    assert kglob_like.started is False


async def test_choose_provider_portal_probe_failure_falls_back_to_kglobalaccel(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("PERCH_HOTKEY_PROVIDER", raising=False)
    portal_like = MockHotkeyProvider()
    kglob_like = MockHotkeyProvider()

    async def _probe_no() -> bool:
        return False

    provider = await choose_provider(
        lambda _cid: None,
        kglobal_factory=lambda: kglob_like,
        portal_factory=lambda: portal_like,
        portal_available=_probe_no,
    )
    assert provider is kglob_like
    assert portal_like.started is False


async def test_choose_provider_falls_back_when_the_portal_session_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """PERC-0048: the probe only proves CreateSession exists. A session
    that then fails raised out of the backend's start() instead of taking
    the documented KGlobalAccel fallback."""
    monkeypatch.delenv("PERCH_HOTKEY_PROVIDER", raising=False)
    kglob_like = MockHotkeyProvider()

    class _FailingPortal(MockHotkeyProvider):
        async def start(self, on_fired: Any) -> None:
            raise BackendDisconnectedProvider("portal CreateSession: no response")

    async def _probe_yes() -> bool:
        return True

    provider = await choose_provider(
        lambda _cid: None,
        kglobal_factory=lambda: kglob_like,
        portal_factory=_FailingPortal,
        portal_available=_probe_yes,
    )
    assert provider is kglob_like
    assert kglob_like.started is True


async def test_choose_provider_env_kglobalaccel_skips_probe(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PERCH_HOTKEY_PROVIDER", "kglobalaccel")
    kglob_like = MockHotkeyProvider()

    probe_calls: list[bool] = []

    async def _probe() -> bool:
        probe_calls.append(True)
        return True

    provider = await choose_provider(
        lambda _cid: None,
        kglobal_factory=lambda: kglob_like,
        portal_available=_probe,
    )
    assert provider is kglob_like
    assert probe_calls == []  # env override means we never probed


async def test_a_signal_pump_that_fails_is_restarted(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """PERC-0060: the pump loops ended silently on any bus error, killing
    every hotkey with no log line and no restart."""
    from perch.backend.kwin.hotkeys import _supervise_pump

    runs: list[int] = []
    parked = asyncio.Event()

    async def pump() -> None:
        runs.append(1)
        if len(runs) < 3:
            raise RuntimeError("bus error")
        await parked.wait()

    task = asyncio.create_task(_supervise_pump("test", pump, first_delay_s=0.0))
    for _ in range(20):
        await asyncio.sleep(0)
    assert len(runs) == 3
    assert "bus error" in caplog.text
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
