"""Live integration tests: :class:`X11Backend` against Xvfb + openbox.

These tests require system ``Xvfb`` and ``openbox``. They skip
automatically when either is missing — see ``conftest.py``.

We exercise the moving parts that unit tests can't cover: the real XRandR
pipeline, the live ``_NET_CLIENT_LIST`` reconciliation driven by
``QSocketNotifier``, the end-to-end ``_NET_MOVERESIZE_WINDOW`` round-trip,
and the ``XGrabKey`` conflict detection that depends on two displays.

Tests marked with ``@pytest.mark.x11`` and CI can gate them with
``pytest -m x11`` or ``pytest -m 'not x11'``.
"""

from __future__ import annotations

import asyncio
import shutil
import subprocess
import time
from typing import TYPE_CHECKING

import pytest
from PySide6.QtCore import QCoreApplication

from perch.backend.types import Geometry, WindowState
from perch.backend.x11 import X11Backend
from perch.backend.x11.hotkeys import (
    HotkeyBusyError,
    ParsedHotkey,
    grab_hotkey,
)

if TYPE_CHECKING:
    from PySide6.QtWidgets import QWidget

    _QtBotProto = QWidget  # mypy-friendly alias for the qtbot protocol.
    del _QtBotProto

pytestmark = pytest.mark.x11


@pytest.fixture(autouse=True)
def _qapp(qapp: object) -> None:
    """Ensure a QApplication so QSocketNotifier + signals work."""


# Helper: pump Qt + asyncio events for ``duration_s`` or until ``cond()``.
async def _pump_until(cond: object, duration_s: float = 1.5) -> None:
    t0 = time.time()
    while time.time() - t0 < duration_s:
        QCoreApplication.processEvents()
        await asyncio.sleep(0.05)
        if callable(cond) and cond():
            return


def _have(name: str) -> bool:
    return shutil.which(name) is not None


# ── Happy path: start + list_outputs + current_desktop ─────────────────────


def test_start_emits_backend_connected_and_lists_virtual_output(
    openbox_display: str,
) -> None:
    async def run() -> None:
        b = X11Backend(display_name=openbox_display)
        connected: list[bool] = []
        b.backend_connected.connect(lambda: connected.append(True))

        await b.start()
        assert connected == [True]

        outs = await b.list_outputs()
        # Xvfb publishes a single synthetic output named "screen".
        assert len(outs) == 1
        assert outs[0].geometry.w == 1920
        assert outs[0].geometry.h == 1080
        assert outs[0].is_connected is True

        # Openbox defaults to 4 desktops.
        assert await b.desktop_count() == 4
        assert await b.current_desktop() == 0

        await b.stop()

    asyncio.run(run())


# ── Live window enumeration + geometry round-trip ──────────────────────────


@pytest.mark.skipif(not _have("xclock"), reason="xclock is required for this test")
def test_window_opened_fires_on_xclock_spawn_and_geometry_round_trip(
    openbox_display: str,
) -> None:
    async def run() -> None:
        b = X11Backend(display_name=openbox_display)
        opened: list[str] = []
        closed: list[str] = []
        b.window_opened.connect(lambda info: opened.append(info.app_id))
        b.window_closed.connect(lambda wid: closed.append(wid))
        await b.start()

        env = {"DISPLAY": openbox_display, "PATH": "/usr/bin:/bin"}
        xc = subprocess.Popen(
            ["xclock", "-geometry", "100x100+500+300"], env=env
        )
        try:
            await _pump_until(lambda: bool(opened), duration_s=3.0)
            assert opened == ["xclock"]

            wins = await b.list_windows()
            assert any(w.app_id == "xclock" for w in wins)
            wid = next(w.id for w in wins if w.app_id == "xclock")

            # Round-trip set_geometry. Openbox may offset by its 1 px border;
            # we assert within a 5 px tolerance rather than exact equality.
            await b.set_geometry(wid, Geometry(300, 200, 400, 300))
            await _pump_until(lambda: False, duration_s=0.5)
            info = await b.get_window(wid)
            assert abs(info.geometry.x - 300) <= 5
            assert abs(info.geometry.y - 200) <= 5
            assert info.geometry.w == 400
            assert info.geometry.h == 300
        finally:
            try:
                xc.terminate()
                xc.wait(timeout=2.0)
            except subprocess.TimeoutExpired:
                xc.kill()
                xc.wait()

        # window_closed should fire once xclock exits and Openbox removes
        # the entry from _NET_CLIENT_LIST.
        await _pump_until(lambda: bool(closed), duration_s=3.0)
        assert closed, "window_closed never fired for xclock"

        await b.stop()

    asyncio.run(run())


# ── set_state live: fullscreen / normal cycle ──────────────────────────────


