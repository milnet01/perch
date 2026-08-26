#!/usr/bin/env bash
#
# local_CI.sh — run the same checks as .github/workflows/ci.yml, locally,
# BEFORE pushing. Catches ruff/mypy/pytest/packaging failures here so a push
# doesn't burn a CI run to tell us what we could have known in 30 seconds.
# Goal: a green local_CI implies a green CI.
#
# HARD RULE: keep this script in lockstep with .github/workflows/ci.yml. If you
# edit one, edit the other in the SAME commit — drift between them defeats the
# entire purpose of the script.
#
# Behaviour vs CI: a CI job stops at its first failing step (the runner shell
# uses `bash -e`). This script instead runs EVERY check and lists all failures
# at the end, so a single local run tells you everything to fix rather than one
# thing at a time. The pass/fail verdict (exit status) is identical to CI.
#
# Two deliberate deviations, both so the local verdict matches CI's:
#   - Matrix: CI runs the test job on Python 3.12, 3.13 and 3.14. This script
#     uses whatever `python`/`ruff`/`mypy`/`pytest` resolve to on your PATH; for
#     full matrix parity, run it once under each interpreter.
#   - Live tests: the pytest step excludes the `x11`/`kwin` markers (see the
#     note at that step). CI installs no compositor so those tests skip there;
#     excluding them locally keeps the "green local ⟹ green CI" implication.

set -uo pipefail
cd "$(dirname "$0")"

# Use the project's .venv (the documented dev environment, see
# docs/contributing-dev-setup.md) if present, so python/ruff/mypy/pytest all
# resolve to the interpreter the editable `perch` install lives in — the local
# equivalent of CI's `pip install -e ".[dev]"`. We prepend .venv/bin to PATH
# directly rather than sourcing .venv/bin/activate: activate bakes in an
# absolute VIRTUAL_ENV that silently points at the wrong bin dir if the
# checkout was ever moved, sending pytest to the system interpreter.
#
# A detached worktree (the pre-push hook gates the tip being pushed in one, so
# the gate sees the commit rather than the dirty tree) has no .venv of its own
# -- .venv is gitignored and therefore never checked out. Fall back to the main
# worktree's .venv in that case, otherwise every check that needs the editable
# `perch` install fails to import it and the gate reports a false failure.
VENV_DIR=""
if [[ -x .venv/bin/python ]]; then
  VENV_DIR="$PWD/.venv"
else
  _common_dir=$(git rev-parse --path-format=absolute --git-common-dir 2>/dev/null || true)
  if [[ -n $_common_dir && -x "${_common_dir%/.git}/.venv/bin/python" ]]; then
    VENV_DIR="${_common_dir%/.git}/.venv"
  fi
fi
if [[ -z "${VIRTUAL_ENV:-}" && -n $VENV_DIR ]]; then
  export VIRTUAL_ENV="$VENV_DIR"
  export PATH="$VIRTUAL_ENV/bin:$PATH"
  hash -r 2>/dev/null || true
fi

# --- pretty output (plain when not a TTY) ------------------------------------
if [[ -t 1 ]]; then
  RED=$'\e[31m'; GREEN=$'\e[32m'; YELLOW=$'\e[33m'; BOLD=$'\e[1m'; RESET=$'\e[0m'
else
  RED=''; GREEN=''; YELLOW=''; BOLD=''; RESET=''
fi

PYTHON="$(command -v python || command -v python3)"
FAILED=()

run() {  # run "<label>" <command...>
  local label="$1"; shift
  printf '%s\n' "${BOLD}== ${label} ==${RESET}"
  if "$@"; then
    printf '   %sPASS%s: %s\n\n' "$GREEN" "$RESET" "$label"
  else
    printf '   %sFAIL%s: %s\n\n' "$RED" "$RESET" "$label"
    FAILED+=("$label")
  fi
}

need() {  # need <tool> "<install hint>" — records a failure if the tool is absent
  local tool="$1" hint="$2"
  if ! command -v "$tool" >/dev/null 2>&1; then
    printf '%s\n\n' "${RED}   MISSING TOOL: ${tool} — install with: ${hint}${RESET}"
    FAILED+=("missing:${tool}")
    return 1
  fi
}

# ==== job: test (ci.yml) =====================================================
need ruff   "pipx install ruff (or pip install -e '.[dev]')"   && run "ruff"  ruff check .
need mypy   "pip install -e '.[dev]'"                          && run "mypy"  mypy
run "intent-dispatch audit" "$PYTHON" tools/intent_dispatch_audit.py
# The `x11` / `kwin` markers gate LIVE integration tests that spawn a real
# Xvfb+openbox / kwin_wayland session. CI installs neither compositor, so those
# tests skip there — but this dev box has openbox installed, so they would run
# (and they are live + flaky). Exclude them so a green local_CI implies a green
# CI (the whole point of the gate); run them deliberately with `pytest -m x11`.
need pytest "pip install -e '.[dev]'" \
  && run "pytest" env QT_QPA_PLATFORM=offscreen pytest -ra -m "not x11 and not kwin"

# ==== job: packaging (ci.yml) ================================================
need appstreamcli "zypper in appstream" \
  && run "appstreamcli validate (metainfo)" \
       appstreamcli validate --no-net data/io.github.milnet01.Perch.metainfo.xml

need desktop-file-validate "zypper in desktop-file-utils" \
  && run "desktop-file-validate" \
       desktop-file-validate data/io.github.milnet01.Perch.desktop

need yamllint "zypper in python3-yamllint" \
  && run "yamllint (Flatpak manifest)" \
       yamllint -d "{extends: relaxed, rules: {line-length: disable}}" \
       packaging/flathub/io.github.milnet01.Perch.yml

need rpmspec "zypper in rpm-build" \
  && run "rpmspec parse (OBS/COPR spec)" \
       bash -c 'rpmspec -P packaging/rpm/perch.spec > /dev/null'

run "PKGBUILD bash -n (release)" bash -n packaging/aur/PKGBUILD
run "PKGBUILD bash -n (git)"     bash -n packaging/aur/perch-git/PKGBUILD

run "KWin script metadata.json well-formedness" \
  "$PYTHON" -c 'import json; json.load(open("src/perch/backend/kwin/script/metadata.json"))'

# ==== verdict ================================================================
if ((${#FAILED[@]})); then
  printf '%s\n' "${RED}${BOLD}CI FAILED — ${#FAILED[@]} check(s) below. Fix before pushing.${RESET}"
  for f in "${FAILED[@]}"; do printf '  %s- %s%s\n' "$RED" "$f" "$RESET"; done
  exit 1
fi
printf '%s\n' "${GREEN}${BOLD}All CI checks passed — safe to push.${RESET}"
