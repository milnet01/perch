"""Skeleton-level tests for :class:`X11Backend` that do not need an X display.

The live end-to-end tests live in ``test_live_openbox.py`` (M4.g). What we
cover here is:
  - :class:`BackendUnavailable` when ``$DISPLAY`` / explicit name is missing.
  - :class:`BackendDisconnected` when *any* method is called before
    ``start()``.
  - :attr:`capabilities` matches the X11 design (``docs/04-backend-x11.md``).
"""

from __future__ import annotations

import pytest

from perch.backend.base import (
    BackendDisconnected,
    BackendUnavailable,
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


def test_commands_require_connection() -> None:
    backend = X11Backend(display_name=":99999.0")
    import asyncio

    async def go() -> None:
        with pytest.raises(BackendDisconnected):
            await backend.set_geometry("w1", Geometry(0, 0, 800, 600))
        with pytest.raises(BackendDisconnected):
            await backend.set_state("w1", WindowState.MAXIMIZED)
        with pytest.raises(BackendDisconnected):
            await backend.close_window("w1")

    asyncio.run(go())


def test_hotkey_methods_require_connection() -> None:
    backend = X11Backend(display_name=":99999.0")
    import asyncio

    async def go() -> None:
        with pytest.raises(BackendDisconnected):
            await backend.register_hotkey("Meta+Left", "cb1")
        with pytest.raises(BackendDisconnected):
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


# ── Connection reset during start() ──────────────────────────────────────────
# python-xlib wraps a ConnectionResetError from the setup handshake in
# Xlib.error.ConnectionClosedError, which subclasses Exception alone — NOT
# OSError — so it is not covered by start()'s ConnectionError/OSError arms and
# has to be named. Real trigger: an X session ending as Perch starts. Caught in
# CI run 33145715623, where a just-launched Xvfb reset the connection and the
# raw Xlib traceback escaped start() instead of the documented
# BackendUnavailable (docs/03-backend-interface.md §Errors).


def test_connection_reset_during_setup_is_backend_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from Xlib import display as xdisplay
    from Xlib import error as xerror

    def _reset(_name: str | None) -> object:
        raise xerror.ConnectionClosedError("server")

    # X11Backend holds this very module as ``_display``, so patching the
    # attribute here is what its ``_display.Display(...)`` call resolves.
    monkeypatch.setattr(xdisplay, "Display", _reset)
    backend = X11Backend(display_name=":0")
    import asyncio

    async def go() -> None:
        with pytest.raises(BackendUnavailable):
            await backend.start()

    asyncio.run(go())


def test_display_lost_mid_handshake_tears_down(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A drop *after* the socket opens must not leave a half-open backend."""
    from unittest.mock import MagicMock

    from Xlib import display as xdisplay
    from Xlib import error as xerror

    fake = MagicMock()
    fake.screen.side_effect = xerror.ConnectionClosedError("server")
    monkeypatch.setattr(xdisplay, "Display", lambda _name: fake)
    backend = X11Backend(display_name=":0")
    import asyncio

    async def go() -> None:
        with pytest.raises(BackendUnavailable):
            await backend.start()

    asyncio.run(go())
    # The display is released and the backend reports itself disconnected,
    # so the next start() attempt begins from a clean slate.
    fake.close.assert_called_once()
    with pytest.raises(BackendDisconnected):
        asyncio.run(backend.list_outputs())


def test_set_geometry_sends_desktop_before_placement(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """docs/07 §Apply order step 2 — the placement is the last word.

    A window manager is free to re-place a window when its desktop
    changes, so sending the move after the placement can undo it. The
    KWin backend already ordered its batch this way.
    """
    import asyncio
    from unittest.mock import MagicMock

    from perch.backend.x11 import backend as x11_backend

    monkeypatch.setattr(
        x11_backend, "build_wm_desktop_message", lambda *a, **k: "desktop-msg"
    )
    monkeypatch.setattr(
        x11_backend, "build_moveresize_message", lambda *a, **k: "place-msg"
    )

    backend = X11Backend()
    display = MagicMock()
    root = display.screen.return_value.root
    monkeypatch.setattr(backend, "_require_connected", lambda: display)
    monkeypatch.setattr(backend, "_require_atoms", MagicMock())
    backend._windows["w1"] = MagicMock()

    asyncio.run(
        backend.set_geometry("w1", Geometry(0, 0, 800, 600), desktop=2)
    )

    sent = [call.args[0] for call in root.send_event.call_args_list]
    assert sent == ["desktop-msg", "place-msg"]


# ── PERC-0047: a server without the RandR extension ──────────────────────────
# python-xlib binds the xrandr_* methods onto the drawable class only once the
# extension is present, so on a RandR-less server the call raises
# AttributeError — not the BadAccess the handler names. The AttributeError
# escapes start() and the backend never comes up at all.


class _NoRandRRoot:
    """A root window that has never heard of the RandR extension."""

    def __init__(self) -> None:
        self.change_attributes_calls = 0

    def change_attributes(self, **_kw: object) -> None:
        self.change_attributes_calls += 1

    def __getattr__(self, name: str) -> object:
        if name.startswith("xrandr_"):
            raise AttributeError(name)
        raise AttributeError(name)


def test_randr_absent_degrades_instead_of_killing_start(
    caplog: pytest.LogCaptureFixture,
) -> None:
    import logging
    from unittest.mock import MagicMock

    backend = X11Backend()
    display = MagicMock()
    display.screen.return_value.root = _NoRandRRoot()
    backend._d = display

    with caplog.at_level(logging.WARNING, logger="perch.backend.x11.backend"):
        backend._init_randr_subscription()

    # Degraded, not crashed — and it left a trace saying so.
    assert any("randr" in r.message.lower() for r in caplog.records)


def test_list_outputs_without_randr_returns_empty(
    caplog: pytest.LogCaptureFixture,
) -> None:
    import logging

    from perch.backend.x11.outputs import list_outputs

    display = type(
        "_D", (), {"screen": lambda self: type("_S", (), {"root": _NoRandRRoot()})()}
    )()
    with caplog.at_level(logging.WARNING, logger="perch.backend.x11.outputs"):
        got = list_outputs(display)

    assert got == []
    assert any("randr" in r.message.lower() for r in caplog.records)


# ── PERC-0047: close_window must stay a request ──────────────────────────────
# docs/03-backend-interface.md: close_window "Requests the window close
# (WM_DELETE_WINDOW / xdg_toplevel close)". XKillClient is not a request — it
# tears down the client's whole connection, taking every other window it owns
# with it and offering no save prompt.


def test_close_window_never_kills_the_client_connection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import asyncio
    from unittest.mock import MagicMock

    from perch.backend.base import BackendUnsupported

    backend = X11Backend()
    display = MagicMock()
    monkeypatch.setattr(backend, "_require_connected", lambda: display)
    monkeypatch.setattr(backend, "_require_atoms", MagicMock())
    backend._windows["w1"] = MagicMock()
    # This window advertises no WM_DELETE_WINDOW.
    monkeypatch.setattr(backend, "_supports_delete_protocol", lambda *_a: False)

    with pytest.raises(BackendUnsupported):
        asyncio.run(backend.close_window("w1"))

    display.kill_client.assert_not_called()


def test_close_window_sends_the_icccm_message_when_supported(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import asyncio
    from unittest.mock import MagicMock

    backend = X11Backend()
    display = MagicMock()
    monkeypatch.setattr(backend, "_require_connected", lambda: display)
    monkeypatch.setattr(backend, "_require_atoms", MagicMock())
    win = MagicMock()
    backend._windows["w1"] = win
    monkeypatch.setattr(backend, "_supports_delete_protocol", lambda *_a: True)

    asyncio.run(backend.close_window("w1"))

    win.send_event.assert_called_once()
    display.kill_client.assert_not_called()


# ── PERC-0047: restoring a minimised window ──────────────────────────────────
# Removing the maximised/fullscreen bits does nothing to an iconified window.
# EWMH wm-spec §5.7 makes _NET_ACTIVE_WINDOW the de-iconify request, and
# capabilities.can_set_state=True promises the round trip works.


def test_set_state_normal_deiconifies_via_active_window(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sent = _restore_to_normal(monkeypatch, WindowState.MINIMIZED)
    assert "active-msg" in sent, "NORMAL must un-iconify, not just clear bits"


def test_set_state_normal_does_not_steal_focus_from_a_maximised_window(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Activating also raises and focuses.

    Sending it unconditionally would make applying a layout shuffle the
    focus across every window it touches, so a window that was never
    iconified must not be activated.
    """
    sent = _restore_to_normal(monkeypatch, WindowState.MAXIMIZED)
    assert "active-msg" not in sent
    assert "state-msg" in sent, "the maximised bits must still be cleared"


def _restore_to_normal(
    monkeypatch: pytest.MonkeyPatch, current: WindowState
) -> list[object]:
    """Run set_state(NORMAL) on a window currently in ``current``."""
    import asyncio
    from unittest.mock import MagicMock

    from perch.backend.x11 import backend as x11_backend

    sent: list[object] = []
    monkeypatch.setattr(
        x11_backend, "build_active_window_message", lambda *a, **k: "active-msg"
    )
    monkeypatch.setattr(
        x11_backend, "build_wm_state_message", lambda *a, **k: "state-msg"
    )
    monkeypatch.setattr(x11_backend, "read_window_state", lambda *a: current)

    backend = X11Backend()
    display = MagicMock()
    root = display.screen.return_value.root
    root.send_event.side_effect = lambda msg, **_kw: sent.append(msg)
    monkeypatch.setattr(backend, "_require_connected", lambda: display)
    monkeypatch.setattr(backend, "_require_atoms", MagicMock())
    backend._windows["w1"] = MagicMock()

    asyncio.run(backend.set_state("w1", WindowState.NORMAL))
    return sent
