"""The exit watchdog that makes Quit always quit (PERC-0099)."""

from __future__ import annotations

import threading

import pytest

from perch import __main__ as perch_main


def test_watchdog_forces_exit_when_shutdown_overruns(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A shutdown that hung left Perch running, invisible, after Quit."""
    exited = threading.Event()
    monkeypatch.setattr("perch.__main__.os._exit", lambda _code: exited.set())
    perch_main.arm_exit_watchdog(0.05)
    assert exited.wait(2.0)


def test_cancelled_watchdog_does_not_fire(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    exited = threading.Event()
    monkeypatch.setattr("perch.__main__.os._exit", lambda _code: exited.set())
    perch_main.arm_exit_watchdog(0.2).cancel()
    assert not exited.wait(0.5)
