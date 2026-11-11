"""Shutdown finishes when a background task is still in flight (PERC-0100).

Runs the real ``app.main()`` in a child process, under ``asyncio.run`` with
qasync's loop exactly as ``cli()`` does. The pytest process already runs its
own event loop, so this cannot run in-process.
"""

from __future__ import annotations

import os
import subprocess
import sys
import textwrap
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

# A window event's handler is still waiting on a D-Bus reply when SIGTERM
# arrives, and the reply lands just as main() returns. Before the fix, that
# wakeup ran after qasync had stopped the loop and was lost, so asyncio.run's
# own cleanup waited for the task forever.
_CHILD = textwrap.dedent(
    """
    import asyncio, os, signal, sys
    from dataclasses import replace
    from PySide6.QtWidgets import QApplication
    from qasync import QEventLoop
    from perch import app as perch_app, autostart
    from perch.backend.mock import MockBackend
    from perch.config import load_or_create
    from perch.core.reducer import Reducer

    qapp = QApplication(sys.argv)
    backend = MockBackend()
    reply: list[asyncio.Future[None]] = []

    async def awaiting_reply(self, info):
        fut = asyncio.get_running_loop().create_future()
        reply.append(fut)
        os.kill(os.getpid(), signal.SIGTERM)
        await fut

    real_stop = backend.stop

    async def stop():
        await real_stop()
        reply[0].set_result(None)

    backend.stop = stop
    Reducer._on_window_opened = awaiting_reply
    perch_app._select_backend = lambda: backend
    autostart.sync_from_config = lambda _c: None
    config = load_or_create()
    config = replace(
        config, general=replace(config.general, onboarding_completed=True)
    )
    perch_app.load_or_create = lambda: config

    async def run():
        asyncio.get_running_loop().call_later(
            0.2, backend.window_opened.emit, object()
        )
        return await perch_app.main(have_sni_host=True, gnome_wayland=False)

    print("rc", asyncio.run(run(), loop_factory=QEventLoop), flush=True)
    """
)


def test_shutdown_finishes_with_a_task_in_flight(xdg_env: Path) -> None:
    del xdg_env
    try:
        done = subprocess.run(
            [sys.executable, "-c", _CHILD],
            capture_output=True,
            text=True,
            timeout=20,
            env={**os.environ, "QT_QPA_PLATFORM": "offscreen"},
        )
    except subprocess.TimeoutExpired as exc:
        # The timeout hands back bytes even under text=True.
        stderr = exc.stderr.decode(errors="replace") if exc.stderr else ""
        raise AssertionError(
            f"shutdown hung with a task in flight; stderr:\n{stderr}"
        ) from None
    assert done.returncode == 0, done.stderr
    assert "rc 0" in done.stdout
    assert "is not the running loop" not in done.stderr