@pytest.mark.skipif(not _have("xclock"), reason="xclock is required for this test")
def test_set_state_toggles_fullscreen_and_back(openbox_display: str) -> None:
    async def run() -> None:
        b = X11Backend(display_name=openbox_display)
        await b.start()

        env = {"DISPLAY": openbox_display, "PATH": "/usr/bin:/bin"}
        xc = subprocess.Popen(["xclock"], env=env)
        try:
            opened_ids: list[str] = []
            b.window_opened.connect(lambda info: opened_ids.append(info.id))
            await _pump_until(lambda: bool(opened_ids), duration_s=3.0)
            wid = opened_ids[0]

            await b.set_state(wid, WindowState.FULLSCREEN)
            await _pump_until(lambda: False, duration_s=0.5)
            info = await b.get_window(wid)
            assert info.state is WindowState.FULLSCREEN

            await b.set_state(wid, WindowState.NORMAL)
            await _pump_until(lambda: False, duration_s=0.5)
            info = await b.get_window(wid)
            assert info.state is WindowState.NORMAL
        finally:
            try:
                xc.terminate()
                xc.wait(timeout=2.0)
            except subprocess.TimeoutExpired:
                xc.kill()
                xc.wait()

        await b.stop()

    asyncio.run(run())


# ── close_window live: WM_DELETE_WINDOW path ───────────────────────────────


@pytest.mark.skipif(not _have("xclock"), reason="xclock is required for this test")
def test_close_window_causes_window_closed_signal(openbox_display: str) -> None:
    async def run() -> None:
        b = X11Backend(display_name=openbox_display)
        closed: list[str] = []
        b.window_closed.connect(lambda wid: closed.append(wid))
        await b.start()

        env = {"DISPLAY": openbox_display, "PATH": "/usr/bin:/bin"}
        xc = subprocess.Popen(["xclock"], env=env)
        try:
            opened_ids: list[str] = []
            b.window_opened.connect(lambda info: opened_ids.append(info.id))
            await _pump_until(lambda: bool(opened_ids), duration_s=3.0)
            wid = opened_ids[0]

            await b.close_window(wid)
            await _pump_until(lambda: bool(closed), duration_s=3.0)
            assert wid in closed
        finally:
            # If close_window succeeded, xc has exited; .wait is instant.
            try:
                xc.wait(timeout=2.0)
            except subprocess.TimeoutExpired:
                xc.kill()
                xc.wait()

        await b.stop()

    asyncio.run(run())


# ── Hotkey grab / conflict / release ───────────────────────────────────────


def test_register_hotkey_claims_the_grab(openbox_display: str) -> None:
    """A second Display attempting the same grab raises HotkeyBusyError."""
    from Xlib import X as _X
    from Xlib import display as _display

    async def run() -> None:
        b = X11Backend(display_name=openbox_display)
        await b.start()
        await b.register_hotkey("Ctrl+Alt+F12", "cb-test")

        d2 = _display.Display(openbox_display)
        try:
            parsed = ParsedHotkey(
                modifiers=_X.ControlMask | _X.Mod1Mask,
                keysym_name="F12",
            )
            with pytest.raises(HotkeyBusyError):
                grab_hotkey(d2, parsed, 0)
        finally:
            d2.close()

        await b.unregister_hotkey("cb-test")

        # After unregister, the same grab must succeed from the second display.
        d3 = _display.Display(openbox_display)
        try:
            parsed = ParsedHotkey(
                modifiers=_X.ControlMask | _X.Mod1Mask,
                keysym_name="F12",
            )
            keycode = grab_hotkey(d3, parsed, 0)
            assert keycode > 0
        finally:
            d3.close()

        await b.stop()

    asyncio.run(run())


# ── Backend error taxonomy (live) ──────────────────────────────────────────


def test_unknown_window_raises_for_live_backend(openbox_display: str) -> None:
    from perch.backend.base import UnknownWindow

    async def run() -> None:
        b = X11Backend(display_name=openbox_display)
        await b.start()
        with pytest.raises(UnknownWindow):
            await b.get_window("nonsense")
        await b.stop()

    asyncio.run(run())


def test_set_geometry_with_bogus_monitor_raises_unknown_output(
    openbox_display: str,
) -> None:
    from perch.backend.base import UnknownOutput

    async def run() -> None:
        b = X11Backend(display_name=openbox_display)
        await b.start()

        env = {"DISPLAY": openbox_display, "PATH": "/usr/bin:/bin"}
        if not _have("xclock"):
            pytest.skip("xclock required")
        xc = subprocess.Popen(["xclock"], env=env)
        try:
            opened_ids: list[str] = []
            b.window_opened.connect(lambda info: opened_ids.append(info.id))
            await _pump_until(lambda: bool(opened_ids), duration_s=3.0)
            wid = opened_ids[0]

            with pytest.raises(UnknownOutput):
                await b.set_geometry(
                    wid, Geometry(0, 0, 100, 100), monitor="NONEXISTENT-99"
                )
        finally:
            try:
                xc.terminate()
                xc.wait(timeout=2.0)
            except subprocess.TimeoutExpired:
                xc.kill()
                xc.wait()

        await b.stop()

    asyncio.run(run())
