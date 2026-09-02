"""Tests for the hardening in PERC-0050.

Each finding calibrates low against `docs/security-standards.md`, which
puts a same-UID attacker out of scope. They are locked anyway because the
guards are cheap and easy to undo by accident.
"""

from __future__ import annotations

import os
import stat
from pathlib import Path

import pytest

from perch import paths
from perch.config.schema import SchemaError
from perch.config.writer import atomic_write


# ── Directory modes ───────────────────────────────────────────────────────
def test_ensure_dir_creates_owner_only(tmp_path: Path) -> None:
    created = paths.ensure_dir(tmp_path / "state" / "perch")
    assert stat.S_IMODE(created.stat().st_mode) == 0o700


def test_ensure_dir_tightens_an_existing_directory(tmp_path: Path) -> None:
    """An install predating this was created with the umask default."""
    existing = tmp_path / "perch"
    existing.mkdir(mode=0o755)
    os.chmod(existing, 0o755)

    paths.ensure_dir(existing)

    assert stat.S_IMODE(existing.stat().st_mode) == 0o700


# ── Atomic write ──────────────────────────────────────────────────────────
def test_atomic_write_refuses_a_symlinked_temp_file(tmp_path: Path) -> None:
    """The .tmp name is predictable and its directory is reachable, so a
    symlink planted there would redirect the write (CWE-59)."""
    target = tmp_path / "config.toml"
    target.write_text("schema_version = 1\n", encoding="utf-8")
    victim = tmp_path / "victim"
    victim.write_text("untouched", encoding="utf-8")
    (tmp_path / "config.toml.tmp").symlink_to(victim)

    with pytest.raises(OSError):
        atomic_write(target, "schema_version = 1\n# new\n")

    assert victim.read_text(encoding="utf-8") == "untouched"


# ── Import validates the bytes it will write ──────────────────────────────
def test_validate_text_checks_the_text_not_the_named_file(
    tmp_path: Path,
) -> None:
    """The import path holds the bytes it intends to write.

    Validating the path re-reads the file, so one that changed between the
    two reads was written without ever having been checked.
    """
    from perch.config.loader import validate_text

    source = tmp_path / "incoming.toml"
    source.write_text("schema_version = 1\n", encoding="utf-8")

    with pytest.raises(SchemaError):
        validate_text('schema_version = 1\n[general]\ntheme = "nope"\n', str(source))


def test_validate_text_accepts_a_good_document(tmp_path: Path) -> None:
    from perch.config.loader import validate_text

    config = validate_text(
        'schema_version = 1\n[general]\ntheme = "dark"\n', "<test>"
    )
    assert config.general.theme == "dark"
