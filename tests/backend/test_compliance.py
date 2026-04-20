"""Backend compliance suite.

Runs against every backend in :data:`BACKEND_CLASSES` (see ``conftest.py``).
Each test either exercises a guaranteed behaviour or skips itself when the
backend declares the relevant capability off — see
``docs/03-backend-interface.md`` §Capability negotiation and
``docs/06-backend-stubs.md`` §Minimum backend acceptance test.
"""

from __future__ import annotations

import pytest

from perch.backend import (
    BackendUnsupported,
    Geometry,
    OutputInfo,
    UnknownOutput,
    UnknownWindow,
    WindowBackend,
    WindowInfo,
    WindowState,
    WindowType,
)
from perch.backend.mock import MockBackend


def _sample_window(wid: str = "w1", monitor: str = "DP-1") -> WindowInfo:
    return WindowInfo(
        id=wid,
        app_id="firefox",
        wm_class="firefox",
        title="Mozilla Firefox",
        pid=1234,
        type=WindowType.NORMAL,
        state=WindowState.NORMAL,
        geometry=Geometry(100, 100, 800, 600),
        monitor=monitor,
        desktop=0,
    )


# ── 1. start() / stop() lifecycle ──────────────────────────────────────────
async def test_start_stop_lifecycle(backend_cls: type[WindowBackend]) -> None:
    b = backend_cls()
    connected: list[bool] = []
    disconnected: list[str] = []
    b.backend_connected.connect(lambda: connected.append(True))
    b.backend_disconnected.connect(lambda reason: disconnected.append(reason))

    await b.start()
    assert connected == [True]

    await b.stop()
    assert len(disconnected) == 1


# ── 2. list_windows() shape validation ─────────────────────────────────────
async def test_list_windows_returns_frozen_dataclasses(
    backend: WindowBackend,
) -> None:
    if isinstance(backend, MockBackend):
        backend._spawn_window(_sample_window())

    windows = await backend.list_windows()
    assert isinstance(windows, list)
    for w in windows:
        assert isinstance(w, WindowInfo)
        assert isinstance(w.geometry, Geometry)
        assert isinstance(w.type, WindowType)
        assert isinstance(w.state, WindowState)


# ── 3. list_outputs() shape validation ─────────────────────────────────────
async def test_list_outputs_returns_frozen_dataclasses(
    backend: WindowBackend,
) -> None:
    outputs = await backend.list_outputs()
    assert isinstance(outputs, list)
    assert len(outputs) >= 1
    for o in outputs:
        assert isinstance(o, OutputInfo)
        assert isinstance(o.geometry, Geometry)
        assert isinstance(o.work_area, Geometry)
        assert o.is_connected is True


# ── 4. Announced capabilities match actual behaviour ───────────────────────
async def test_set_position_matches_capability(backend: WindowBackend) -> None:
    if not backend.capabilities.can_set_position:
        pytest.skip("backend does not claim can_set_position")
    if isinstance(backend, MockBackend):
        backend._spawn_window(_sample_window())

    await backend.set_geometry("w1", Geometry(200, 300, 800, 600))
    w = await backend.get_window("w1")
    assert (w.geometry.x, w.geometry.y) == (200, 300)


async def test_set_state_matches_capability(backend: WindowBackend) -> None:
    if not backend.capabilities.can_set_state:
        pytest.skip("backend does not claim can_set_state")
    if isinstance(backend, MockBackend):
        backend._spawn_window(_sample_window())

    await backend.set_state("w1", WindowState.MINIMIZED)
    w = await backend.get_window("w1")
    assert w.state is WindowState.MINIMIZED


async def test_set_monitor_matches_capability(backend: WindowBackend) -> None:
    if not backend.capabilities.can_set_monitor:
        pytest.skip("backend does not claim can_set_monitor")
    if isinstance(backend, MockBackend):
        backend._spawn_window(_sample_window())

    await backend.set_geometry(
        "w1", Geometry(0, 0, 800, 600), monitor="HDMI-1"
    )
    w = await backend.get_window("w1")
    assert w.monitor == "HDMI-1"


# ── 5. Event ordering guarantees ───────────────────────────────────────────
async def test_window_opened_precedes_geometry_changed(
    backend: WindowBackend,
) -> None:
    if not isinstance(backend, MockBackend):
        pytest.skip("event-ordering driver is mock-specific")
    order: list[str] = []
    backend.window_opened.connect(lambda _info: order.append("opened"))
    backend.geometry_changed.connect(
        lambda _wid, _g, _m, _d: order.append("geometry_changed")
    )

    backend._spawn_window(_sample_window())
    await backend.set_geometry("w1", Geometry(10, 10, 100, 100))

    assert order[0] == "opened"
    assert "geometry_changed" in order[1:]


async def test_window_closed_is_terminal(backend: WindowBackend) -> None:
    if not isinstance(backend, MockBackend):
        pytest.skip("terminal-close driver is mock-specific")
    events: list[str] = []
    backend.window_closed.connect(lambda _wid: events.append("closed"))
    backend.geometry_changed.connect(
        lambda _wid, _g, _m, _d: events.append("geometry_changed")
    )
    backend.window_changed.connect(lambda _info: events.append("changed"))

    backend._spawn_window(_sample_window())
    await backend.close_window("w1")

    assert "closed" in events
    closed_at = events.index("closed")
    assert all(e not in events[closed_at + 1 :] for e in ("geometry_changed", "changed"))

    with pytest.raises(UnknownWindow):
        await backend.get_window("w1")


# ── 6. Error taxonomy ──────────────────────────────────────────────────────
async def test_unknown_window_raises(backend: WindowBackend) -> None:
    with pytest.raises(UnknownWindow):
        await backend.get_window("does-not-exist")


async def test_unknown_output_raises(backend: WindowBackend) -> None:
    if not backend.capabilities.can_set_monitor:
        pytest.skip("no can_set_monitor → no UnknownOutput path")
    if isinstance(backend, MockBackend):
        backend._spawn_window(_sample_window())
    with pytest.raises(UnknownOutput):
        await backend.set_geometry(
            "w1", Geometry(0, 0, 100, 100), monitor="NONEXISTENT-99"
        )


async def test_unsupported_capability_raises(backend: WindowBackend) -> None:
    """Dropping ``can_set_desktop`` must surface as ``BackendUnsupported``."""
    if not isinstance(backend, MockBackend):
        pytest.skip("capability-flip driver is mock-specific")
    backend._spawn_window(_sample_window())
    caps = backend.capabilities
    from dataclasses import replace

    backend.set_capabilities(replace(caps, can_set_desktop=False))
    with pytest.raises(BackendUnsupported):
        await backend.set_geometry(
            "w1", Geometry(0, 0, 100, 100), desktop=1
        )


# ── Additional coverage: MAXIMIZED fallback contract ───────────────────────
async def test_set_state_maximized_may_raise_unsupported(
    backend: WindowBackend,
) -> None:
    """Mirrors the Sway/Hyprland compromise documented in docs/06.

    A backend declaring ``can_set_state = True`` is still allowed to refuse
    ``MAXIMIZED`` specifically by raising :class:`BackendUnsupported`. The
    rules engine's apply pipeline will substitute work-area geometry.
    """
    if not isinstance(backend, MockBackend):
        pytest.skip("fail-state injection is mock-specific")
    backend._spawn_window(_sample_window())
    backend._fail_state(WindowState.MAXIMIZED)
    with pytest.raises(BackendUnsupported):
        await backend.set_state("w1", WindowState.MAXIMIZED)
