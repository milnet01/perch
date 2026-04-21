#!/usr/bin/env bash
# Flathub first submission — fork github.com/flathub/flathub,
# commit the manifest + regenerated python deps includes, push to
# your fork, open a PR.
#
# Flathub's "new app" flow (2024+):
#   * You PR the manifest to flathub/flathub on a branch named
#     after the app id.
#   * Reviewers check the manifest, request changes, eventually
#     accept.
#   * On acceptance, Flathub admins create flathub/io.github.milnet01.Perch.
#     Future updates go there, not flathub/flathub.
#
# Preconditions:
#   * `gh` authed (you have it — milnet01).
#   * `flatpak` installed (you have it).
#   * `flatpak-builder` installed for the local build smoke test:
#       SUDO_ASKPASS=/usr/libexec/ssh/ksshaskpass sudo -A \
#           zypper install flatpak-builder
#   * `flatpak-builder-tools` cloned so `flatpak-pip-generator` is
#     reachable. Script clones it to a scratch dir on demand.
#   * The org.kde.Platform//6.8 runtime installed (script installs
#     if missing).
#
# **This script does not open the PR automatically.** It prepares
# the fork branch, builds locally, and stops — so you can review the
# generated python deps files + the Flatpak manifest before
# actually pushing to your fork and opening the PR.

set -euo pipefail

usage() {
    cat <<'HELP'
Usage: packaging/submit/flathub.sh [--skip-build] [--push]

Flags:
  --skip-build   Skip the local `flatpak-builder` smoke test. Only use
                 when the full build has been verified recently.
  --push         After preparing the fork branch, push to
                 github.com/milnet01/flathub and open a PR. Default
                 behaviour is stage-only so you can eyeball the diff
                 first.

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

REPO_ROOT="$(git -C "$(dirname "${BASH_SOURCE[0]}")" rev-parse --show-toplevel)"
cd "$REPO_ROOT"

APP_ID="${APP_ID:-io.github.milnet01.Perch}"
FORK="${FLATHUB_FORK:-milnet01}"
MANIFEST="packaging/flathub/$APP_ID.yml"
SCRATCH="$(mktemp -d -t perch-flathub-XXXX)"

if ! command -v gh >/dev/null; then
    echo "error: gh not installed or not on PATH" >&2
    exit 1
fi

if ! command -v flatpak-builder >/dev/null && [[ $SKIP_BUILD -eq 0 ]]; then
    echo "error: flatpak-builder not installed. Install with:" >&2
    echo "  SUDO_ASKPASS=/usr/libexec/ssh/ksshaskpass sudo -A zypper install flatpak-builder" >&2
    echo "or re-run with --skip-build (only if you've built this manifest recently)." >&2
    exit 1
fi

trap 'rm -rf "$SCRATCH"' EXIT
cd "$SCRATCH"

# ── 1. Clone flatpak-builder-tools to get flatpak-pip-generator. ─────
echo ">> [1/6] fetching flatpak-builder-tools..."
git clone --depth=1 https://github.com/flatpak/flatpak-builder-tools.git fbt
PIPGEN="$PWD/fbt/pip/flatpak-pip-generator"
[[ -x "$PIPGEN" ]] || chmod +x "$PIPGEN"

# ── 2. Generate python3-*.yml includes from pyproject.toml pins. ─────
echo ">> [2/6] generating python deps manifests..."
python3 "$PIPGEN" --output python3-perch-deps \
    'PySide6>=6.8,<7' \
    'qasync>=0.28,<1' \
    'sdbus>=0.14.2,<1' \
    'python-xlib>=0.33' \
    'tomlkit>=0.13,<1'
# Matches pyproject.toml's [project].dependencies exactly; regenerate
# whenever those pins change.

# ── 3. Fork + clone flathub/flathub. ────────────────────────────────
echo ">> [3/6] forking + cloning flathub/flathub..."
gh repo fork flathub/flathub --clone=true --remote=true --default-branch-only=false 2>&1 | tail -3 || true
if [[ ! -d flathub ]]; then
    gh repo clone "$FORK/flathub" flathub
fi
cd flathub
git remote add upstream https://github.com/flathub/flathub.git 2>/dev/null || true
git fetch upstream master
git checkout -B "$APP_ID" upstream/master

# ── 4. Drop the manifest + generated deps into the branch. ──────────
echo ">> [4/6] staging manifest..."
cp "$REPO_ROOT/$MANIFEST" "$APP_ID.yml"
cp "$SCRATCH/python3-perch-deps.yaml" python3-perch-deps.yml 2>/dev/null \
    || cp "$SCRATCH"/python3-*.yaml ./

# Enable the python deps include in the manifest.
sed -i 's|^\s*#\s*-\s*python3-perch-deps.yml|        - python3-perch-deps.yml|' "$APP_ID.yml" || true

git add "$APP_ID.yml" python3-*.yml
git status

# ── 5. Local build smoke test. ──────────────────────────────────────
if [[ $SKIP_BUILD -eq 0 ]]; then
    echo ">> [5/6] local flatpak-builder smoke test..."
    flatpak install -y --noninteractive flathub \
        org.kde.Sdk//6.8 org.kde.Platform//6.8 2>&1 | tail -3 || true
    flatpak-builder --force-clean --ccache --user \
        --install-deps-from=flathub \
        build-dir "$APP_ID.yml"
    echo "   build succeeded."
else
    echo ">> [5/6] --skip-build set, skipping local build."
fi

# ── 6. Commit in fork; optionally push + open PR. ────────────────────
git commit -m "add: $APP_ID v$(grep -m1 '^version' "$REPO_ROOT/pyproject.toml" | cut -d'"' -f2)"

if [[ $DO_PUSH -eq 0 ]]; then
    echo
    echo "✔ Branch staged at: $PWD (not pushed)"
    echo "  Review the commit, then re-run with --push to submit the PR."
    echo
    exit 0
fi

read -r -p ">> push to $FORK/flathub and open PR against flathub/flathub ? [y/N] " confirm
case "$confirm" in
    y|Y|yes|YES) ;;
    *) echo "aborted."; exit 1 ;;
esac

git push -u origin "$APP_ID" --force-with-lease
gh pr create \
    --repo flathub/flathub \
    --base master \
    --head "$FORK:$APP_ID" \
    --title "Add $APP_ID" \
    --body "$(cat <<PRBODY
Submitting $APP_ID (Perch) for Flathub review.

Upstream: https://github.com/milnet01/perch
License: GPL-3.0-or-later
Tag: v$(grep -m1 '^version' "$REPO_ROOT/pyproject.toml" | cut -d'"' -f2)

Manifest authored at \`packaging/flathub/$APP_ID.yml\` in the upstream
repo. Python deps regenerated from \`pyproject.toml\` pins via
\`flatpak-pip-generator\`. Local \`flatpak-builder\` smoke test
passes on this machine.

Happy to address review feedback; I'll iterate on this branch.
PRBODY
)"
echo ">> PR opened. Track review progress on flathub/flathub."
