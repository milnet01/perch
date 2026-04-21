#!/usr/bin/env bash
# Fedora COPR submission — create / update <user>/perch and kick
# off a build from the upstream tag.
#
# Preconditions:
#   * `copr-cli` installed. On Tumbleweed:
#       SUDO_ASKPASS=/usr/libexec/ssh/ksshaskpass sudo -A \
#           pip install --break-system-packages copr-cli
#     (or via Fedora: `dnf install copr-cli`)
#   * API token in ~/.config/copr
#     Get it from https://copr.fedorainfracloud.org/api/ — click
#     "Get API token" and paste the block into ~/.config/copr.
#   * The project `<user>/perch` does not yet exist (first run
#     creates it) or already exists (subsequent runs rebuild).
#
# COPR's "Custom source" build mode pulls the GitHub tarball; this
# script wires that in with a SCM URL pointing at v<version>.

set -euo pipefail

usage() {
    cat <<'HELP'
Usage: packaging/submit/copr.sh [--dry-run]

Env:
  COPR_USER         COPR username (default: inferred from ~/.config/copr).
  COPR_PROJECT      Project name (default: perch).
  COPR_CHROOTS      Target chroots (default: fedora-latest,fedora-rawhide,opensuse-tumbleweed-x86_64).
HELP
}

[[ "${1:-}" == "-h" || "${1:-}" == "--help" ]] && { usage; exit 0; }
DRY="${1:-}"

REPO_ROOT="$(git -C "$(dirname "${BASH_SOURCE[0]}")" rev-parse --show-toplevel)"
cd "$REPO_ROOT"

if ! command -v copr-cli >/dev/null; then
    echo "error: copr-cli not installed." >&2
    echo "  dnf install copr-cli          # on Fedora" >&2
    echo "  pip install --user copr-cli   # elsewhere" >&2
    exit 1
fi

if [[ ! -f "$HOME/.config/copr" ]]; then
    echo "error: ~/.config/copr is missing." >&2
    echo "  Get an API token at https://copr.fedorainfracloud.org/api/" >&2
    exit 1
fi

USER="${COPR_USER:-$(awk -F= '/^username/ { gsub(/ /, "", $2); print $2; exit }' ~/.config/copr)}"
PROJECT="${COPR_PROJECT:-perch}"
CHROOTS="${COPR_CHROOTS:-fedora-latest-x86_64 opensuse-tumbleweed-x86_64}"
VERSION="$(grep -m1 '^version' pyproject.toml | cut -d'"' -f2)"
TARBALL_URL="https://github.com/milnet01/perch/archive/v${VERSION}/perch-${VERSION}.tar.gz"

echo ">> COPR user:     $USER"
echo ">> project:       $USER/$PROJECT"
echo ">> chroots:       $CHROOTS"
echo ">> tarball:       $TARBALL_URL"

# Does the project already exist?
if copr-cli list-package-names "$USER/$PROJECT" >/dev/null 2>&1; then
    echo ">> project exists — will submit a new build."
else
    if [[ "$DRY" == "--dry-run" ]]; then
        echo ">> --dry-run — would 'copr-cli create $USER/$PROJECT'"
    else
        read -r -p ">> project doesn't exist. Create $USER/$PROJECT ? [y/N] " confirm
        case "$confirm" in
            y|Y|yes|YES) ;;
            *) echo "aborted."; exit 1 ;;
        esac
        copr-cli create --chroot $CHROOTS --description "Perch — persistent window geometry manager" "$PROJECT"
    fi
fi

if [[ "$DRY" == "--dry-run" ]]; then
    echo ">> --dry-run — skipping build submission."
    exit 0
fi

read -r -p ">> submit build v$VERSION ? [y/N] " confirm
case "$confirm" in
    y|Y|yes|YES) ;;
    *) echo "aborted."; exit 1 ;;
esac

# --nowait returns immediately; the user tracks progress on copr.fedorainfracloud.org.
copr-cli build --nowait "$USER/$PROJECT" "$TARBALL_URL"
echo ">> submitted. track: https://copr.fedorainfracloud.org/coprs/$USER/$PROJECT/"
