"""Private-session fixture for the live KWin integration tests.

Spawns a dedicated ``dbus-daemon`` + ``kwin_wayland --virtual`` so the
tests run against a real KWin scripting API without touching the user's
session. The private Wayland socket name includes the PID to avoid
collisions with concurrent runs.

Tests marked with ``@pytest.mark.kwin`` use these fixtures and skip
automatically when ``dbus-daemon`` / ``kwin_wayland`` are not on PATH, or
when the private KWin service doesn't come up within a timeout (the
latter happens on CI without ``libseat``).
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import select
import shutil
import signal
import subprocess
import time
from collections.abc import Iterator

import pytest


def _have_dbus_daemon() -> bool:
    return shutil.which("dbus-daemon") is not None


def _have_tools() -> bool:
    return (
        shutil.which("dbus-daemon") is not None
        and shutil.which("kwin_wayland") is not None
    )


def _start_dbus_daemon() -> tuple[subprocess.Popen[bytes], str]:
    """Launch a private session-bus daemon; return (process, address)."""
    rfd, wfd = os.pipe()
    try:
        proc = subprocess.Popen(
            [
                "dbus-daemon",
                "--session",
                "--nofork",
                f"--print-address={wfd}",
            ],
            pass_fds=(wfd,),
        )
    finally:
        os.close(wfd)
    # Wait on the pipe with select() so the deadline holds even while the
    # daemon is up and silent; a blocking read would hang past it. End of
    # file means the daemon exited, and there is nothing left to wait for.
    raw = b""
    deadline = time.monotonic() + 10.0
    with os.fdopen(rfd, "rb", buffering=0) as r:
        while b"\n" not in raw:
            remaining = deadline - time.monotonic()
            if remaining <= 0 or not select.select([r], [], [], remaining)[0]:
                break
            chunk = r.read(256)
            if not chunk:
                break
            raw += chunk
    address = raw.split(b"\n", 1)[0].decode().strip()
    if not address:
        proc.terminate()
        raise RuntimeError("dbus-daemon failed to publish an address")
    return proc, address


async def _wait_for_kwin(address: str, timeout: float = 15.0) -> None:
    """Poll ``org.kde.KWin`` on the private bus until it registers."""
    # sdbus's own proxy, not a hand-declared class: sdbus allows one async
    # interface class per D-Bus interface name per process, and the KWin
    # backend uses this one too.
    from sdbus import sd_bus_open_user, set_default_bus
    from sdbus_async.dbus_daemon import FreedesktopDbus

    env_backup = os.environ.get("DBUS_SESSION_BUS_ADDRESS")
    os.environ["DBUS_SESSION_BUS_ADDRESS"] = address
    try:
        set_default_bus(sd_bus_open_user())
        svc = FreedesktopDbus()
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                names = await svc.list_names()
                if "org.kde.KWin" in names:
                    return
            except Exception:
                pass
            await asyncio.sleep(0.1)
        raise RuntimeError(f"org.kde.KWin never appeared on {address}")
    finally:
        if env_backup is None:
            os.environ.pop("DBUS_SESSION_BUS_ADDRESS", None)
        else:
            os.environ["DBUS_SESSION_BUS_ADDRESS"] = env_backup


def wayland_socket() -> str:
    """The Wayland socket :func:`virtual_kwin_session` gives its KWin."""
    return f"wayland-perch-{os.getpid()}"


@pytest.fixture(scope="module")
def virtual_kwin_session() -> Iterator[str]:
    """A private ``DBUS_SESSION_BUS_ADDRESS`` with a live virtual KWin.

    Module-scoped because spinning up kwin_wayland is slow (~1 s) and
    every integration test in the module shares the same session.
    """
    if not _have_tools():
        pytest.skip("dbus-daemon or kwin_wayland not installed; live KWin tests skipped")

    dbus_proc, address = _start_dbus_daemon()

    # Use a unique wayland socket so a concurrent Plasma session on the
    # same host doesn't collide.
    socket = wayland_socket()
    env = {
        **{k: v for k, v in os.environ.items() if not k.startswith("WAYLAND_")},
        "DBUS_SESSION_BUS_ADDRESS": address,
        # Suppress xdg-desktop-portal activation chatter on the private bus.
        "GNOME_DESKTOP_SESSION_ID": "kwin-virtual-test",
    }
    kwin_proc = subprocess.Popen(
        [
            "kwin_wayland",
            "--virtual",
            "--width", "1920",
            "--height", "1080",
            "--no-lockscreen",
            "--socket", socket,
        ],
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    try:
        asyncio.run(_wait_for_kwin(address))
    except Exception as exc:
        kwin_proc.terminate()
        with contextlib.suppress(subprocess.TimeoutExpired):
            kwin_proc.wait(timeout=5.0)
        dbus_proc.terminate()
        with contextlib.suppress(subprocess.TimeoutExpired):
            dbus_proc.wait(timeout=5.0)
        pytest.skip(f"virtual KWin did not come up: {exc}")

    try:
        yield address
    finally:
        kwin_proc.send_signal(signal.SIGTERM)
        try:
            kwin_proc.wait(timeout=5.0)
        except subprocess.TimeoutExpired:
            kwin_proc.kill()
            kwin_proc.wait()
        dbus_proc.terminate()
        try:
            dbus_proc.wait(timeout=5.0)
        except subprocess.TimeoutExpired:
            dbus_proc.kill()
            dbus_proc.wait()
