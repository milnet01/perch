"""app.main() startup and shutdown seams (PERC-0064)."""

from __future__ import annotations

import signal
from dataclasses import replace
from typing import TYPE_CHECKING, Any

import pytest
from PySide6.QtWidgets import QApplication

from perch import app as perch_app
from perch import autostart
from perch.backend.mock import MockBackend
from perch.config import load_or_create
from perch.core.reducer import Reducer

if TYPE_CHECKING:
    from pathlib import Path

    from pytestqt.qtbot import QtBot


class _Loop:
    """Records add_signal_handler calls; refuses the ones listed."""

    def __init__(self, refuse: set[int]) -> None:
        self.refuse = refuse
        self.installed: list[int] = []

    def add_signal_handler(self, sig: int, handler: Any) -> None:
        if sig in self.refuse:
            raise NotImplementedError
        self.installed.append(sig)


def test_a_refused_sigint_still_installs_sigterm() -> None:
    """One suppress round both calls meant a SIGINT failure silently
    skipped SIGTERM — the signal the session manager sends at logout."""
    loop = _Loop(refuse={signal.SIGINT})
    perch_app._install_signal_handlers(loop, lambda: None)  # type: ignore[arg-type]
    assert loop.installed == [signal.SIGTERM]


async def test_main_refuses_to_run_without_a_qapplication(
    monkeypatch: pytest.MonkeyPatch, xdg_env: Path
) -> None:
    """An assert here vanished under ``python -O``."""
    del xdg_env
    monkeypatch.setattr(QApplication, "instance", staticmethod(lambda: None))
    with pytest.raises(RuntimeError, match="QApplication"):
        await perch_app.main(have_sni_host=True, gnome_wayland=False)


async def test_backend_is_stopped_when_startup_fails_after_it_started(
    qtbot: QtBot, monkeypatch: pytest.MonkeyPatch, xdg_env: Path
) -> None:
    """Between a successful backend.start() and the main loop, a raise from
    reducer.start() skipped backend.stop() — leaving the KWin script
    loaded and the bus name held."""
    del qtbot, xdg_env
    backend = MockBackend()
    stopped: list[bool] = []
    real_stop = backend.stop

    async def stop() -> None:
        stopped.append(True)
        await real_stop()

    monkeypatch.setattr(backend, "stop", stop)
    monkeypatch.setattr(perch_app, "_select_backend", lambda: backend)
    monkeypatch.setattr(autostart, "sync_from_config", lambda _c: None)

    config = load_or_create()
    general = replace(config.general, onboarding_completed=True)
    monkeypatch.setattr(
        "perch.app.load_or_create", lambda: replace(config, general=general)
    )

    async def failing_start(self: Any) -> None:
        raise OSError("state flush failed")

    monkeypatch.setattr(Reducer, "start", failing_start)
    with pytest.raises(OSError, match="state flush failed"):
        await perch_app.main(have_sni_host=True, gnome_wayland=False)
    assert stopped == [True]
