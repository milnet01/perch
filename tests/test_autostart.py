"""Autostart (XDG .desktop + Flatpak Background portal)."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import pytest

from perch import autostart
from perch.config.schema import Config, GeneralSettings


def _conf(start_at_login: bool) -> Config:
    return Config(general=GeneralSettings(start_at_login=start_at_login))


# ── XDG probe + file lifecycle ───────────────────────────────────────────────


def test_autostart_file_honours_xdg_config_home(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "cfg"))
    assert autostart.autostart_dir() == tmp_path / "cfg" / "autostart"
    assert (
        autostart.autostart_file()
        == tmp_path / "cfg" / "autostart" / "io.github.milnet01.Perch.desktop"
    )


def test_autostart_file_default_home_fallback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))
    assert autostart.autostart_dir() == tmp_path / ".config" / "autostart"


def test_xdg_enable_writes_desktop_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    autostart.xdg_enable()
    path = autostart.autostart_file()
    content = path.read_text(encoding="utf-8")
    assert "[Desktop Entry]" in content
    assert "Exec=perch" in content
    assert "X-GNOME-Autostart-enabled=true" in content
    assert autostart.xdg_is_enabled()


def test_xdg_enable_is_idempotent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    autostart.xdg_enable()
    autostart.xdg_enable()
    # No exception, still exactly one file with the expected content.
    assert autostart.xdg_is_enabled()


def test_xdg_disable_removes_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    autostart.xdg_enable()
    autostart.xdg_disable()
    assert not autostart.autostart_file().exists()
    assert not autostart.xdg_is_enabled()


def test_xdg_disable_missing_file_is_no_op(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    # No prior enable — disable should swallow the FileNotFoundError.
    autostart.xdg_disable()
    assert not autostart.autostart_file().exists()


def test_hidden_entry_reports_disabled(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Freedesktop §Hidden: Hidden=true means "pretend I'm not here"."""
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    path = autostart.autostart_file()
    path.parent.mkdir(parents=True)
    path.write_text(
        "[Desktop Entry]\nType=Application\nExec=perch\nHidden=true\n",
        encoding="utf-8",
    )
    assert not autostart.xdg_is_enabled()


# ── sync() façade ────────────────────────────────────────────────────────────


def test_sync_enabled_xdg(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    autostart.sync(True, flatpak=False)
    assert autostart.xdg_is_enabled()


def test_sync_disabled_xdg(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    autostart.xdg_enable()
    autostart.sync(False, flatpak=False)
    assert not autostart.xdg_is_enabled()


def test_sync_from_config_enabled(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    # Patch is_flatpak to False so we don't hit the portal path from tests.
    monkeypatch.setattr(autostart, "is_flatpak", lambda: False)
    autostart.sync_from_config(_conf(start_at_login=True))
    assert autostart.xdg_is_enabled()


def test_sync_from_config_disabled(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    monkeypatch.setattr(autostart, "is_flatpak", lambda: False)
    autostart.xdg_enable()
    autostart.sync_from_config(_conf(start_at_login=False))
    assert not autostart.xdg_is_enabled()


# ── is_flatpak probe ─────────────────────────────────────────────────────────


def test_is_flatpak_false_on_dev_host() -> None:
    # /.flatpak-info is never present on a host — be extra defensive if
    # someone runs tests inside a Flatpak sandbox (skip).
    if Path("/.flatpak-info").is_file():
        pytest.skip("running inside a Flatpak sandbox")
    assert not autostart.is_flatpak()


# ── Portal path (mocked) ─────────────────────────────────────────────────────


class _FakePortal:
    """Records calls to RequestBackground and returns a scripted result."""

    def __init__(self, *, granted: bool = True) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self._granted = granted

    async def request_background(
        self, parent_window: str, options: dict[str, Any]
    ) -> dict[str, Any]:
        self.calls.append((parent_window, options))
        return {"autostart": self._granted}


def test_portal_set_autostart_enabled() -> None:
    fake = _FakePortal()
    asyncio.run(autostart.portal_set_autostart(True, factory=lambda: fake))
    assert len(fake.calls) == 1
    _, options = fake.calls[0]
    assert options["autostart"] == ("b", True)
    assert options["commandline"] == ("as", ["perch"])


def test_portal_set_autostart_disabled_omits_commandline() -> None:
    fake = _FakePortal()
    asyncio.run(autostart.portal_set_autostart(False, factory=lambda: fake))
    _, options = fake.calls[0]
    assert options["autostart"] == ("b", False)
    # commandline is only meaningful when enabling — disabling should not
    # include it (portal ignores it, but we keep the payload minimal).
    assert "commandline" not in options


def test_portal_swallows_exceptions() -> None:
    class _ExplodingPortal:
        async def request_background(
            self, parent_window: str, options: dict[str, Any]
        ) -> dict[str, Any]:
            raise RuntimeError("portal unreachable")

    # A failing portal call must not crash autostart.sync — the user's
    # config save should still succeed.
    asyncio.run(
        autostart.portal_set_autostart(True, factory=lambda: _ExplodingPortal())
    )


def test_sync_flatpak_routes_to_portal(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _FakePortal()
    autostart.sync(True, flatpak=True, portal_factory=lambda: fake)
    assert len(fake.calls) == 1
