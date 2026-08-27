#!/usr/bin/env python3
"""Prove local_CI.sh and .github/workflows/ci.yml still run the same checks.

CLAUDE.md makes their agreement a hard rule, and until now nothing enforced
it: a check added to ci.yml alone still let `local_CI.sh` print "safe to
push", which is the one sentence that must never be able to lie.

The correspondence is DECLARED below rather than inferred, because the two
files legitimately name the same check differently -- CI's single "PKGBUILD
shell syntax" step is two local checks, and the appstream step keeps a name
from the tool it used to call. Inferring a mapping from names that are
allowed to differ would either miss real drift or invent it.

Four questions, all mechanical:

  1. Does every ci.yml check step have a declared local counterpart?
  2. Does every declared counterpart still exist in local_CI.sh?
  3. Is the mapping itself stale -- does it name a ci.yml step that is gone?
  4. Does local_CI.sh run a check that CI does not?

Question 1 is the one that matters: a CI check with no local equivalent is
a red push waiting to happen. Question 4 is reported too, because a local
check CI never runs is a check nobody is really gated on.

Usage: python tools/ci_lockstep_check.py   (exit 0 clean, 1 with findings)
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github/workflows/ci.yml"
GATE = ROOT / "local_CI.sh"

# ci.yml steps that build the environment rather than check anything. They
# have no local counterpart by design: local_CI.sh uses the project's .venv
# and the tools already on the machine.
SETUP_STEPS = {
    "Set up Python ${{ matrix.python-version }}",
    "Install system deps (Xvfb + Qt runtime libs)",
    "Install Perch + dev extras",
    "Install validators",
}

# ci.yml step name -> the local_CI.sh run label(s) covering it.
EQUIVALENT: dict[str, list[str]] = {
    "ruff": ["ruff"],
    "mypy": ["mypy"],
    "intent-dispatch audit": ["intent-dispatch audit"],
    "CI/local lockstep": ["CI/local lockstep"],
    "pytest": ["pytest"],
    "docs check (links + drift)": ["docs check (links + drift)"],
    "appstream-util validate (metainfo)": ["appstreamcli validate (metainfo)"],
    "desktop-file-validate": ["desktop-file-validate"],
    "yamllint (Flatpak manifest)": ["yamllint (Flatpak manifest)"],
    "rpmspec parse (OBS spec)": ["rpmspec parse (OBS spec)"],
    "PKGBUILD shell syntax (bash -n)": [
        "PKGBUILD bash -n (release)",
        "PKGBUILD bash -n (git)",
    ],
    "KWin script metadata.json well-formedness": [
        "KWin script metadata.json well-formedness"
    ],
}

# Differences that are deliberate, with the reason. Recorded here so a
# reader can tell a considered deviation from an accident.
KNOWN_DEVIATIONS = """\
  - pytest: CI runs the whole suite; local_CI.sh excludes the x11/kwin
    markers. CI installs no compositor so those tests skip there anyway,
    and this box has openbox, so they would run (live and flaky) and break
    the "green local implies green CI" implication.
  - CI runs the test job on 3.12/3.13/3.14; local_CI.sh uses one
    interpreter, so a version-specific failure can still reach CI."""

RUN_LABEL = re.compile(r'\brun\s+"([^"]+)"')


def ci_check_steps() -> list[str]:
    workflow = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    names = []
    for job in workflow["jobs"].values():
        for step in job.get("steps", []):
            if "run" not in step:
                continue  # an action (checkout, setup-python), not a check
            name = step.get("name")
            if name and name not in SETUP_STEPS:
                names.append(name)
    return names


def local_labels() -> list[str]:
    text = GATE.read_text(encoding="utf-8")
    # Skip the definition line itself: `run() {  # run "<label>" ...`
    return [m for m in RUN_LABEL.findall(text) if m != "<label>"]


def main() -> int:
    ci = ci_check_steps()
    local = local_labels()
    findings: list[str] = []

    for name in ci:
        if name not in EQUIVALENT:
            findings.append(
                f"ci.yml step {name!r} has no declared local counterpart -- "
                f"add the check to local_CI.sh and map it in {Path(__file__).name}"
            )

    for name, labels in EQUIVALENT.items():
        if name not in ci:
            findings.append(
                f"mapping is stale: no ci.yml step named {name!r} "
                f"(renamed or removed?)"
            )
        for label in labels:
            if label not in local:
                findings.append(
                    f"local_CI.sh has no check labelled {label!r}, "
                    f"which ci.yml step {name!r} is mapped to"
                )

    mapped = {label for labels in EQUIVALENT.values() for label in labels}
    for label in local:
        if label not in mapped:
            findings.append(
                f"local_CI.sh runs {label!r}, which no ci.yml step covers -- "
                f"add it to ci.yml, or map it if CI names it differently"
            )

    if findings:
        print(f"ci_lockstep_check: {len(findings)} finding(s)")
        for finding in findings:
            print(f"  - {finding}")
        return 1

    print(
        f"ci_lockstep_check: in lockstep "
        f"({len(ci)} CI checks, {len(local)} local checks)"
    )
    print("known deliberate deviations:")
    print(KNOWN_DEVIATIONS)
    return 0


if __name__ == "__main__":
    sys.exit(main())
