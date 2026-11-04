"""The session Xvfb that pytest-xvfb starts must not reset between clients.

PERC-0089. pytest-xvfb starts Xvfb through pyvirtualdisplay, which pipes the
server's stderr and never reads it. By default Xvfb resets every time its
last client disconnects, and each reset writes the keymap compiler's warnings
to that pipe. The X11 compliance tests connect and disconnect once per test,
so after enough of them the pipe fills, Xvfb blocks writing to it, and the
next ``X11Backend.start()`` hangs in connection setup.

``-noreset`` in ``xvfb_args`` (pyproject.toml) keeps the server up across
clients. A reset recreates the root window, so a property set on root by a
client that has since disconnected is gone after one, and still there
without one.
"""

from __future__ import annotations

import os
import time

import pytest

Xlib_display = pytest.importorskip("Xlib.display")
Xlib_error = pytest.importorskip("Xlib.error")
pytest_xvfb = pytest.importorskip("pytest_xvfb")


def _session_xvfb_display() -> str:
    """The display name of pytest-xvfb's own Xvfb, or skip.

    The test writes to the root window, so it must never run against the
    host's display: only against the server pytest-xvfb started.
    """
    instance = pytest_xvfb.xvfb_instance
    if instance is None or instance.display is None:
        pytest.skip("pytest-xvfb did not start an Xvfb for this session")
    name = f":{instance.display}"
    if os.environ.get("DISPLAY") != name:
        pytest.skip("$DISPLAY is not pytest-xvfb's Xvfb")
    return name


def _connect(name: str) -> object:
    # A reset in progress can drop a new connection during setup; that is
    # the server restarting, not the answer this test is after.
    for _ in range(50):
        try:
            return Xlib_display.Display(name)
        except Xlib_error.ConnectionClosedError:
            time.sleep(0.05)
    pytest.fail(f"could not connect to {name}")


def test_session_xvfb_keeps_state_after_last_client_leaves() -> None:
    name = _session_xvfb_display()
    marker = f"perch-noreset-{os.getpid()}-{time.monotonic_ns()}"

    writer = _connect(name)
    writer.screen().root.set_wm_name(marker)  # type: ignore[attr-defined]
    writer.sync()  # type: ignore[attr-defined]
    writer.close()  # type: ignore[attr-defined]
    # Give a resetting server time to finish before looking.
    time.sleep(0.2)

    reader = _connect(name)
    try:
        seen = reader.screen().root.get_wm_name()  # type: ignore[attr-defined]
    finally:
        reader.close()  # type: ignore[attr-defined]
    assert seen == marker, (
        "the session Xvfb reset when its last client left; without -noreset "
        "its unread stderr pipe fills and the X11 compliance tests hang "
        "(PERC-0089)"
    )
