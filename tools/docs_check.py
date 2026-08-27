#!/usr/bin/env python3
"""Mechanical documentation checks for the local and CI gates.

Two checks, both zero-judgement:

1. **Cross-references** — every relative Markdown link in the scanned set
   resolves to a file that exists, and every ``#anchor`` matches a heading
   in the target document.
2. **Drift** — a retired or forbidden string must not appear outside the
   documents that exist to record it.

This is the gate's half of ``/perch-docs-check``. That skill is the wider
scan: it also reads tense against the roadmap's milestone state, and judges
whether a swapped library named in prose is history or a live claim. Those
need a reader, so they are deliberately not here — a gate that needs
judgement is a gate that gets tuned until it passes. The swapped-library
grep is the worked example: every occurrence in this repo today is correct
rationale, so allow-listing them would leave the check vacuous.

Usage: python tools/docs_check.py   (exit 0 clean, 1 with findings)
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# The documents a reader is expected to navigate. ROADMAP.md is excluded:
# it is a generated render of the roadmap store (see CLAUDE.md), so a
# finding there is a store-content bug and is not fixable in the file.
SCANNED = [
    *sorted(ROOT.glob("docs/*.md")),
    ROOT / "README.md",
    ROOT / "CONTRIBUTING.md",
    ROOT / "CODE_OF_CONDUCT.md",
    ROOT / "CHANGELOG.md",
    ROOT / "CLAUDE.md",
]

# [text](target) — skip images, which carry the same shape behind a `!`.
LINK = re.compile(r"(?<!\!)\[[^\]]*\]\(([^)\s]+)\)")
HEADING = re.compile(r"^#{1,6}\s+(.*?)\s*$")
SKIP_SCHEMES = ("http://", "https://", "mailto:", "ftp://")


@dataclass(frozen=True)
class DriftRule:
    name: str
    pattern: re.Pattern[str]
    allowed: frozenset[str]
    why: str


DRIFT_RULES = (
    DriftRule(
        name="retired KWin scripting API (Plasma 5)",
        pattern=re.compile(r"\b(clientAdded|clientList|clientRemoved|clientActivated)\b"),
        allowed=frozenset({"docs/05-backend-kwin.md", "docs/11-roadmap.md"}),
        why="renamed in the Plasma 5 to 6 transition; only the KWin backend "
        "doc's comparison section and the research log may name them",
    ),
    DriftRule(
        name="pre-3.12 Python floor",
        pattern=re.compile(r"requires-python.*3\.11|python_requires.*3\.11|>= ?3\.11"),
        allowed=frozenset({"docs/coding-standards.md", "docs/contributing-dev-setup.md"}),
        why="Perch floors Python 3.12 (Phase 2.5 research); the two standards "
        "documents state that rule and so must quote the string",
    ),
)


def slug(heading: str) -> str:
    """GitHub's heading-to-anchor transform, near enough for a link check.

    Each whitespace character becomes one hyphen; runs are NOT collapsed.
    ``## v1.0.1 - Get it downloadable`` with an em dash anchors as
    ``v101--get-it-downloadable``, because the dropped dash leaves two
    spaces behind. Collapsing them reports a working link as broken.
    """
    text = re.sub(r"`|\*|_", "", heading.lower())
    text = re.sub(r"[^\w\s-]", "", text)
    return re.sub(r"\s", "-", text.strip())


def anchors(path: Path) -> set[str]:
    if path.suffix != ".md" or not path.is_file():
        return set()
    found = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        match = HEADING.match(line)
        if match:
            found.add(slug(match.group(1)))
    return found


def check_links(findings: list[str]) -> None:
    for doc in SCANNED:
        if not doc.is_file():
            continue
        rel = doc.relative_to(ROOT)
        for number, line in enumerate(doc.read_text(encoding="utf-8").splitlines(), 1):
            for target in LINK.findall(line):
                if target.startswith(SKIP_SCHEMES):
                    continue
                file_part, _, anchor = target.partition("#")
                if not file_part:  # same-document anchor
                    resolved = doc
                else:
                    resolved = (doc.parent / file_part).resolve()
                    if not resolved.exists():
                        findings.append(f"{rel}:{number}: link target missing — {target}")
                        continue
                if (
                    anchor
                    and resolved.suffix == ".md"
                    and slug(anchor) not in anchors(resolved)
                ):
                    findings.append(f"{rel}:{number}: anchor not a heading — {target}")


def check_drift(findings: list[str]) -> None:
    for rule in DRIFT_RULES:
        for doc in SCANNED:
            if not doc.is_file():
                continue
            rel = doc.relative_to(ROOT)
            if str(rel) in rule.allowed:
                continue
            for number, line in enumerate(doc.read_text(encoding="utf-8").splitlines(), 1):
                if rule.pattern.search(line):
                    findings.append(
                        f"{rel}:{number}: {rule.name} — {rule.why}\n      {line.strip()[:120]}"
                    )


def main() -> int:
    findings: list[str] = []
    check_links(findings)
    check_drift(findings)
    if findings:
        print(f"docs_check: {len(findings)} finding(s)")
        for finding in findings:
            print(f"  - {finding}")
        return 1
    print(f"docs_check: clean ({len(SCANNED)} documents scanned)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
