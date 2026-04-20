"""Tests for :class:`MockBackend`'s test-driver API.

The compliance suite already exercises the ``WindowBackend`` contract. This
file verifies the *driver* surface (``_spawn_window``, ``_move_window``,
output lifecycle, command log, capability flips) that the rules-engine tests
and the reducer tests in M2.c-M2.d will rely on.
"""

from __future__ import annotations

from dataclasses import replace

import pytest

from perch.backend import (
    BackendUnsupported,
    Capabilities,
    Geometry,
    OutputInfo,
    WindowInfo,
    WindowState,
    WindowType,
)
from perch.backend.mock import MockBackend


@pytest.fixture(autouse=True)
def _require_qapp(qapp: object) -> None: ...


async def _connected_mock() -> MockBackend:
    b = MockBackend()
    await b.start()
    return b


def _window(wid: str = "w1") -> WindowInfo:
    return WindowInfo(
        id=wid,
        app_id="code",
        wm_class="code",
        title="VSCode",
        pid=42,
        type=WindowType.NORMAL,
        state=WindowState.NORMAL,
        geometry=Geometry(0, 0, 800, 600),
        monitor="DP-1",
        desktop=0,
    )


def _output(name: str = "DP-1") -> OutputInfo:
    return OutputInfo(
        name=name,
        geometry=Geometry(0, 0, 1920, 1080),
        work_area=Geometry(0, 0, 1920, 1040),
        scale=1.0,
        refresh_mhz=60000,
        is_primary=True,
        is_connected=True,
    )


async def test_spawn_emits_window_opened() -> None:
    b = await _connected_mock()
    received: list[WindowInfo] = []
    b.window_opened.connect(received.append)

    b._spawn_window(_window())

    assert len(received) == 1
    assert received[0].id == "w1"


async def test_double_spawn_raises() -> None:
    b = await _connected_mock()
    b._spawn_window(_window())
    with pytest.raises(ValueError, match="already present"):
        b._spawn_window(_window())


async def test_change_window_emits_window_changed() -> None:
    b = await _connected_mock()
    b._spawn_window(_window())
    received: list[WindowInfo] = []
    b.window_changed.connect(received.append)

    w = _window()
    b._change_window(replace(w, title="Renamed"))

    assert received[-1].title == "Renamed"


async def test_move_window_emits_geometry_changed_without_recording() -> None:
    """``_move_window`` models a user drag and must not enter the command log."""
    b = await _connected_mock()
    b._spawn_window(_window())
    events: list[tuple[str, Geometry, str, int]] = []
    b.geometry_changed.connect(
        lambda wid, g, m, d: events.append((wid, g, m, d))
    )

    b._move_window("w1", Geometry(50, 50, 800, 600))

    assert events[-1][0] == "w1"
    assert events[-1][1] == Geometry(50, 50, 800, 600)
    assert b.commands.names() == []  # user drags aren't Perch commands


async def test_set_geometry_records_and_emits() -> None:
    b = await _connected_mock()
    b._spawn_window(_window())
    b._add_output(_output("DP-1"))
    b._add_output(_output("HDMI-1"))
    events: list[tuple[str, Geometry, str, int]] = []
    b.geometry_changed.connect(
        lambda wid, g, m, d: events.append((wid, g, m, d))
    )

    await b.set_geometry(
        "w1", Geometry(10, 10, 400, 300), monitor="HDMI-1", desktop=2
    )

    assert b.commands.entries == [
        ("set_geometry", ("w1", Geometry(10, 10, 400, 300), "HDMI-1", 2)),
    ]
    assert events[-1] == ("w1", Geometry(10, 10, 400, 300), "HDMI-1", 2)


async def test_outputs_lifecycle_emits_events() -> None:
    b = await _connected_mock()
    added: list[OutputInfo] = []
    changed: list[OutputInfo] = []
    removed: list[str] = []
    b.output_added.connect(added.append)
    b.output_changed.connect(changed.append)
    b.output_removed.connect(removed.append)

    b._add_output(_output("DP-1"))
    b._change_output(replace(_output("DP-1"), is_primary=False))
    b._remove_output("DP-1")

    assert [o.name for o in added] == ["DP-1"]
    assert changed[0].is_primary is False
    assert removed == ["DP-1"]


async def test_hotkey_register_fire_unregister() -> None:
    b = await _connected_mock()
    fired: list[str] = []
    b.hotkey_fired.connect(fired.append)

    await b.register_hotkey("Meta+C", "snap.center-60")
    assert b.hotkeys == {"snap.center-60": "Meta+C"}

    b._fire_hotkey("snap.center-60")
    assert fired == ["snap.center-60"]

    await b.unregister_hotkey("snap.center-60")
    assert b.hotkeys == {}


async def test_flip_capabilities_degrades_set_state() -> None:
    b = await _connected_mock()
    b._spawn_window(_window())
    caps = b.capabilities
    b.set_capabilities(replace(caps, can_set_state=False))

    with pytest.raises(BackendUnsupported):
        await b.set_state("w1", WindowState.MINIMIZED)


async def test_fail_state_only_affects_targeted_state() -> None:
    b = await _connected_mock()
    b._spawn_window(_window())

    b._fail_state(WindowState.MAXIMIZED)
    with pytest.raises(BackendUnsupported):
        await b.set_state("w1", WindowState.MAXIMIZED)

    # Other states still succeed.
    await b.set_state("w1", WindowState.MINIMIZED)
    w = await b.get_window("w1")
    assert w.state is WindowState.MINIMIZED

    b._clear_fail_state(WindowState.MAXIMIZED)
    await b.set_state("w1", WindowState.MAXIMIZED)  # no longer raises


async def test_default_capabilities_are_all_true() -> None:
    b = MockBackend()
    expected = Capabilities(
        can_set_position=True,
        can_set_size=True,
        can_set_monitor=True,
        can_set_desktop=True,
        can_set_state=True,
        can_enumerate_windows=True,
        can_observe_geometry=True,
        can_observe_outputs=True,
        can_register_hotkeys=True,
        can_preplace_windows=True,
        notes=b.capabilities.notes,  # opaque to the user
    )
    assert b.capabilities == expected
