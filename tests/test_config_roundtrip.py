"""tomlkit round-trip fixture — BLOCKS M1 exit.

Per ``docs/02-state-format.md`` §Read / write split and Phase 2.5 research
(``docs/11-roadmap.md``), tomlkit has a known footgun where deep inline-table
rewrites can drop mid-table comments. Silently dropping a user's comments is
treated as an unacceptable trust violation, so this fixture enforces it.

The fixture exercises the shapes Perch actually writes: top-level comments,
``[general]`` with inline comments, ``[exclusions]``, nested ``[snaps.*]``
tables, ``[[rules]]`` arrays of tables, ``[layouts.<name>.windows]`` double
nesting, and ``[[profiles]]``.
"""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Any

import pytest

from perch.config import load_or_create
from perch.config.writer import load_document, write_document

FIXTURE = Path(__file__).parent / "fixtures" / "commented_config.toml"


@pytest.fixture
def fixture_copy(tmp_path: Path) -> Path:
    target = tmp_path / "config.toml"
    target.write_text(FIXTURE.read_text(encoding="utf-8"), encoding="utf-8")
    return target


def test_untouched_roundtrip_preserves_every_comment(fixture_copy: Path) -> None:
    """Read fixture with tomlkit, write straight back — output == input byte-for-byte."""
    original = fixture_copy.read_text(encoding="utf-8")
    document = load_document(fixture_copy)
    write_document(fixture_copy, document)
    assert fixture_copy.read_text(encoding="utf-8") == original


@pytest.mark.parametrize(
    ("path", "new_value"),
    [
        (("general", "theme"), "light"),
        (("general", "start_at_login"), False),
    ],
)
def test_mutated_roundtrip_preserves_comments(
    fixture_copy: Path, path: tuple[str, ...], new_value: object
) -> None:
    """Edit one value deep in the document — all comments must still be present."""
    original = fixture_copy.read_text(encoding="utf-8")
    comment_lines = [line for line in original.splitlines() if line.lstrip().startswith("#")]
    inline_comments = [line for line in original.splitlines() if " # " in line]

    document = load_document(fixture_copy)
    node: Any = document
    for key in path[:-1]:
        node = node[key]
    node[path[-1]] = new_value
    write_document(fixture_copy, document)

    rewritten = fixture_copy.read_text(encoding="utf-8")
    for comment in comment_lines:
        assert comment in rewritten, f"dropped standalone comment: {comment!r}"
    for line in inline_comments:
        tail = line.split(" # ", 1)[1]
        assert f"# {tail}" in rewritten, f"dropped inline comment: {tail!r}"

    # Confirm the edit actually landed.
    reparsed = tomllib.loads(rewritten)
    current = reparsed
    for key in path[:-1]:
        current = current[key]
    assert current[path[-1]] == new_value


def test_fixture_loads_through_schema_validator(fixture_copy: Path) -> None:
    """The fixture must be valid against the schema (so round-tripping means something)."""
    config = load_or_create(config_path=fixture_copy)
    assert config.general.theme == "dark"
    assert len(config.rules) == 1
    assert "coding" in config.layouts


def test_default_config_roundtrips(tmp_path: Path) -> None:
    """The defaults Perch seeds must themselves round-trip without loss."""
    target = tmp_path / "config.toml"
    load_or_create(config_path=target)
    original = target.read_text(encoding="utf-8")

    document = load_document(target)
    write_document(target, document)
    assert target.read_text(encoding="utf-8") == original
