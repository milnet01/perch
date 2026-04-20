"""CLI exit-code behaviour.

These drive ``perch.__main__.cli`` the same way ``[project.scripts]`` will at
install time. They exercise the three M1 exit-criteria paths:

* ``perch --version`` prints the version and exits 0.
* ``perch`` against a fresh XDG dir creates defaults and exits 0.
* ``perch`` against a malformed config without a backup exits non-zero and
  logs a pinpoint error.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from perch import __main__ as entry
from perch import __version__


def test_version_flag_prints_version_and_exits_zero(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as excinfo:
        entry.cli(["--version"])
    assert excinfo.value.code == 0
    captured = capsys.readouterr()
    assert __version__ in (captured.out + captured.err)


def test_fresh_xdg_creates_default_config(xdg_env: Path) -> None:
    exit_code = entry.cli([])
    assert exit_code == 0
    config_path = xdg_env / "config" / "perch" / "config.toml"
    assert config_path.exists()
    text = config_path.read_text(encoding="utf-8")
    assert "schema_version" in text
    assert "[general]" in text


def test_malformed_config_exits_nonzero(xdg_env: Path) -> None:
    config_path = xdg_env / "config" / "perch" / "config.toml"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text("not = valid [ toml", encoding="utf-8")

    exit_code = entry.cli([])
    assert exit_code == 1


def test_malformed_config_falls_back_to_backup(xdg_env: Path) -> None:
    config_dir = xdg_env / "config" / "perch"
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "config.toml").write_text("not = valid [ toml", encoding="utf-8")
    (config_dir / "config.toml.bak").write_text(
        'schema_version = 1\n[general]\ntheme = "light"\n', encoding="utf-8"
    )
    exit_code = entry.cli([])
    assert exit_code == 0
