"""Skeleton-level tests for :class:`X11Backend` that do not need an X display.

The live end-to-end tests live in ``test_live_openbox.py`` (M4.g). What we
cover here is:
  - :class:`BackendUnavailable` when ``$DISPLAY`` / explicit name is missing.
  - :class:`BackendDisconnected` when a method is called before ``start()``.
  - Skeleton commands (``set_geometry`` / ``set_state`` / ``close_window``)
    raise :class:`BackendUnsupported` prior to M4.e landing.
  - Hotkey methods raise :class:`BackendUnsupported` prior to M4.f landing.
  - :attr:`capabilities` matches the X11 design (``docs/04-backend-x11.md``).
"""

from __future__ import annotations

import pytest

from perch.backend.base import (
    BackendDisconnected,
    BackendUnavailable,
    BackendUnsupported,
)
from perch.backend.types import Geometry, WindowState
from perch.backend.x11 import X11Backend


@pytest.fixture(autouse=True)
def _qapp(qapp: object) -> None:
    """X11Backend is a QObject; construction requires a QApplication."""


def test_missing_display_raises_backend_unavailable() -> None:
    # A guaranteed-not-a-real-display name. Xlib immediately errors.
    backend = X11Backend(display_name=":99999.0")
    import asyncio

    async def go() -> None:
        with pytest.raises(BackendUnavailable):
            await backend.start()

    asyncio.run(go())


def test_methods_require_start_first() -> None:
    backend = X11Backend(display_name=":99999.0")
    import asyncio

    async def go() -> None:
        with pytest.raises(BackendDisconnected):
            await backend.list_outputs()
        with pytest.raises(BackendDisconnected):
            await backend.current_desktop()
        with pytest.raises(BackendDisconnected):
            await backend.desktop_count()
        with pytest.raises(BackendDisconnected):
            await backend.list_windows()

    asyncio.run(go())


def test_get_window_requires_connection() -> None:
    # X11Backend.get_window must hit the live display (unlike the MockBackend
    # dict-lookup). With no Display attached, BackendDisconnected is the
    # correct surface — an UnknownWindow here would promise that "no such
    # window exists" when really we simply can't answer the question.
    backend = X11Backend(display_name=":99999.0")
    import asyncio

    async def go() -> None:
        with pytest.raises(BackendDisconnected):
            await backend.get_window("nope")

    asyncio.run(go())


def test_commands_raise_backend_unsupported_until_m4e() -> None:
    backend = X11Backend(display_name=":99999.0")
    import asyncio

    async def go() -> None:
        with pytest.raises(BackendUnsupported):
            await backend.set_geometry("w1", Geometry(0, 0, 800, 600))
        with pytest.raises(BackendUnsupported):
            await backend.set_state("w1", WindowState.MAXIMIZED)
        with pytest.raises(BackendUnsupported):
            await backend.close_window("w1")

    asyncio.run(go())


def test_hotkey_methods_raise_backend_unsupported_until_m4f() -> None:
    backend = X11Backend(display_name=":99999.0")
    import asyncio

    async def go() -> None:
        with pytest.raises(BackendUnsupported):
            await backend.register_hotkey("Meta+Left", "cb1")
        with pytest.raises(BackendUnsupported):
            await backend.unregister_hotkey("cb1")

    asyncio.run(go())


def test_capabilities_match_documented_x11_surface() -> None:
    backend = X11Backend(display_name=":99999.0")
    caps = backend.capabilities
    # Everything X11/EWMH can do is declared true except can_preplace_windows.
    assert caps.can_set_position is True
    assert caps.can_set_size is True
    assert caps.can_set_monitor is True
    assert caps.can_set_desktop is True
    assert caps.can_set_state is True
    assert caps.can_enumerate_windows is True
    assert caps.can_observe_geometry is True
    assert caps.can_observe_outputs is True
    assert caps.can_register_hotkeys is True
    assert caps.can_preplace_windows is False
    assert "python-xlib" in caps.notes


def test_stop_on_never_started_is_a_noop() -> None:
    backend = X11Backend(display_name=":99999.0")
    import asyncio

    async def go() -> None:
        await backend.stop()  # must not raise

    asyncio.run(go())
