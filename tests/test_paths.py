"""XDG path resolution."""

from __future__ import annotations

from pathlib import Path

import pytest

from perch import paths


def test_honours_xdg_config_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "cfg"))
    assert paths.config_dir() == tmp_path / "cfg" / "perch"
    assert paths.config_file() == tmp_path / "cfg" / "perch" / "config.toml"


def test_falls_back_to_default_when_env_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))
    assert paths.config_dir() == tmp_path / ".config" / "perch"


def test_empty_env_treated_as_unset(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Per XDG spec: an empty-string env var is equivalent to unset."""
    monkeypatch.setenv("XDG_STATE_HOME", "")
    monkeypatch.setenv("HOME", str(tmp_path))
    assert paths.state_dir() == tmp_path / ".local" / "state" / "perch"


def test_ensure_dir_creates_nested(tmp_path: Path) -> None:
    target = tmp_path / "a" / "b" / "c"
    paths.ensure_dir(target)
    assert target.is_dir()
