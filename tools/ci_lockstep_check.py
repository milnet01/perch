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

Five questions, all mechanical:

  1. Does every ci.yml check step have a declared local counterpart?
  2. Does every declared counterpart still exist in local_CI.sh?
  3. Is the mapping itself stale -- does it name a ci.yml step that is gone?
  4. Does local_CI.sh run a check that CI does not?
  5. Does a step CI runs once per matrix interpreter run locally under EVERY
     one of those interpreters?

Question 1 is the one that matters: a CI check with no local equivalent is
a red push waiting to happen. Question 4 is reported too, because a local
check CI never runs is a check nobody is really gated on. Question 5 was
added after CI run 33145715623, where a local run green under 3.13 was
followed by a 3.14-only failure: a check that runs locally under one of
three interpreters is a third of a check, and nothing said so.

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
    the "green local implies green CI" implication."""

RUN_LABEL = re.compile(r'\brun\s+"([^"]+)"')
# A local label may carry the matrix interpreter it ran under: `pytest (3.14)`.
VERSIONED = re.compile(r"^(?P<base>.+) \((?P<version>\d+\.\d+)\)$")


def ci_check_steps() -> dict[str, list[str]]:
    """Map each ci.yml check step to the interpreters it runs under.

    An empty list means the step runs once, outside any matrix -- the docs
    and packaging jobs. A non-empty one is every `python-version` its job's
    matrix names, which is how many times CI really runs that check.
    """
    workflow = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    steps: dict[str, list[str]] = {}
    for job in workflow["jobs"].values():
        matrix = job.get("strategy", {}).get("matrix", {})
        versions = [str(v) for v in matrix.get("python-version", [])]
        for step in job.get("steps", []):
            if "run" not in step:
                continue  # an action (checkout, setup-python), not a check
            name = step.get("name")
            if name and name not in SETUP_STEPS:
                steps[name] = versions
    return steps


#: The loop variable local_CI.sh suffixes a matrixed check with. The labels
#: are read out of the script's source, so a check inside `for ver in ...`
#: reads literally as `pytest ($ver)`; expanding it here against the matrix
#: is what lets one written line stand for the three runs it performs. Rename
#: the loop variable and every matrixed label reads as uncovered -- loud and
#: in the right direction, which is why the coupling is acceptable.
MATRIX_PLACEHOLDER = "($ver)"


def local_labels(versions: list[str]) -> list[str]:
    text = GATE.read_text(encoding="utf-8")
    # Skip the definition line itself: `run() {  # run "<label>" ...`
    raw = [m for m in RUN_LABEL.findall(text) if m != "<label>"]
    labels: list[str] = []
    for label in raw:
        if label.endswith(f" {MATRIX_PLACEHOLDER}"):
            base = label[: -len(MATRIX_PLACEHOLDER) - 1]
            labels.extend(f"{base} ({v})" for v in versions)
        else:
            labels.append(label)
    return labels


def main() -> int:
    ci = ci_check_steps()
    all_versions = {v for versions in ci.values() for v in versions}
    local = local_labels(sorted(all_versions))
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
            continue
        # A matrixed step must appear once per interpreter, suffixed with it;
        # an unmatrixed one appears bare. Running a matrixed check under one
        # interpreter is the gap that lets a version-specific failure reach CI.
        for label in labels:
            wanted = [f"{label} ({v})" for v in ci[name]] or [label]
            for want in wanted:
                if want not in local:
                    findings.append(
                        f"local_CI.sh has no check labelled {want!r}, "
                        f"which ci.yml step {name!r} is mapped to"
                    )

    mapped = {label for labels in EQUIVALENT.values() for label in labels}
    for label in local:
        match = VERSIONED.match(label)
        base = match["base"] if match else label
        if base not in mapped:
            findings.append(
                f"local_CI.sh runs {label!r}, which no ci.yml step covers -- "
                f"add it to ci.yml, or map it if CI names it differently"
            )
        elif match and match["version"] not in all_versions:
            findings.append(
                f"local_CI.sh runs {label!r} under Python "
                f"{match['version']}, which ci.yml's matrix does not name"
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
