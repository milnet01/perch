"""Tests for :class:`KWinBackend` routing + enumeration + lifecycle.

No live D-Bus: ``start()``'s bus handshake and scripting proxy are injected
via ``bus_setup`` / ``scripting_factory`` / ``script_installer`` kwargs.
For the event-routing tests the backend is instantiated directly and the
:class:`EventSink` methods are driven by hand so Qt signal emission can be
verified without a bus.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock

import pytest
from PySide6.QtCore import QCoreApplication

from perch.backend.base import (
    BackendDisconnected,
    BackendUnavailable,
    UnknownOutput,
    UnknownWindow,
)
from perch.backend.kwin.backend import KWinBackend
from perch.backend.kwin.service import PerchKWin1
from perch.backend.types import Geometry, OutputInfo, WindowState, WindowType


@pytest.fixture(autouse=True)
def _qapp(qapp: object) -> None:
    """QApplication so Qt signals connect."""


@pytest.fixture
def wayland_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make ``_probe_session_env`` see a plausible Plasma Wayland session."""
    monkeypatch.setenv("XDG_SESSION_TYPE", "wayland")
    monkeypatch.setenv("XDG_CURRENT_DESKTOP", "KDE")


# ── env probe ─────────────────────────────────────────────────────────────


async def test_start_refuses_x11_session(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("XDG_SESSION_TYPE", "x11")
    monkeypatch.delenv("XDG_CURRENT_DESKTOP", raising=False)
    b = KWinBackend()
    with pytest.raises(BackendUnavailable):
        await b.start()


async def test_start_refuses_non_kde_wayland(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("XDG_SESSION_TYPE", "wayland")
    monkeypatch.setenv("XDG_CURRENT_DESKTOP", "GNOME")
    b = KWinBackend()
    with pytest.raises(BackendUnavailable):
        await b.start()


# ── start / stop with injected helpers ────────────────────────────────────


@pytest.fixture
def _bus_setup() -> AsyncMock:
    return AsyncMock(return_value=None)


@pytest.fixture
def _scripting() -> MagicMock:
    s = MagicMock()
    s.is_script_loaded = AsyncMock(return_value=False)
    s.unload_script = AsyncMock(return_value=True)
    s.load_script = AsyncMock(return_value=0)
    return s


@pytest.fixture
def _installer(tmp_path: Path) -> Any:
    fake_main = tmp_path / "main.js"
    fake_main.write_text("// fake\n")

    def _install() -> Path:
        return fake_main

    return _install


@pytest.fixture
def _ready_service(
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[list[PerchKWin1]]:
    """Intercept service construction; auto-fire ScriptReady.

    ``KWinBackend.start()`` normally waits up to 5 s for the JS script to
    call ScriptReady; in unit tests we short-circuit by setting the event
    ourselves the instant the service is built.
    """
    created: list[PerchKWin1] = []
    original = PerchKWin1

    def _factory(sink: object) -> PerchKWin1:
        svc = original(cast(Any, sink))
        svc.export = AsyncMock(return_value=None)  # type: ignore[method-assign]
        svc.script_ready.set()
        created.append(svc)
        return svc

    monkeypatch.setattr("perch.backend.kwin.backend.PerchKWin1", _factory)
    yield created


@pytest.fixture
def _mock_run_script(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    m = AsyncMock(return_value=(0, MagicMock()))
    monkeypatch.setattr("perch.backend.kwin.backend.install_and_run_script", m)
    return m


@pytest.fixture
def _mock_unload_script(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    m = AsyncMock(return_value=True)
    monkeypatch.setattr("perch.backend.kwin.backend.unload_script_if_loaded", m)
    return m


async def test_start_emits_backend_connected_and_loads_script(
    wayland_env: None,
    _bus_setup: AsyncMock,
    _scripting: MagicMock,
    _installer: Any,
    _ready_service: list[PerchKWin1],
    _mock_run_script: AsyncMock,
    _mock_unload_script: AsyncMock,
) -> None:
    connected: list[bool] = []
    b = KWinBackend(
        bus_setup=_bus_setup,
        scripting_factory=AsyncMock(return_value=_scripting),
        script_installer=_installer,
    )
    b.backend_connected.connect(lambda: connected.append(True))
    await b.start()
    assert connected == [True]
    _bus_setup.assert_awaited_once()
    _mock_run_script.assert_awaited_once()
    # Defensive unload of a prior-session ghost before our load.
    _mock_unload_script.assert_awaited_once()


async def test_start_raises_backend_unavailable_if_script_never_ready(
    wayland_env: None,
    _bus_setup: AsyncMock,
    _scripting: MagicMock,
    _installer: Any,
    monkeypatch: pytest.MonkeyPatch,
    _mock_run_script: AsyncMock,
    _mock_unload_script: AsyncMock,
) -> None:
    # Don't auto-fire script_ready in this test — leave it un-set, and
    # shrink the timeout to keep the test fast.
    monkeypatch.setattr("perch.backend.kwin.backend.SCRIPT_READY_TIMEOUT_S", 0.05)
    b = KWinBackend(
        bus_setup=_bus_setup,
        scripting_factory=AsyncMock(return_value=_scripting),
        script_installer=_installer,
    )
    with pytest.raises(BackendUnavailable, match="ScriptReady"):
        await b.start()


async def test_start_raises_backend_unavailable_if_bus_setup_fails(
    wayland_env: None,
    _scripting: MagicMock,
    _installer: Any,
) -> None:
    bad_bus = AsyncMock(side_effect=RuntimeError("nobody here"))
    b = KWinBackend(
        bus_setup=bad_bus,
        scripting_factory=AsyncMock(return_value=_scripting),
        script_installer=_installer,
    )
    with pytest.raises(BackendUnavailable, match="could not acquire"):
        await b.start()


async def test_stop_invalidates_polls_before_unloading(
    wayland_env: None,
    _bus_setup: AsyncMock,
    _scripting: MagicMock,
    _installer: Any,
    _ready_service: list[PerchKWin1],
    _mock_run_script: AsyncMock,
    _mock_unload_script: AsyncMock,
) -> None:
    b = KWinBackend(
        bus_setup=_bus_setup,
        scripting_factory=AsyncMock(return_value=_scripting),
        script_installer=_installer,
    )
    await b.start()
    assert len(_ready_service) == 1
    svc = _ready_service[0]
    # A PollCommand in flight at stop time must wake up with the
    # invalidation reply rather than hanging.
    poll_task = asyncio.create_task(svc.PollCommand())
    await asyncio.sleep(0)
    await b.stop()
    reply = await asyncio.wait_for(poll_task, timeout=1.0)
    assert json.loads(reply) == {"nop": True, "reason": "invalidated"}


async def test_stop_on_never_started_backend_is_noop() -> None:
    b = KWinBackend()
    await b.stop()  # must not raise


# ── Enumeration via mock service ──────────────────────────────────────────


@pytest.fixture
def started_backend(
    wayland_env: None,
    _bus_setup: AsyncMock,
    _scripting: MagicMock,
    _installer: Any,
    _ready_service: list[PerchKWin1],
    _mock_run_script: AsyncMock,
    _mock_unload_script: AsyncMock,
    monkeypatch: pytest.MonkeyPatch,
) -> Any:
    # Route choose_provider() through MockHotkeyProvider unless the caller
    # supplies a hotkey_provider explicitly.
    monkeypatch.setenv("PERCH_HOTKEY_PROVIDER", "mock")

    async def _build(**overrides: Any) -> KWinBackend:
        b = KWinBackend(
            bus_setup=_bus_setup,
            scripting_factory=AsyncMock(return_value=_scripting),
            script_installer=_installer,
            **overrides,
        )
        await b.start()
        return b

    return _build


async def test_list_windows_round_trips_and_decodes(started_backend: Any) -> None:
    b = await started_backend()
    assert b._service is not None
    b._service.execute = AsyncMock(
        return_value={
            "ok": True,
            "windows": [
                {
                    "id": "w-1",
                    "app_id": "firefox",
                    "title": "tab",
                    "type": "normal",
                    "state": "normal",
                    "x": 0,
                    "y": 0,
                    "w": 1920,
                    "h": 1080,
                    "output": "HDMI-A-1",
                    "desktop": 0,
                },
                {
                    "id": "w-2",
                    "app_id": "kitty",
                    "title": "prompt",
                    "type": "normal",
                    "state": "normal",
                    "x": 100,
                    "y": 200,
                    "w": 800,
                    "h": 600,
                    "output": "HDMI-A-1",
                    "desktop": 0,
                },
            ],
        }
    )
    wins = await b.list_windows()
    assert [w.app_id for w in wins] == ["firefox", "kitty"]
    # Cached for get_window fast path.
    assert b._windows["w-1"].id == "w-1"


async def test_list_windows_drops_malformed_entries(started_backend: Any) -> None:
    b = await started_backend()
    assert b._service is not None
    b._service.execute = AsyncMock(
        return_value={
            "ok": True,
            "windows": [
                {"id": "w-1", "app_id": "ok"},
                "not-a-dict",
                {"no-id": "broken"},  # KeyError on decode_window_info
            ],
        }
    )
    wins = await b.list_windows()
    assert [w.id for w in wins] == ["w-1"]


async def test_get_window_raises_unknown_window_on_missing_id(
    started_backend: Any,
) -> None:
    b = await started_backend()
    assert b._service is not None
    b._service.execute = AsyncMock(
        return_value={"ok": False, "error": "unknown_window", "id": "nope"}
    )
    with pytest.raises(UnknownWindow):
        await b.get_window("nope")


async def test_list_outputs_marks_first_as_primary(started_backend: Any) -> None:
    b = await started_backend()
    assert b._service is not None
    b._service.execute = AsyncMock(
        return_value={
            "ok": True,
            "outputs": [
                {
                    "name": "HDMI-A-1",
                    "x": 0,
                    "y": 0,
                    "w": 1920,
                    "h": 1080,
                    "scale": 1.0,
                    "refresh_mhz": 60000,
                },
                {
                    "name": "DP-1",
                    "x": 1920,
                    "y": 0,
                    "w": 2560,
                    "h": 1440,
                    "scale": 1.25,
                    "refresh_mhz": 144000,
                },
            ],
        }
    )
    outs = await b.list_outputs()
    assert len(outs) == 2
    assert outs[0].name == "HDMI-A-1" and outs[0].is_primary is True
    assert outs[1].name == "DP-1" and outs[1].is_primary is False
    assert outs[0].work_area == outs[0].geometry  # no strut info from KWin
    assert outs[0].is_connected is True


async def test_current_desktop_and_count(started_backend: Any) -> None:
    b = await started_backend()
    assert b._service is not None
    b._service.execute = AsyncMock()
    b._service.execute.side_effect = [
        {"ok": True, "desktop": 2},
        {"ok": True, "count": 4},
    ]
    assert await b.current_desktop() == 2
    assert await b.desktop_count() == 4


async def test_hotkey_register_round_trips_via_mock_provider(
    started_backend: Any,
) -> None:
    from perch.backend.kwin.hotkeys import MockHotkeyProvider

    provider = MockHotkeyProvider()
    b = await started_backend(hotkey_provider=provider)
    await b.register_hotkey("Ctrl+Alt+F12", "cb-1")
    assert "cb-1" in provider.bindings

    fired: list[str] = []
    b.hotkey_fired.connect(lambda cid: fired.append(cid))
    provider.fire("cb-1")
    assert fired == ["cb-1"]

    await b.unregister_hotkey("cb-1")
    assert "cb-1" not in provider.bindings


async def test_hotkey_busy_raises_and_emits_backend_error(
    started_backend: Any,
) -> None:
    from perch.backend.kwin.hotkeys import HotkeyBusyError, MockHotkeyProvider

    provider = MockHotkeyProvider(busy={"Ctrl+Alt+F12"})
    b = await started_backend(hotkey_provider=provider)

    errs: list[str] = []
    b.backend_error.connect(lambda msg: errs.append(msg))
    with pytest.raises(HotkeyBusyError):
        await b.register_hotkey("Ctrl+Alt+F12", "cb-1")
    assert errs, "HotkeyBusyError should have emitted a backend_error signal"
    assert "already grabbed" in errs[0]


async def test_hotkey_parse_error_raises_and_emits_backend_error(
    started_backend: Any,
) -> None:
    from perch.backend.kwin.hotkeys import HotkeyParseError, MockHotkeyProvider

    b = await started_backend(hotkey_provider=MockHotkeyProvider())
    errs: list[str] = []
    b.backend_error.connect(lambda msg: errs.append(msg))
    with pytest.raises(HotkeyParseError):
        await b.register_hotkey("NotAModifier+Q", "cb-1")
    assert errs


# ── Commands (M5.e) ────────────────────────────────────────────────────────


async def test_set_geometry_sends_single_op_when_monitor_and_desktop_none(
    started_backend: Any,
) -> None:
    b = await started_backend()
    assert b._service is not None
    b._service.execute = AsyncMock(return_value={"ok": True})
    await b.set_geometry("w-1", Geometry(10, 20, 300, 400))
    sent = b._service.execute.await_args.args[0]
    assert sent["op"] == "setFrameGeometry"
    assert sent["id"] == "w-1"
    assert sent["x"] == 10 and sent["w"] == 300
    assert sent["preplace"] is True
    assert "output" not in sent


async def test_set_geometry_batches_when_desktop_specified(started_backend: Any) -> None:
    b = await started_backend()
    assert b._service is not None
    b._service.execute = AsyncMock(return_value={"ok": True})
    await b.set_geometry("w-1", Geometry(0, 0, 100, 100), desktop=2)
    sent = b._service.execute.await_args.args[0]
    assert "batch" in sent
    assert sent["batch"][0]["op"] == "setDesktop"
    assert sent["batch"][0]["desktop"] == 2
    assert sent["batch"][1]["op"] == "setFrameGeometry"


async def test_set_geometry_raises_unknown_output_for_unknown_monitor(
    started_backend: Any,
) -> None:
    b = await started_backend()
    assert b._service is not None
    # list_outputs() returns nothing, so the cache stays empty and the
    # explicit monitor doesn't match.
    b._service.execute = AsyncMock(return_value={"ok": True, "outputs": []})
    with pytest.raises(UnknownOutput):
        await b.set_geometry("w-1", Geometry(0, 0, 100, 100), monitor="NONE")


async def test_set_geometry_includes_monitor_when_cached(started_backend: Any) -> None:
    b = await started_backend()
    # Seed the output cache.
    b._outputs["HDMI-A-1"] = OutputInfo(
        name="HDMI-A-1",
        geometry=Geometry(0, 0, 1920, 1080),
        work_area=Geometry(0, 0, 1920, 1080),
        scale=1.0,
        refresh_mhz=60000,
        is_primary=True,
        is_connected=True,
    )
    assert b._service is not None
    b._service.execute = AsyncMock(return_value={"ok": True})
    await b.set_geometry("w-1", Geometry(0, 0, 100, 100), monitor="HDMI-A-1")
    sent = b._service.execute.await_args.args[0]
    assert sent["output"] == "HDMI-A-1"


async def test_set_geometry_unknown_window_translates(started_backend: Any) -> None:
    b = await started_backend()
    assert b._service is not None
    b._service.execute = AsyncMock(
        return_value={"ok": False, "error": "unknown_window", "id": "w-1"}
    )
    with pytest.raises(UnknownWindow):
        await b.set_geometry("w-1", Geometry(0, 0, 100, 100))


async def test_set_state_fullscreen_uses_batch(started_backend: Any) -> None:
    b = await started_backend()
    assert b._service is not None
    b._service.execute = AsyncMock(return_value={"ok": True})
    await b.set_state("w-1", WindowState.FULLSCREEN)
    sent = b._service.execute.await_args.args[0]
    assert "batch" in sent
    ops = [sub["op"] for sub in sent["batch"]]
    assert ops == ["setMinimized", "setFullScreen"]
    assert sent["batch"][1]["value"] is True


async def test_set_state_maximized_clears_fullscreen_and_minimized(
    started_backend: Any,
) -> None:
    b = await started_backend()
    assert b._service is not None
    b._service.execute = AsyncMock(return_value={"ok": True})
    await b.set_state("w-1", WindowState.MAXIMIZED)
    sent = b._service.execute.await_args.args[0]
    ops = [sub["op"] for sub in sent["batch"]]
    assert ops == ["setMinimized", "setFullScreen", "setMaximizeMode"]
    last = sent["batch"][-1]
    assert last["vertical"] is True and last["horizontal"] is True


async def test_set_state_minimized_is_single_op(started_backend: Any) -> None:
    b = await started_backend()
    assert b._service is not None
    b._service.execute = AsyncMock(return_value={"ok": True})
    await b.set_state("w-1", WindowState.MINIMIZED)
    sent = b._service.execute.await_args.args[0]
    assert sent["op"] == "setMinimized"
    assert sent["value"] is True


async def test_set_state_normal_clears_everything(started_backend: Any) -> None:
    b = await started_backend()
    assert b._service is not None
    b._service.execute = AsyncMock(return_value={"ok": True})
    await b.set_state("w-1", WindowState.NORMAL)
    sent = b._service.execute.await_args.args[0]
    ops = [sub["op"] for sub in sent["batch"]]
    assert ops == ["setFullScreen", "setMinimized", "setMaximizeMode"]
    last = sent["batch"][-1]
    assert last["vertical"] is False and last["horizontal"] is False


async def test_set_state_unknown_window_translates(started_backend: Any) -> None:
    b = await started_backend()
    assert b._service is not None
    b._service.execute = AsyncMock(
        return_value={"ok": False, "error": "unknown_window", "id": "w-1"}
    )
    with pytest.raises(UnknownWindow):
        await b.set_state("w-1", WindowState.FULLSCREEN)


async def test_close_window_dispatches_close_op(started_backend: Any) -> None:
    b = await started_backend()
    assert b._service is not None
    b._service.execute = AsyncMock(return_value={"ok": True})
    await b.close_window("w-1")
    sent = b._service.execute.await_args.args[0]
    assert sent == {"op": "closeWindow", "id": "w-1"}


async def test_close_window_unknown_translates(started_backend: Any) -> None:
    b = await started_backend()
    assert b._service is not None
    b._service.execute = AsyncMock(
        return_value={"ok": False, "error": "unknown_window", "id": "w-1"}
    )
    with pytest.raises(UnknownWindow):
        await b.close_window("w-1")


async def test_queries_require_connection() -> None:
    b = KWinBackend()
    with pytest.raises(BackendDisconnected):
        await b.list_windows()
    with pytest.raises(BackendDisconnected):
        await b.get_window("x")
    with pytest.raises(BackendDisconnected):
        await b.list_outputs()
    with pytest.raises(BackendDisconnected):
        await b.current_desktop()
    with pytest.raises(BackendDisconnected):
        await b.desktop_count()


# ── Event routing ─────────────────────────────────────────────────────────


def _drive_events() -> KWinBackend:
    """Backend without start(); we exercise only the EventSink surface."""
    return KWinBackend()


def test_on_window_added_emits_window_opened_and_geometry() -> None:
    b = _drive_events()
    opened: list[str] = []
    geom: list[str] = []
    b.window_opened.connect(lambda info: opened.append(info.id))
    b.geometry_changed.connect(lambda wid, _g, _m, _d: geom.append(wid))
    b.on_window_added(
        {
            "id": "w-1",
            "app_id": "firefox",
            "title": "",
            "type": "normal",
            "state": "normal",
            "x": 10,
            "y": 20,
            "w": 300,
            "h": 400,
            "output": "HDMI-A-1",
            "desktop": 0,
        }
    )
    assert opened == ["w-1"]
    assert geom == ["w-1"]
    QCoreApplication.processEvents()


def test_on_window_removed_emits_window_closed() -> None:
    b = _drive_events()
    closed: list[str] = []
    b.window_closed.connect(lambda wid: closed.append(wid))
    b.on_window_removed({"id": "w-gone"})
    assert closed == ["w-gone"]


def test_on_window_removed_ignores_missing_id() -> None:
    b = _drive_events()
    closed: list[str] = []
    b.window_closed.connect(lambda wid: closed.append(wid))
    b.on_window_removed({"not-id": "…"})
    assert closed == []


def test_on_window_geometry_changed_skips_no_op_updates() -> None:
    b = _drive_events()
    geom: list[str] = []
    b.geometry_changed.connect(lambda wid, _g, _m, _d: geom.append(wid))
    p = {
        "id": "w-1",
        "x": 0,
        "y": 0,
        "w": 100,
        "h": 100,
        "output": "HDMI-A-1",
        "desktop": 0,
        "type": "normal",
        "state": "normal",
    }
    b.on_window_geometry_changed(p)
    b.on_window_geometry_changed(p)  # identical geometry — no second signal
    assert geom == ["w-1"]


def test_on_window_properties_changed_emits_window_changed() -> None:
    b = _drive_events()
    changed: list[WindowType] = []
    b.window_changed.connect(lambda info: changed.append(info.type))
    b.on_window_properties_changed(
        {
            "id": "w-1",
            "type": "dialog",
            "state": "normal",
            "x": 0,
            "y": 0,
            "w": 100,
            "h": 100,
            "output": "",
            "desktop": 0,
        }
    )
    assert changed == [WindowType.DIALOG]


async def test_on_outputs_changed_reconciles_added_changed_removed(
    wayland_env: None,
    _bus_setup: AsyncMock,
    _scripting: MagicMock,
    _installer: Any,
    _ready_service: list[PerchKWin1],
    _mock_run_script: AsyncMock,
    _mock_unload_script: AsyncMock,
) -> None:
    added: list[OutputInfo] = []
    changed: list[OutputInfo] = []
    removed: list[str] = []
    b = KWinBackend(
        bus_setup=_bus_setup,
        scripting_factory=AsyncMock(return_value=_scripting),
        script_installer=_installer,
    )
    b.output_added.connect(lambda info: added.append(info))
    b.output_changed.connect(lambda info: changed.append(info))
    b.output_removed.connect(lambda name: removed.append(name))
    await b.start()

    assert b._service is not None
    # Seed: 2 outputs on first query.
    b._service.execute = AsyncMock()  # type: ignore[method-assign]
    b._service.execute.side_effect = [
        {
            "ok": True,
            "outputs": [
                {
                    "name": "A",
                    "x": 0,
                    "y": 0,
                    "w": 100,
                    "h": 100,
                    "scale": 1.0,
                    "refresh_mhz": 60000,
                },
                {
                    "name": "B",
                    "x": 100,
                    "y": 0,
                    "w": 100,
                    "h": 100,
                    "scale": 1.0,
                    "refresh_mhz": 60000,
                },
            ],
        },
        # After OutputsChanged: A moved, B gone, C new.
        {
            "ok": True,
            "outputs": [
                {
                    "name": "A",
                    "x": 0,
                    "y": 0,
                    "w": 200,
                    "h": 200,
                    "scale": 1.0,
                    "refresh_mhz": 60000,
                },
                {
                    "name": "C",
                    "x": 200,
                    "y": 0,
                    "w": 100,
                    "h": 100,
                    "scale": 1.0,
                    "refresh_mhz": 60000,
                },
            ],
        },
    ]
    await b.list_outputs()  # seed the cache

    b.on_outputs_changed()
    # Background task; drain it.
    pending = [t for t in b._bg_tasks]
    for t in pending:
        await t

    assert [o.name for o in added] == ["C"]
    assert [o.name for o in changed] == ["A"]
    assert removed == ["B"]


def test_on_script_ready_only_logs() -> None:
    """ScriptReady sets the service event; backend side only logs."""
    b = _drive_events()
    b.on_script_ready({"version": "1.0.0"})  # must not raise


def test_malformed_window_payloads_do_not_raise() -> None:
    b = _drive_events()
    # Missing 'id' key → decode_window_info raises KeyError → we swallow.
    b.on_window_added({"no-id": "…"})
    b.on_window_geometry_changed({"no-id": "…"})
    b.on_window_properties_changed({"no-id": "…"})


# ── Capabilities ──────────────────────────────────────────────────────────


def test_capabilities_match_doc() -> None:
    b = KWinBackend()
    caps = b.capabilities
    assert caps.can_set_position is True
    assert caps.can_preplace_windows is True
    assert caps.can_register_hotkeys is True
    assert "Plasma" in caps.notes
    assert "KGlobalAccel" in caps.notes
