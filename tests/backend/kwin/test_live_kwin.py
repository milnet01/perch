"""Live integration tests: ``KWinBackend`` against ``kwin_wayland --virtual``.

Gated on ``@pytest.mark.kwin`` — CI can opt in with ``pytest -m kwin`` and
opt out with ``pytest -m 'not kwin'``. The underlying fixture skips
automatically when ``dbus-daemon`` / ``kwin_wayland`` are missing, or
when the virtual KWin fails to come up (e.g. in CI without ``libseat``).

These tests exercise the real round-trip between the Python backend and
the KWin scripting API: script load, enumeration queries, and the
invalidation + clean unload on shutdown. They don't cover hotkeys —
KGlobalAccel lives on the user's session bus, not the private one we
spawn here; the manual checklist (``docs/testing/kwin-checklist.md``)
covers that path.

Each test structures its work as ``asyncio.run(run())`` so the bus
proxies, the backend, and the teardown all share one event loop. Bus
objects bound to a loop that has already closed produce cryptic
"A connection to the bus can't be made" errors.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest
from PySide6.QtCore import QCoreApplication

from perch.backend.kwin import KWinBackend
from perch.backend.kwin.hotkeys import MockHotkeyProvider

pytestmark = pytest.mark.kwin


@pytest.fixture(autouse=True)
def _qapp(qapp: Any) -> None:
    """QApplication so Qt signals / timers work inside the tests."""


@pytest.fixture(autouse=True)
def _wayland_env(
    virtual_kwin_session: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Route DBUS_SESSION_BUS_ADDRESS + XDG session type for the backend."""
    monkeypatch.setenv("DBUS_SESSION_BUS_ADDRESS", virtual_kwin_session)
    monkeypatch.setenv("XDG_SESSION_TYPE", "wayland")
    monkeypatch.setenv("XDG_CURRENT_DESKTOP", "KDE")


# ── Happy-path start / enumeration ────────────────────────────────────────


def test_start_connects_and_enumerates_outputs() -> None:
    """kwin_wayland --virtual publishes exactly one virtual output."""

    async def run() -> None:
        b = KWinBackend(hotkey_provider=MockHotkeyProvider())
        await b.start()
        try:
            outs = await b.list_outputs()
            assert len(outs) == 1
            # The virtual output is named "Virtual-0" on Plasma 6.6.x; the
            # exact string has shifted on other point releases, so only
            # assert it's non-empty and the geometry matches what we asked for.
            assert outs[0].name
            assert outs[0].geometry.w == 1920
            assert outs[0].geometry.h == 1080

            assert await b.desktop_count() >= 1
            assert await b.current_desktop() == 0
        finally:
            await b.stop()

    asyncio.run(run())


def test_list_windows_is_empty_on_fresh_virtual_kwin() -> None:
    """A bare --virtual session has no managed windows yet.

    Virtual KWin may have placeholder internal windows; ``normalWindow``
    is false for them and the JS filter drops them, so a fresh session
    lists none at all. A tolerance here would let the filter regress.
    """

    async def run() -> None:
        b = KWinBackend(hotkey_provider=MockHotkeyProvider())
        await b.start()
        try:
            wins = await b.list_windows()
            assert wins == []
        finally:
            await b.stop()

    asyncio.run(run())


def test_stop_is_idempotent_on_a_started_backend() -> None:
    """stop() twice must not raise.

    Running two full start/stop cycles in the same Python process is out
    of scope for now — sdbus's service-export state doesn't cleanly
    recycle within a process, and real usage recovers from a dead KWin
    by restarting the whole Perch process (``state.json`` is the source
    of truth). The spike's cycle probe covers the JS-unload-then-load
    path against a live script.
    """

    async def run() -> None:
        b = KWinBackend(hotkey_provider=MockHotkeyProvider())
        await b.start()
        await b.stop()
        await b.stop()  # second stop is a no-op

    asyncio.run(run())


def test_backend_connected_signal_fires_on_start() -> None:
    async def run() -> None:
        b = KWinBackend(hotkey_provider=MockHotkeyProvider())
        seen: list[bool] = []
        b.backend_connected.connect(lambda: seen.append(True))
        await b.start()
        try:
            QCoreApplication.processEvents()
            assert seen == [True]
        finally:
            await b.stop()

    asyncio.run(run())


# ── Events from a real window (PERC-0046) ─────────────────────────────────

_CLIENT = """
import sys, time
from PySide6.QtWidgets import QApplication, QWidget
app = QApplication(sys.argv)
w = QWidget()
w.setWindowTitle("perch-live-probe")
w.resize(320, 240)
w.show()
deadline = time.monotonic() + 30
while time.monotonic() < deadline:
    app.processEvents()
    time.sleep(0.02)
"""


def test_a_moved_window_reports_its_new_geometry() -> None:
    """main.js debounced geometry through ``QTimer.triggered``, which KWin's
    QJSEngine does not have (the signal is ``timeout``): the connect threw on
    every geometry change, so Perch never heard a window move."""
    import os
    import subprocess
    import sys

    from perch.backend.types import Geometry

    from .conftest import wayland_socket

    async def run() -> None:
        b = KWinBackend(hotkey_provider=MockHotkeyProvider())
        opened: list[str] = []
        moved: list[Geometry] = []
        b.window_opened.connect(
            lambda info: opened.append(info.id)
            if info.title == "perch-live-probe"
            else None
        )
        b.geometry_changed.connect(lambda _wid, geom, *_rest: moved.append(geom))
        await b.start()
        client = subprocess.Popen(
            [sys.executable, "-c", _CLIENT],
            env={
                **os.environ,
                "QT_QPA_PLATFORM": "wayland",
                "WAYLAND_DISPLAY": wayland_socket(),
            },
        )
        try:
            for _ in range(200):
                if opened:
                    break
                await asyncio.sleep(0.05)
            assert opened, "the KWin script never reported the probe window"
            moved.clear()
            target = Geometry(100, 120, 400, 300)
            await b.set_geometry(opened[0], target)
            for _ in range(100):
                if target in moved:
                    break
                await asyncio.sleep(0.05)
            assert target in moved
        finally:
            client.kill()
            client.wait()
            await b.stop()

    asyncio.run(run())


