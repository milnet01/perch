#!/usr/bin/env bash
# Flathub first submission — orchestrates the three steps that must all pass,
# then forks flathub/flathub, stages the submission files and (with --push)
# opens the PR.
#
# It owns none of the work itself. The pieces live next to the manifest and
# are individually runnable:
#   packaging/flathub/generate-pip-sources.sh   the pinned dependency closure
#   packaging/flathub/flatpak-build.sh          the offline build + smoke
# This script runs them in the order a submission needs and adds the parts
# that only make sense once: the fork, the branch, the PR.
#
# Flathub's new-app flow:
#   * A NEW app is PR'd against the `new-pr` branch of flathub/flathub, not
#     `master`. A PR to master is the wrong queue.
#   * The branch is named after the app id, and carries the manifest,
#     python3-deps.yaml and flathub.json at the REPO ROOT -- no packaging/
#     directory travels with it, which is why the manifest reaches Perch's
#     own files through its git clone rather than by relative path.
#   * On acceptance Flathub creates flathub/io.github.milnet01.Perch and
#     future updates go there. Accept the repo invitation within a week,
#     with 2FA on the GitHub account -- both are Flathub requirements.
#
# Preconditions: `gh` authenticated, `flatpak-builder`, and the runtimes
#   flatpak install flathub org.kde.Platform//6.11 org.kde.Sdk//6.11 \
#       io.qt.PySide.BaseApp//6.11 org.flatpak.Builder
#
# It stages and STOPS by default. --push is the outward-facing step.
set -euo pipefail

usage() {
    cat <<'HELP'
Usage: packaging/submit/flathub.sh [--skip-build] [--push]

Flags:
  --skip-build   Skip the submission-mode build + smoke. Only when the full
                 build has been verified since the last manifest change.
  --push         Push the fork branch and open the PR. Default is stage-only
                 so the diff can be reviewed first.

Env:
  FLATHUB_FORK   Fork owner (default: milnet01).
  APP_ID         App id (default: io.github.milnet01.Perch).
HELP
}

SKIP_BUILD=0
DO_PUSH=0
for arg in "$@"; do
    case "$arg" in
        -h|--help) usage; exit 0 ;;
        --skip-build) SKIP_BUILD=1 ;;
        --push) DO_PUSH=1 ;;
        *) usage >&2 ; exit 2 ;;
    esac
done

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
APP_ID="${APP_ID:-io.github.milnet01.Perch}"
FORK="${FLATHUB_FORK:-milnet01}"
FLATHUB_DIR="$REPO_ROOT/packaging/flathub"
MANIFEST="$FLATHUB_DIR/$APP_ID.yml"
cd "$REPO_ROOT"

# ── 1. The closure must match pyproject, and be committed. ───────────
# Regenerating and diffing is the cheapest way to prove it: an empty diff IS
# the confirmation. "Regenerate if the closure changed" is a judgement call,
# and a dependency bump that lands in pyproject while python3-deps.yaml keeps
# the old pin builds green locally and fails on Flathub's builders.
echo ">> [1/5] confirming python3-deps.yaml matches pyproject.toml"
"$FLATHUB_DIR/generate-pip-sources.sh" >/dev/null
if ! git diff --quiet -- "$FLATHUB_DIR/python3-deps.yaml"; then
    echo "!! python3-deps.yaml is stale -- the closure moved since it was" >&2
    echo "   committed. Review and commit the regenerated file, then re-run:" >&2
    git --no-pager diff --stat -- "$FLATHUB_DIR/python3-deps.yaml" >&2
    exit 1
fi
echo "   closure current."

# ── 2. Build exactly what Flathub will build. ────────────────────────
# LOCAL=0 builds the committed manifest verbatim, from the release commit it
# pins. A default (LOCAL=1) build swaps in the working tree and so proves
# nothing about the submission.
if [[ $SKIP_BUILD -eq 0 ]]; then
    echo ">> [2/5] submission-mode build + smoke"
    LOCAL=0 "$FLATHUB_DIR/flatpak-build.sh"
