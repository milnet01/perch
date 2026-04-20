"""Xvfb + openbox fixture for live X11 backend tests.

Launches ``Xvfb -displayfd`` so Xvfb picks a free display number (fixed
numbers are flaky in CI — shared runners leave stale ``/tmp/.X99-lock``
files), starts openbox against that display with ``--sm-disable``, and
polls root for ``_NET_SUPPORTING_WM_CHECK`` before yielding.

Tests marked with ``pytest.mark.x11`` will be skipped automatically when
Xvfb or openbox is not installed, so the rest of the suite keeps running
in minimal environments (and in developer checkouts before the system
packages are installed).
"""

from __future__ import annotations

import os
import shutil
import subprocess
import time
from collections.abc import Iterator

import pytest


def _have_tools() -> bool:
    return shutil.which("Xvfb") is not None and shutil.which("openbox") is not None


def _start_xvfb() -> tuple[subprocess.Popen[bytes], str]:
    """Launch Xvfb on a free display, returning (process, ``:N``)."""
    rfd, wfd = os.pipe()
    try:
        proc = subprocess.Popen(
            [
                "Xvfb",
                "-displayfd",
                str(wfd),
                "-screen",
                "0",
                "1920x1080x24",
            ],
            pass_fds=(wfd,),
        )
    finally:
        os.close(wfd)
    display_num = ""
    deadline = time.monotonic() + 10.0
    with os.fdopen(rfd, "r") as r:
        while time.monotonic() < deadline:
            ch = r.read(1)
            if not ch:
                time.sleep(0.05)
                continue
            if ch == "\n":
                break
            display_num += ch
    if not display_num:
        proc.terminate()
        raise RuntimeError("Xvfb failed to bind to a display")
    return proc, f":{display_num}"


def _wait_for_wm(display_name: str, timeout: float = 10.0) -> None:
    """Poll ``_NET_SUPPORTING_WM_CHECK`` on root until the WM has set it."""
    from Xlib import Xatom
    from Xlib import display as _display

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            d = _display.Display(display_name)
            try:
                atom = d.intern_atom("_NET_SUPPORTING_WM_CHECK", only_if_exists=True)
                if atom != 0:
                    prop = d.screen().root.get_full_property(atom, Xatom.WINDOW)
                    if prop is not None and prop.value:
                        return
            finally:
                d.close()
        except Exception:
            pass
        time.sleep(0.05)
    raise RuntimeError(f"No WM claimed {display_name} within {timeout:.1f}s")


@pytest.fixture
def openbox_display() -> Iterator[str]:
    """A display name like ``":1"`` with Xvfb + openbox running, WM ready."""
    if not _have_tools():
        pytest.skip("Xvfb or openbox not installed; live X11 tests skipped")
    xvfb, display = _start_xvfb()
    env = {**os.environ, "DISPLAY": display}
    ob = subprocess.Popen(["openbox", "--sm-disable"], env=env)
    try:
        _wait_for_wm(display)
        yield display
    finally:
        ob.terminate()
        try:
            ob.wait(timeout=2.0)
        except subprocess.TimeoutExpired:
            ob.kill()
            ob.wait()
        xvfb.terminate()
        try:
            xvfb.wait(timeout=2.0)
        except subprocess.TimeoutExpired:
            xvfb.kill()
            xvfb.wait()
