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

    Virtual KWin may have placeholder internal windows on some versions;
    the contract is only that ``normalWindow`` is false for them, which
    the JS filter enforces. We accept an empty or tiny list; reject an
    obvious explosion.
    """

    async def run() -> None:
        b = KWinBackend(hotkey_provider=MockHotkeyProvider())
        await b.start()
        try:
            wins = await b.list_windows()
            assert len(wins) < 10
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