# ── A KWin settings reload keeps the script (PERC-0097) ───────────────────


def test_the_script_survives_a_kwin_settings_reload(
    virtual_kwin_session: str,
) -> None:
    """Perch installs its script as a KWin package and KWin leaves that
    package disabled. On every settings reload KWin unloads a disabled
    package's script BY NAME, so a live script loaded under the package's
    own name died with it and Perch heard nothing more until restarted."""
    import os
    import subprocess

    async def run() -> None:
        b = KWinBackend(hotkey_provider=MockHotkeyProvider())
        await b.start()
        try:
            subprocess.run(
                [
                    "dbus-send", "--session", "--print-reply",
                    "--dest=org.kde.KWin", "/KWin", "org.kde.KWin.reconfigure",
                ],
                env={**os.environ, "DBUS_SESSION_BUS_ADDRESS": virtual_kwin_session},
                check=True,
                capture_output=True,
            )
            await asyncio.sleep(1.0)
            try:
                outs = await asyncio.wait_for(b.list_outputs(), timeout=5.0)
            except TimeoutError:
                pytest.fail("the script stopped answering after a KWin reload")
            assert outs
        finally:
            await b.stop()

    asyncio.run(run())



# ── A window placed by Perch is held there briefly (PERC-0095) ────────────

_PUSH_JS = """
for (const w of workspace.windowList()) {
    if (w.caption === "perch-live-probe") {
        w.frameGeometry = {x: 600, y: 500, width: w.frameGeometry.width,
                           height: w.frameGeometry.height};
    }
}
"""

_MAXIMISE_JS = """
for (const w of workspace.windowList()) {
    if (w.caption === "perch-live-probe") w.setMaximize(true, true);
}
"""


async def _place_then_run(
    tmp_path: Any, steps: Any
) -> None:
    """Open the probe window, place it at 100,120 keeping its size, then
    hand ``steps(where, target, run_js)`` the rest. ``run_js`` runs a
    one-shot KWin script, standing in for whatever moves the window."""
    import os
    import subprocess
    import sys

    from perch.backend.kwin.scripting import (
        KWIN_SCRIPTING_OBJ,
        KWIN_SERVICE,
        KWinScripting,
        install_and_run_script,
        unload_script_if_loaded,
    )
    from perch.backend.types import Geometry, WindowInfo

    from .conftest import wayland_socket

    b = KWinBackend(hotkey_provider=MockHotkeyProvider())
    opened: list[str] = []
    b.window_opened.connect(
        lambda info: opened.append(info.id)
        if info.title == "perch-live-probe"
        else None
    )
    await b.start()
    scripting = KWinScripting.new_proxy(KWIN_SERVICE, KWIN_SCRIPTING_OBJ)

    async def run_js(source: str) -> None:
        path = tmp_path / "push.js"
        path.write_text(source)
        await unload_script_if_loaded(scripting, "perch-test-push")
        await install_and_run_script(scripting, path, "perch-test-push")

    async def where() -> WindowInfo:
        return await b.get_window(opened[0])

    client = subprocess.Popen(
        [sys.executable, "-c", _CLIENT],
        env={
            **os.environ,
            "QT_QPA_PLATFORM": "wayland",
            "WAYLAND_DISPLAY": wayland_socket(),
        },
    )
    try:
        for _ in range(200):
            if opened:
                break
            await asyncio.sleep(0.05)
        assert opened, "the KWin script never reported the probe window"
        # Position only, as on the desktop: a size change waits for the
        # client to confirm it and would overwrite the push afterwards.
        size = (await where()).geometry
        target = Geometry(100, 120, size.w, size.h)
        await b.set_geometry(opened[0], target)
        await steps(where, target, run_js)
    finally:
        await unload_script_if_loaded(scripting, "perch-test-push")
        client.kill()
        client.wait()
        await b.stop()


def test_a_placed_window_pushed_straight_back_is_put_back(
    tmp_path: Any,
) -> None:
    """On Plasma Wayland KWin sometimes moved a just-restored window back to
    its own spot a millisecond after accepting Perch's move. The virtual
    KWin does not do that by itself, so a second script does the pushing:
    straight after placement it must be undone, and once the hold is over
    a move must be left alone."""

    async def steps(where: Any, target: Any, run_js: Any) -> None:
        await run_js(_PUSH_JS)
        await asyncio.sleep(0.3)
        assert (await where()).geometry == target, (
            "a push straight after placement stuck"
        )
        await asyncio.sleep(1.0)
        await run_js(_PUSH_JS)
        await asyncio.sleep(0.3)
        assert (await where()).geometry.x == 600, "a move after the hold was undone"

    asyncio.run(_place_then_run(tmp_path, steps))


def test_a_placed_window_may_maximise_itself(tmp_path: Any) -> None:
    """An app may maximise itself right after opening, restoring its own
    state. The hold must let it, not pull it back to the placed rect."""
    from perch.backend.types import WindowState

    async def steps(where: Any, _target: Any, run_js: Any) -> None:
        await run_js(_MAXIMISE_JS)
        await asyncio.sleep(0.5)
        assert (await where()).state == WindowState.MAXIMIZED

    asyncio.run(_place_then_run(tmp_path, steps))