else
    echo ">> [2/5] --skip-build set; NOT verified against the pinned commit."
fi

# ── 3. Flathub's own linter. Their infra runs it; a failure blocks. ──
echo ">> [3/5] flatpak-builder-lint (manifest + appstream)"
flatpak run --command=flatpak-builder-lint org.flatpak.Builder \
    manifest "$MANIFEST" || true
flatpak run --command=flatpak-builder-lint org.flatpak.Builder \
    appstream "$REPO_ROOT/data/$APP_ID.metainfo.xml" || true
cat <<'EOT'
   Any finish-args error above needs either removal or a written
   justification in the PR. Perch's three known ones are the KWin talk-name
   and the two filesystem paths -- see packaging/flathub/SUBMISSION.md.
EOT

# ── 4. Fork + branch from new-pr, stage the three files. ─────────────
echo ">> [4/5] forking flathub/flathub and staging the branch"
SCRATCH="$(mktemp -d)"
trap 'rm -rf "$SCRATCH"' EXIT
cd "$SCRATCH"
gh repo fork flathub/flathub --clone=true --remote=true --default-branch-only=false 2>&1 | tail -3 || true
[[ -d flathub ]] || gh repo clone "$FORK/flathub" flathub
cd flathub
git remote add upstream https://github.com/flathub/flathub.git 2>/dev/null || true
git fetch upstream new-pr
git checkout -B "$APP_ID" upstream/new-pr

cp "$MANIFEST"                      "$APP_ID.yml"
cp "$FLATHUB_DIR/python3-deps.yaml" python3-deps.yaml
cp "$FLATHUB_DIR/flathub.json"      flathub.json
git add "$APP_ID.yml" python3-deps.yaml flathub.json
git --no-pager diff --cached --stat

VERSION="$(grep -m1 '^version' "$REPO_ROOT/pyproject.toml" | cut -d'"' -f2)"
git commit -q -m "Add $APP_ID"

# ── 5. Push + PR, or stop. ───────────────────────────────────────────
if [[ $DO_PUSH -eq 0 ]]; then
    cat <<EOT

Branch staged at: $PWD (not pushed, and this directory is temporary)
Re-run with --push to submit, or copy the directory aside to keep it.
EOT
    trap - EXIT
    exit 0
fi

read -r -p ">> push to $FORK/flathub and open a PR against flathub/flathub ? [y/N] " confirm
case "$confirm" in
    y|Y|yes|YES) ;;
    *) echo "aborted."; exit 1 ;;
esac

git push -u origin "$APP_ID" --force-with-lease
gh pr create \
    --repo flathub/flathub \
    --base new-pr \
    --head "$FORK:$APP_ID" \
    --title "Add $APP_ID" \
    --body "$(cat <<PRBODY
Submitting $APP_ID (Perch) for Flathub review.

Upstream: https://github.com/milnet01/perch
License: GPL-3.0-or-later
Version: $VERSION

Perch is a window geometry manager for Plasma: it remembers where each
window belongs and restores it when the window reopens.

The manifest builds on org.kde.Platform//6.11 with io.qt.PySide.BaseApp for
PySide6 and Qt. The four remaining Python dependencies are sha256-pinned
wheels in python3-deps.yaml, generated from pyproject.toml, so the build is
network-free. flathub.json restricts the buildbot to x86_64, which is the
arch the pinned sdbus wheel covers.

These finish-args entries need justification:

- --talk-name=org.kde.KWin — Perch drives window placement through KWin's
  scripting D-Bus interface. This is the app's core function on Plasma
  Wayland; there is no portal equivalent.
- --filesystem=xdg-data/kwin/scripts:create — KWin runs on the host and
  cannot read /app, so the bundled KWin script has to be mirrored into the
  host's script directory at first run.

Happy to address review feedback; I'll iterate on this branch.
PRBODY
)"
echo ">> PR opened against the new-pr branch. Track review on flathub/flathub."
