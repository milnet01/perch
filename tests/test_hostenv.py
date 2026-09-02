"""Host-program environment restoration (``perch.hostenv``).

Regression cover for the AppImage leak: ``entrypoint.sh`` exports
``LD_LIBRARY_PATH`` pointing at the bundled AlmaLinux 8 libraries, and every
child inherits it, so a browser or file manager Perch spawns was resolved
against those instead of its own.
"""

from __future__ import annotations

import os

import pytest

from perch import hostenv


def test_no_marker_means_inherit(monkeypatch: pytest.MonkeyPatch) -> None:
    """Outside an AppImage nothing was overwritten, so nothing is undone."""
    monkeypatch.delenv(hostenv.HOST_PATH_VAR, raising=False)
    monkeypatch.setenv("LD_LIBRARY_PATH", "/host/libs")
    assert hostenv.host_env() is None


def test_marker_restores_the_host_value(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(hostenv.HOST_PATH_VAR, "/host/libs")
    monkeypatch.setenv("LD_LIBRARY_PATH", "/appdir/usr/lib/perch-runtime-libs")
    env = hostenv.host_env()
    assert env is not None
    assert env["LD_LIBRARY_PATH"] == "/host/libs"
    assert hostenv.HOST_PATH_VAR not in env


def test_empty_marker_drops_the_variable(monkeypatch: pytest.MonkeyPatch) -> None:
    """The host had no LD_LIBRARY_PATH, so the child must not get one."""
    monkeypatch.setenv(hostenv.HOST_PATH_VAR, "")
    monkeypatch.setenv("LD_LIBRARY_PATH", "/appdir/usr/lib/perch-runtime-libs")
    env = hostenv.host_env()
    assert env is not None
    assert "LD_LIBRARY_PATH" not in env


def test_context_manager_swaps_and_restores(monkeypatch: pytest.MonkeyPatch) -> None:
    """Qt spawns on our behalf, so the swap has to reach os.environ."""
    monkeypatch.setenv(hostenv.HOST_PATH_VAR, "/host/libs")
    monkeypatch.setenv("LD_LIBRARY_PATH", "/appdir/usr/lib/perch-runtime-libs")
    with hostenv.host_environment():
        assert os.environ["LD_LIBRARY_PATH"] == "/host/libs"
    assert os.environ["LD_LIBRARY_PATH"] == "/appdir/usr/lib/perch-runtime-libs"


def test_context_manager_restores_after_an_exception(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(hostenv.HOST_PATH_VAR, "/host/libs")
    monkeypatch.setenv("LD_LIBRARY_PATH", "/appdir/usr/lib/perch-runtime-libs")
    try:
        with hostenv.host_environment():
            raise RuntimeError("boom")
    except RuntimeError:
        pass
    assert os.environ["LD_LIBRARY_PATH"] == "/appdir/usr/lib/perch-runtime-libs"


def test_context_manager_is_a_noop_outside_an_appimage(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(hostenv.HOST_PATH_VAR, raising=False)
    monkeypatch.setenv("LD_LIBRARY_PATH", "/host/libs")
    with hostenv.host_environment():
        assert os.environ["LD_LIBRARY_PATH"] == "/host/libs"
    assert os.environ["LD_LIBRARY_PATH"] == "/host/libs"
