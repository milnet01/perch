"""Atomic-write behaviour and backup rotation."""

from __future__ import annotations

from pathlib import Path

import pytest

from perch.config.writer import atomic_write


def test_atomic_write_creates_file(tmp_path: Path) -> None:
    target = tmp_path / "sub" / "out.toml"
    atomic_write(target, "hello = 1\n")
    assert target.read_text(encoding="utf-8") == "hello = 1\n"
    # Tmp and bak must not linger after a clean write.
    assert not target.with_suffix(target.suffix + ".tmp").exists()


def test_atomic_write_rotates_previous_to_bak(tmp_path: Path) -> None:
    target = tmp_path / "out.toml"
    atomic_write(target, "first = 1\n")
    atomic_write(target, "second = 2\n")

    assert target.read_text(encoding="utf-8") == "second = 2\n"
    bak = target.with_suffix(target.suffix + ".bak")
    assert bak.exists()
    assert bak.read_text(encoding="utf-8") == "first = 1\n"


def test_atomic_write_overwrites_existing_backup(tmp_path: Path) -> None:
    target = tmp_path / "out.toml"
    bak = target.with_suffix(target.suffix + ".bak")
    bak.write_text("stale\n", encoding="utf-8")
    target.write_text("primary\n", encoding="utf-8")

    atomic_write(target, "new\n")

    assert target.read_text(encoding="utf-8") == "new\n"
    assert bak.read_text(encoding="utf-8") == "primary\n"


def test_atomic_write_leaves_no_tmp_on_success(tmp_path: Path) -> None:
    target = tmp_path / "out.toml"
    atomic_write(target, "x = 1\n")
    stray = list(tmp_path.glob("*.tmp"))
    assert stray == [], f"unexpected temp files: {stray}"


def test_atomic_write_is_byte_exact_utf8(tmp_path: Path) -> None:
    target = tmp_path / "out.toml"
    payload = 'title = "Perch \u2728 bird"\n'
    atomic_write(target, payload)
    assert target.read_bytes() == payload.encode("utf-8")


@pytest.mark.parametrize("suffix", ["", ".toml", ".json"])
def test_atomic_write_works_with_various_suffixes(tmp_path: Path, suffix: str) -> None:
    target = tmp_path / f"out{suffix}"
    atomic_write(target, "data\n")
    assert target.read_text(encoding="utf-8") == "data\n"
