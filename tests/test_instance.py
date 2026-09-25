"""Single-instance guard (PERC-0049, docs/01-architecture.md §Why one process)."""

from __future__ import annotations

import shutil
import tempfile
from collections.abc import Iterator
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from perch import instance

if TYPE_CHECKING:
    from pytestqt.qtbot import QtBot


def test_a_second_holder_is_refused_until_the_first_releases(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
    first = instance.acquire_instance_lock()
    assert first is not None
    assert instance.acquire_instance_lock() is None
    first.unlock()
    again = instance.acquire_instance_lock()
    assert again is not None
    again.unlock()


def test_lock_lives_in_the_runtime_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
    assert instance.lock_path() == tmp_path / "perch.lock"


def test_a_relative_runtime_dir_falls_back_to_state(
    xdg_env: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("XDG_RUNTIME_DIR", "relative")
    assert instance.lock_path() == xdg_env / "state" / "perch" / "perch.lock"


def test_cli_refuses_to_start_a_second_copy(
    qapp: object,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    xdg_env: Path,
) -> None:
    del qapp, xdg_env
    from perch import __main__ as entry

    monkeypatch.setattr(instance, "acquire_instance_lock", lambda: None)

    def _must_not_run(**_kwargs: object) -> None:
        raise AssertionError("a second copy went on to start the app")

    # Without the guard cli() runs the whole app; fail fast instead of hanging.
    monkeypatch.setattr("perch.app.main", _must_not_run)
    assert entry.cli([]) == 1
    assert "already running" in capsys.readouterr().err


# ── PERC-0043: `perch --settings` reaches the running copy ──────────────────


@pytest.fixture
def short_runtime_dir(monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    """A runtime dir with a short path.

    A Unix socket path tops out near 108 bytes, and tmp_path under a long
    TMPDIR or --basetemp is longer than that, so listen() would fail for
    a reason that has nothing to do with Perch.
    """
    runtime = Path(tempfile.mkdtemp(prefix="perch-", dir="/tmp"))
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(runtime))
    try:
        yield runtime
    finally:
        shutil.rmtree(runtime, ignore_errors=True)


def test_a_settings_request_reaches_the_running_copy(
    qtbot: QtBot, short_runtime_dir: Path
) -> None:
    del short_runtime_dir
    channel = instance.InstanceChannel()
    assert channel.listen(), channel.error_string()
    got: list[bool] = []
    channel.settings_requested.connect(lambda: got.append(True))
    assert instance.request_settings()
    # waitUntil, not waitSignal: the request is sent before any wait
    # starts, and pytest-qt's waitSignal aborted the process in that shape.
    qtbot.waitUntil(lambda: bool(got), timeout=2000)


def test_no_running_copy_means_no_delivery(
    qapp: object, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    del qapp
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
    assert instance.request_settings(timeout_ms=200) is False


def test_cli_settings_hands_off_to_the_running_copy(
    qapp: object,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    xdg_env: Path,
) -> None:
    """docs/08 offers `perch --settings` as the way in when the tray is
    invisible; with a second copy refused, it has to open the first's
    window, not report "already running"."""
    del qapp, xdg_env
    from perch import __main__ as entry

    requests: list[bool] = []

    def _request() -> bool:
        requests.append(True)
        return True

    def _must_not_run(**_kwargs: object) -> None:
        raise AssertionError("a second copy went on to start the app")

    monkeypatch.setattr(instance, "acquire_instance_lock", lambda: None)
    monkeypatch.setattr(instance, "request_settings", _request)
    # Without the guard a regression past the lock check runs the whole
    # app and the suite hangs instead of failing.
    monkeypatch.setattr("perch.app.main", _must_not_run)
    assert entry.cli(["--settings"]) == 0
    assert requests == [True]
    assert "already running" not in capsys.readouterr().err
