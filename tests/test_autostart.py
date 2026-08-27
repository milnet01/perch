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


class _FakeResponseSignal:
    """Stands in for an sdbus signal descriptor: ``.catch()`` yields once."""

    def __init__(self, payload: tuple[int, dict[str, Any]]) -> None:
        self._payload = payload

    def catch(self) -> Any:
        async def _iter() -> Any:
            yield self._payload

        return _iter()


class _FakePortal:
    """Records RequestBackground calls and scripts the Request's Response.

    Doubles as the ``request_factory``: calling the instance with a path
    hands back the same object, so a test builds one fake, not two.
    """

    #: Shape the portal really uses — the value must never be treated as
    #: the result dict, which is the defect PERC-0037 fixed.
    REQUEST_PATH = "/org/freedesktop/portal/desktop/request/1_1/perch"

    def __init__(self, *, granted: bool = True, response_code: int = 0) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.subscribed: list[str] = []
        self._granted = granted
        self._response_code = response_code

    async def request_background(
        self, parent_window: str, options: dict[str, Any]
    ) -> str:
        self.calls.append((parent_window, options))
        return self.REQUEST_PATH

    def __call__(self, path: str) -> _FakePortal:
        self.subscribed.append(path)
        return self

    @property
    def response(self) -> _FakeResponseSignal:
        # a{sv} — the value arrives variant-wrapped, as it does on the bus.
        return _FakeResponseSignal(
            (self._response_code, {"autostart": ("b", self._granted)})
        )


def test_portal_set_autostart_enabled() -> None:
    fake = _FakePortal()
    granted = asyncio.run(
        autostart.portal_set_autostart(
            True, factory=lambda: fake, request_factory=fake
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
            False, factory=lambda: fake, request_factory=fake
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
                True, factory=lambda: _ExplodingPortal()
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
    granted = asyncio.run(
        autostart.portal_set_autostart(
            True, factory=lambda: fake, request_factory=fake
        )
    )
    assert granted is True
    # The Response was awaited on the path the portal handed back.
    assert fake.subscribed == [_FakePortal.REQUEST_PATH]


def test_portal_denied_response_is_not_granted() -> None:
    fake = _FakePortal(granted=False)
    assert (
        asyncio.run(
            autostart.portal_set_autostart(
                True, factory=lambda: fake, request_factory=fake
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
                True, factory=lambda: fake, request_factory=fake
            )
        )
        is False
    )


def test_portal_response_timeout_is_not_granted() -> None:
    class _SilentRequest:
        @property
        def response(self) -> Any:
            class _Never:
                def catch(self) -> Any:
                    async def _iter() -> Any:
                        await asyncio.Event().wait()
                        yield (0, {})

                    return _iter()

            return _Never()

    fake = _FakePortal()
    assert (
        asyncio.run(
            autostart.portal_set_autostart(
                True,
                factory=lambda: fake,
                request_factory=lambda _path: _SilentRequest(),
                timeout_s=0.01,
            )
        )
        is False
    )


def test_sync_flatpak_routes_to_portal(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _FakePortal()
    autostart.sync(
        True,
        flatpak=True,
        portal_factory=lambda: fake,
        portal_request_factory=fake,
    )
    assert len(fake.calls) == 1
