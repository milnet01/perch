#!/usr/bin/env python3
"""Prove every version-bearing file carries the version pyproject.toml declares.

docs/versioning-release-standards.md makes the lockstep an invariant: editing
one version-bearing file and forgetting another is the failure the release
recipe exists to prevent. Until now nothing enforced it -- the old recipe
carried no post_check at all, so a bump that silently missed a file produced a
release whose RPM, PKGBUILD and AppImage download link disagreed.

The file list is NOT duplicated here. It is read from .claude/bump.json, which
is the single declaration of what must move together; a second hand-maintained
list is a mirror, and a drifted mirror reports green for a release that will
ship wrong. Adding a file to the recipe is therefore enough to put it under
this check.

Two questions per recipe entry, both mechanical:

  1. Is the declared post-bump text present at all? A file the bump skipped
     fails here.
  2. Does EVERY line of that file matching the entry's shape carry the
     canonical version? This is the half a presence check misses: README.md
     names the AppImage three times, and a bump that rewrote two of them
     passes question 1 while shipping a dead download link.

Question 2 works by turning the entry's `replace` template into a regex --
the literal text around {NEW} is escaped, {NEW} itself becomes a version
capture group. So it fires only on the shapes the recipe already declares and
cannot invent drift from an unrelated version string elsewhere in the file.

An entry whose `replace` carries {TODAY} is REPORTED AS UNCHECKED rather than
guessed at: today's date need not be the release date, and a check that
quietly assumes otherwise is worse than one that says it did not run.

Usage: python tools/version_lockstep_check.py   (exit 0 clean, 1 with findings)
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RECIPE = ROOT / ".claude/bump.json"

VERSION_RE = r"(\d+\.\d+\.\d+)"
DATE_RE = r"\d{4}-\d{2}-\d{2}"


def canonical_version(recipe: dict) -> str:
    """Read the version every other file must agree with."""
    source = ROOT / recipe["version_source"]
    text = source.read_text(encoding="utf-8")
    match = re.search(recipe["version_pattern"], text, re.MULTILINE)
    if not match:
        sys.exit(
            f"FAIL  cannot read the version from {recipe['version_source']} "
            f"using version_pattern {recipe['version_pattern']!r}"
        )
    return match.group(1)


def shape_regex(replace: str) -> re.Pattern[str] | None:
    """Turn a `replace` template into the regex matching its whole family.

    Literal text is escaped; {NEW} becomes a version capture group. Returns
    None where the template carries {TODAY}, which cannot be verified.
    """
    if "{TODAY}" in replace:
        return None
    parts = [re.escape(p) for p in replace.split("{NEW}")]
    return re.compile(VERSION_RE.join(parts))


def main() -> int:
    recipe = json.loads(RECIPE.read_text(encoding="utf-8"))
    version = canonical_version(recipe)

    findings: list[str] = []
    unchecked: list[str] = []
    checked = 0

    for entry in recipe["files"]:
        path = entry["path"]
        target = ROOT / path
        if not target.exists():
            findings.append(f"{path}: listed in bump.json but does not exist")
            continue

        text = target.read_text(encoding="utf-8")
        expected = entry["replace"].replace("{NEW}", version)

        pattern = shape_regex(entry["replace"])
        if pattern is None:
            unchecked.append(f"{path}: `replace` carries {{TODAY}} — not verified")
            continue

        # Question 1: did the bump write the new text at all?
        if expected not in text:
            findings.append(f"{path}: expected {expected!r}, not found")
            continue

        # Question 2: does every line of this shape carry the same version?
        stale = sorted({m.group(1) for m in pattern.finditer(text)} - {version})
        if stale:
            findings.append(
                f"{path}: {', '.join(stale)} still present in a line matching "
                f"this entry's shape (canonical is {version})"
            )
            continue

        checked += 1

    print(f"version lockstep: canonical {version} from {recipe['version_source']}")
    for note in unchecked:
        print(f"  SKIP  {note}")
    if not findings:
        tail = f", {len(unchecked)} unchecked" if unchecked else ""
        print(f"  OK    {checked} file(s) agree{tail}")
        return 0
    for finding in findings:
        print(f"  FAIL  {finding}")
    print(f"\n{len(findings)} version-lockstep finding(s).")
    return 1


if __name__ == "__main__":
    sys.exit(main())
