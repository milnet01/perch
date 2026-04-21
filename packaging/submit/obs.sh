#!/usr/bin/env bash
# openSUSE Build Service submission — create / update
# home:<user>/perch using packaging/rpm/perch.spec + _service.
#
# Preconditions:
#   * `osc` installed.  On Tumbleweed:
#       SUDO_ASKPASS=/usr/libexec/ssh/ksshaskpass sudo -A \
#           zypper install --no-recommends osc
#   * `osc -A https://api.opensuse.org login` completed (prompts once
#     for your openSUSE account password; osc writes ~/.oscrc with a
#     username + password / token pair).
#   * You have access to home:<user>:  every openSUSE account owns one
#     by default; if it doesn't exist, the script creates it.
#
# OBS's `obs_scm` service reads the upstream tag on its build nodes,
# so this script just pushes _service + perch.spec; OBS does the
# checkout + build itself. No local build required.

set -euo pipefail

usage() {
    cat <<'HELP'
Usage: packaging/submit/obs.sh [--dry-run]

Env:
  OBS_API       OBS API URL (default: https://api.opensuse.org).
  OBS_USER      OBS username (default: inferred from ~/.oscrc).
  OBS_PROJECT   Override the target project (default: home:<OBS_USER>).
HELP
}

[[ "${1:-}" == "-h" || "${1:-}" == "--help" ]] && { usage; exit 0; }
DRY="${1:-}"

REPO_ROOT="$(git -C "$(dirname "${BASH_SOURCE[0]}")" rev-parse --show-toplevel)"
cd "$REPO_ROOT"

if ! command -v osc >/dev/null; then
    echo "error: osc not installed. Install with:" >&2
    echo "  SUDO_ASKPASS=/usr/libexec/ssh/ksshaskpass sudo -A zypper install osc" >&2
    exit 1
fi

if [[ ! -f "$HOME/.oscrc" ]]; then
    echo "error: ~/.oscrc not configured. Run:" >&2
    echo "  osc -A https://api.opensuse.org login" >&2
    exit 1
fi

API="${OBS_API:-https://api.opensuse.org}"
USER="${OBS_USER:-$(awk -F= '/^user/ { gsub(/ /, "", $2); print $2; exit }' ~/.oscrc)}"
PROJECT="${OBS_PROJECT:-home:$USER}"
PACKAGE="perch"

echo ">> OBS project: $PROJECT"
echo ">> OBS package: $PACKAGE"

SCRATCH="$(mktemp -d -t perch-obs-XXXX)"
trap 'rm -rf "$SCRATCH"' EXIT

cd "$SCRATCH"

echo ">> checking out project (creates home:$USER if absent)..."
osc -A "$API" co "$PROJECT" || {
    echo "error: cannot access $PROJECT on $API" >&2
    exit 1
}

cd "$PROJECT"
if [[ ! -d "$PACKAGE" ]]; then
    echo ">> creating $PACKAGE package..."
    osc -A "$API" mkpac "$PACKAGE"
fi
cd "$PACKAGE"

# Copy the spec + service definition. Re-runs overwrite.
cp "$REPO_ROOT/packaging/rpm/perch.spec" ./
cp "$REPO_ROOT/packaging/rpm/_service" ./
osc add perch.spec _service 2>/dev/null || true

echo ">> staged files:"
osc status

if [[ "$DRY" == "--dry-run" ]]; then
    echo ">> --dry-run — skipping commit."
    exit 0
fi

read -r -p ">> commit to $PROJECT/$PACKAGE ? [y/N] " confirm
case "$confirm" in
    y|Y|yes|YES) ;;
    *) echo "aborted."; exit 1 ;;
esac

osc commit -m "release: v$(grep -m1 '^version' "$REPO_ROOT/pyproject.toml" | cut -d'"' -f2)"

echo ">> committed. OBS will run the source service + build on its nodes."
echo ">> track build: $API/package/show/$PROJECT/$PACKAGE"
echo ">>              https://build.opensuse.org/package/show/$PROJECT/$PACKAGE"
