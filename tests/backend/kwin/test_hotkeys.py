"""Unit tests for the hotkey parser + MockHotkeyProvider + choose_provider.

The live ``KGlobalAccelProvider`` needs a session bus and a running
KGlobalAccel; it's covered in the ``@pytest.mark.kwin`` integration
suite. Here we test the parser, the mock provider's contract, and the
``choose_provider`` selector.
"""

from __future__ import annotations

from typing import Any

import pytest

from perch.backend.kwin.hotkeys import (
    HotkeyBusyError,
    HotkeyParseError,
    KGlobalAccelProvider,
    MockHotkeyProvider,
    ParsedAccel,
    _accel_to_qt_key,
    choose_provider,
    generate_callback_id,
    parse_accel,
)

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
