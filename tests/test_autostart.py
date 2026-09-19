"""Autostart (XDG .desktop + Flatpak Background portal)."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import pytest

from perch import autostart
from perch.config.schema import Config, GeneralSettings
from perch.portal import request_path


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


_SENDER = ":1.1"


class _FakeWaiter:
    def __init__(self) -> None:
        self.queue: asyncio.Queue[tuple[int, dict[str, Any]]] = asyncio.Queue()
        self.closed = False

    async def wait(self, timeout_s: float) -> tuple[int, dict[str, Any]] | None:
        try:
            return await asyncio.wait_for(self.queue.get(), timeout=timeout_s)
        except TimeoutError:
            return None

    def close(self) -> None:
        self.closed = True


class _FakePortal:
    """Records RequestBackground calls and answers the way a real portal can.

    Once a permission is stored the Response is emitted during the call,
    at the path derived from the caller's handle_token, and reaches only
    a subscription already in place. ``silent`` sends no Response at all.
    """

    def __init__(
        self, *, granted: bool = True, response_code: int = 0, silent: bool = False
    ) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.events: list[str] = []
        self._subscriptions: dict[str, _FakeWaiter] = {}
        self._granted = granted
        self._response_code = response_code
        self._silent = silent

    async def sender(self) -> str:
        return _SENDER

    async def subscribe(self, path: str) -> _FakeWaiter:
        self.events.append(f"subscribe {path}")
        waiter = _FakeWaiter()
        self._subscriptions[path] = waiter
        return waiter

    async def request_background(
        self, parent_window: str, options: dict[str, Any]
    ) -> str:
        self.calls.append((parent_window, options))
        path = request_path(_SENDER, options["handle_token"][1])
        self.events.append(f"call {path}")
        waiter = self._subscriptions.get(path)
        if waiter is not None and not self._silent:
            # a{sv} — the value arrives variant-wrapped, as it does on the bus.
            waiter.queue.put_nowait(
                (self._response_code, {"autostart": ("b", self._granted)})
            )
        return path

    def seams(self) -> dict[str, Any]:
        return {
            "factory": lambda: self,
            "subscriber": self.subscribe,
            "sender": self.sender,
        }


def test_portal_set_autostart_enabled() -> None:
    fake = _FakePortal()
    granted = asyncio.run(
        autostart.portal_set_autostart(
            True, **fake.seams()
        )
    )
    assert granted is True
    assert len(fake.calls) == 1
    _, options = fake.calls[0]
    assert options["autostart"] == ("b", True)
    assert options["commandline"] == ("as", ["perch"])


def test_portal_set_autostart_disabled_omits_commandline() -> None:
    fake = _FakePortal()
    asyncio.run(
        autostart.portal_set_autostart(
            False, **fake.seams()
        )
    )
    _, options = fake.calls[0]
    assert options["autostart"] == ("b", False)
    # commandline is only meaningful when enabling — disabling should not
    # include it (portal ignores it, but we keep the payload minimal).
    assert "commandline" not in options


def test_portal_swallows_exceptions() -> None:
    class _ExplodingPortal:
        async def request_background(
            self, parent_window: str, options: dict[str, Any]
        ) -> str:
            raise RuntimeError("portal unreachable")

    # A failing portal call must not crash autostart.sync — the user's
    # config save should still succeed.
    assert (
        asyncio.run(
            autostart.portal_set_autostart(
                True,
                factory=lambda: _ExplodingPortal(),
                sender=_FakePortal().sender,
            )
        )
        is False
    )


def test_portal_reads_the_response_not_the_request_path() -> None:
    """RequestBackground returns a Request path, not the result.

    The outcome arrives on that Request's ``Response`` signal. Reading the
    return value as a mapping raises ``AttributeError`` on a ``str`` — the
    live-Flatpak failure PERC-0037 records.
    """
    fake = _FakePortal(granted=True)
    granted = asyncio.run(autostart.portal_set_autostart(True, **fake.seams()))
    assert granted is True


def test_portal_subscribes_before_calling() -> None:
    """PERC-0064: once a permission is stored the Response can arrive
    before RequestBackground returns; subscribing afterwards lost it and
    the task waited out the whole timeout, logging failure for a toggle
    that had worked."""
    fake = _FakePortal(granted=True)
    assert asyncio.run(autostart.portal_set_autostart(True, **fake.seams())) is True
    sub, call = fake.events
    assert sub.startswith("subscribe ")
    assert call == "call " + sub.removeprefix("subscribe ")


def test_portal_denied_response_is_not_granted() -> None:
    fake = _FakePortal(granted=False)
    assert (
        asyncio.run(
            autostart.portal_set_autostart(
                True, **fake.seams()
            )
        )
        is False
    )


def test_portal_cancelled_request_is_not_granted() -> None:
    # response != 0 means the user dismissed the permission dialog; the
    # results dict is not authoritative then.
    fake = _FakePortal(granted=True, response_code=1)
    assert (
        asyncio.run(
            autostart.portal_set_autostart(
                True, **fake.seams()
            )
        )
        is False
    )


def test_portal_response_timeout_is_not_granted() -> None:
    fake = _FakePortal(silent=True)
    assert (
        asyncio.run(
            autostart.portal_set_autostart(True, **fake.seams(), timeout_s=0.01)
        )
        is False
    )


def test_sync_flatpak_routes_to_portal(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _FakePortal()
    autostart.sync(
        True,
        flatpak=True,
        portal_factory=lambda: fake,
        portal_subscriber=fake.subscribe,
        portal_sender=fake.sender,
    )
    assert len(fake.calls) == 1
