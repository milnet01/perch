"""The KWin backend's bus-name claim on a private bus (PERC-0049)."""

from __future__ import annotations

import asyncio
import os
import subprocess
import sys
import time
from collections.abc import Iterator

import pytest

from .conftest import _have_dbus_daemon, _start_dbus_daemon

_NAME = "io.github.milnet01.Perch.BusNameTest"


@pytest.fixture
def private_bus(monkeypatch: pytest.MonkeyPatch) -> Iterator[str]:
    if not _have_dbus_daemon():
        pytest.skip("dbus-daemon not installed")
    proc, address = _start_dbus_daemon()
    monkeypatch.setenv("DBUS_SESSION_BUS_ADDRESS", address)
    try:
        yield address
    finally:
        proc.terminate()
        proc.wait(timeout=5.0)


def test_a_name_held_by_another_process_is_not_treated_as_ours(
    private_bus: str,
) -> None:
    """The suppressed SdBusRequestNameExistsError let a second Perch
    believe it owned the service while every command timed out."""
    from sdbus.sd_bus_internals import SdBusRequestNameExistsError

    from perch.backend.kwin.backend import _default_bus_setup

    holder = subprocess.Popen(
        [
            sys.executable,
            "-c",
            "import sdbus, time;"
            "sdbus.set_default_bus(sdbus.sd_bus_open_user());"
            f"sdbus.request_default_bus_name({_NAME!r});"
            "print('held', flush=True); time.sleep(30)",
        ],
        env={**os.environ, "DBUS_SESSION_BUS_ADDRESS": private_bus},
        stdout=subprocess.PIPE,
        text=True,
    )
    try:
        assert holder.stdout is not None
        assert holder.stdout.readline().strip() == "held"
        with pytest.raises(SdBusRequestNameExistsError):
            asyncio.run(_default_bus_setup(_NAME))
    finally:
        holder.kill()
        holder.wait()


def test_reclaiming_our_own_name_within_one_process_succeeds(
    private_bus: str,
) -> None:
    from perch.backend.kwin.backend import _default_bus_setup

    del private_bus

    async def twice() -> None:
        await _default_bus_setup(_NAME)
        await _default_bus_setup(_NAME)

    started = time.monotonic()
    asyncio.run(twice())
    assert time.monotonic() - started < 10
