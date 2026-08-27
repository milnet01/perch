"""Unit tests for the first-run setup wizard.

Contract: ``docs/08-ui.md`` §First-run setup wizard.

The badge logic for rows 1 and 3 is pure, so it is exercised with no live
desktop — the same discipline the tray tests use. The wizard itself is
driven by stubbing ``SetupWizard.exec``: the pytest-qt idiom in
``tests/ui/test_dialog.py`` forbids a real ``exec()``, which would block
the test thread.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

import pytest
import tomlkit

from perch import autostart as autostart_module
from perch.backend.base import WindowBackend
from perch.backend.hyprland.backend import HyprlandBackend
from perch.backend.kwin.backend import KWinBackend
from perch.backend.mock import MockBackend
from perch.backend.mutter.backend import MutterBackend
from perch.backend.sway.backend import SwayBackend
from perch.backend.x11.backend import X11Backend
from perch.config.schema import Config, GeneralSettings
from perch.config.writer import load_document
from perch.ui import onboarding
from perch.ui.onboarding import (
    BACKEND_LABELS,
    BADGE_OFF,
    BADGE_OK,
    BADGE_WARN,
    SetupWizard,
    backend_label,
    check_autostart,
    check_compositor,
    check_tray,
    run_setup_wizard,
)

if TYPE_CHECKING:
    from pytestqt.qtbot import QtBot

#: Every backend Perch ships that can actually drive a compositor.
REAL_BACKENDS = [
    KWinBackend,
    MutterBackend,
    SwayBackend,
    HyprlandBackend,
    X11Backend,
]


# ── Row 1: tray ──────────────────────────────────────────────────────────────


def test_tray_row_is_ok_when_a_host_is_present() -> None:
    assert check_tray(have_host=True, gnome=False).badge == BADGE_OK


def test_tray_row_on_gnome_wayland_offers_the_extension() -> None:
    result = check_tray(have_host=False, gnome=True)
    assert result.badge == BADGE_WARN
    # Same copy as the standalone hint, via the shared helper, so the two
    # surfaces cannot drift.
    assert onboarding.appindicator_guidance() in result.detail
    assert onboarding.APPINDICATOR_EXTENSION_URL in result.detail


def test_tray_row_elsewhere_points_at_the_settings_command() -> None:
    result = check_tray(have_host=False, gnome=False)
    assert result.badge == BADGE_WARN
    assert "perch --settings" in result.detail
    # The AppIndicator guidance is GNOME-specific — offering it on KDE or
    # Xfce would send the user after an extension that does not apply.
    assert "AppIndicator" not in result.detail


# ── Row 2: autostart is a preference, not a check ────────────────────────────


@pytest.mark.parametrize(
    ("enabled", "expected"), [(True, BADGE_OK), (False, BADGE_OFF)]
)
def test_autostart_row_is_never_a_warning(enabled: bool, expected: str) -> None:
    result = check_autostart(enabled=enabled)
    assert result.badge == expected
    assert result.badge != BADGE_WARN


# ── Row 3: compositor ────────────────────────────────────────────────────────


def test_every_real_backend_has_exactly_one_label() -> None:
    """A new backend without a label would silently read as limited mode."""
    assert {cls.__name__ for cls in REAL_BACKENDS} == set(BACKEND_LABELS)


def test_compositor_row_names_the_backend() -> None:
    # Built by name rather than imported: the map is keyed on the class
    # name, and this makes that the thing under test.
    stub = cast(WindowBackend, type("KWinBackend", (), {})())
    result = check_compositor(stub)
    assert result.badge == BADGE_OK
    assert result.detail == "KWin / Plasma"


def test_compositor_row_warns_on_the_mock_backend() -> None:
    assert backend_label(MockBackend()) is None
    result = check_compositor(MockBackend())
    assert result.badge == BADGE_WARN
    assert "limited mode" in result.detail


def test_compositor_row_warns_when_there_is_no_backend() -> None:
    assert check_compositor(None).badge == BADGE_WARN


# ── The wizard's persistence contract ────────────────────────────────────────


def _seed(tmp_path: Path, *, start_at_login: bool) -> Path:
    path = tmp_path / "config.toml"
    path.write_text(
        "schema_version = 1\n\n"
        "[general]\n"
        f"start_at_login = {str(start_at_login).lower()}\n",
        encoding="utf-8",
    )
    return path


def _run(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    *,
    accepted: bool,
    checkbox: bool | None = None,
    start_at_login: bool = True,
) -> tuple[Any, list[bool], Path]:
    """Drive one wizard run without ever showing it."""
    path = _seed(tmp_path, start_at_login=start_at_login)
    synced: list[bool] = []
    monkeypatch.setattr(autostart_module, "sync", synced.append)

    def fake_exec(self: SetupWizard) -> int:
        if checkbox is not None:
            self.health.start_at_login.setChecked(checkbox)
        return 1 if accepted else 0

    monkeypatch.setattr(SetupWizard, "exec", fake_exec)

    def save(target: Path, document: Any) -> None:
        target.write_text(tomlkit.dumps(document), encoding="utf-8")

    outcome = run_setup_wizard(
        Config(general=GeneralSettings(start_at_login=start_at_login)),
        None,
        None,
        config_path=path,
        have_host=True,
        gnome=False,
        load_document_callback=load_document,
        save_callback=save,
    )
    return outcome, synced, path


@pytest.mark.parametrize("accepted", [True, False])
def test_every_exit_marks_onboarding_completed(
    qtbot: QtBot, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, accepted: bool
) -> None:
    """Finish, Cancel and window-close alike — or it reappears every launch."""
    outcome, _synced, path = _run(monkeypatch, tmp_path, accepted=accepted)
    assert outcome.config.general.onboarding_completed is True
    written = tomlkit.parse(path.read_text(encoding="utf-8"))
    assert written["general"]["onboarding_completed"] is True


def test_finish_persists_the_checkbox_and_applies_it(
    qtbot: QtBot, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    outcome, synced, path = _run(
        monkeypatch, tmp_path, accepted=True, checkbox=False, start_at_login=True
    )
    # Persisted, not merely synced: sync_from_config reconciles from config
    # at every startup, so writing the old value back would revert it.
    assert outcome.config.general.start_at_login is False
    written = tomlkit.parse(path.read_text(encoding="utf-8"))
    assert written["general"]["start_at_login"] is False
    assert synced == [False]


def test_cancel_drops_the_checkbox_and_touches_no_system_setting(
    qtbot: QtBot, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    outcome, synced, path = _run(
        monkeypatch, tmp_path, accepted=False, checkbox=False, start_at_login=True
    )
    assert outcome.config.general.start_at_login is True
    written = tomlkit.parse(path.read_text(encoding="utf-8"))
    assert written["general"]["start_at_login"] is True
    assert synced == []


def test_show_config_dialog_only_on_finish(
    qtbot: QtBot, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    def tick(self: SetupWizard) -> int:
        self.done_page.show_config.setChecked(True)
        return 0  # rejected

    monkeypatch.setattr(autostart_module, "sync", lambda _enabled: None)
    monkeypatch.setattr(SetupWizard, "exec", tick)

    def save(target: Path, document: Any) -> None:
        target.write_text(tomlkit.dumps(document), encoding="utf-8")

    outcome = run_setup_wizard(
        Config(),
        None,
        None,
        config_path=_seed(tmp_path, start_at_login=True),
        have_host=True,
        gnome=False,
        load_document_callback=load_document,
        save_callback=save,
    )
    assert outcome.show_config_dialog is False


def test_a_failed_write_does_not_stop_perch_starting(
    qtbot: QtBot, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The wizard runs again next launch — the benign failure of the two."""
    monkeypatch.setattr(autostart_module, "sync", lambda _enabled: None)
    monkeypatch.setattr(SetupWizard, "exec", lambda self: 1)

    def explode(_path: Path, _document: Any) -> None:
        raise OSError("disk full")

    outcome = run_setup_wizard(
        Config(),
        None,
        None,
        config_path=_seed(tmp_path, start_at_login=True),
        have_host=True,
        gnome=False,
        load_document_callback=load_document,
        save_callback=explode,
    )
    assert outcome.accepted is True
