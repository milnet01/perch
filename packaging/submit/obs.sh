#!/usr/bin/env bash
# openSUSE Build Service submission — create / update the
# home:<user>:perch SUBPROJECT using packaging/rpm/perch.spec + _service.
#
# A subproject (home:milnet:perch), not a package in home:milnet. That is
# the convention already used on this account for ants-terminal and
# finbreak, and it gives each project its own repository list -- Perch
# builds RPMs for Tumbleweed and Fedora only, where finbreak also targets
# Debian and Ubuntu.
#
# The subproject must exist before the first run. Create it with:
#   osc meta prj home:<user>:perch -e
#
# Preconditions:
#   * `osc` installed.  On Tumbleweed:
#       SUDO_ASKPASS=/usr/libexec/ssh/ksshaskpass sudo -A \
#           zypper install --no-recommends osc
#   * `osc -A https://api.opensuse.org login` completed (prompts once
#     for your openSUSE account password; osc writes its config with a
#     username + password / token pair). Modern osc uses
#     ~/.config/osc/oscrc; older versions used ~/.oscrc.
#   * You have access to home:<user>:  every openSUSE account owns one
#     by default; if it doesn't exist, the script creates it.
#
# This uploads the spec plus the release TARBALL, and uses no OBS source
# service at all.
#
# The _service file this replaced did not work and could not have. Its
# obs_scm entry was mode="manual", so OBS never ran it server-side and
# the build died with `no .obsinfo file found`; and having ANY buildtime
# service pulls the obs-service-* packages into the build root, where
# Fedora could not resolve `wget` (obs-service-download_files depends on
# it, and both wget1-wget and wget2-wget provide it). Both targets failed,
# for two unrelated reasons, from one mechanism nobody needed.
#
# Source0 in the spec is the GitHub archive URL and %autosetup expects
# perch-<version>/, which is exactly what that archive contains -- so
# uploading the tarball is all OBS needs. The cost is that a new release
# means re-running this script rather than OBS noticing a tag; that is one
# command, against a tag-watching mechanism that has never once fired.

set -euo pipefail

usage() {
    cat <<'HELP'
Usage: packaging/submit/obs.sh [--dry-run]

Env:
  OBS_API       OBS API URL (default: https://api.opensuse.org).
  OBS_USER      OBS username (default: inferred from ~/.oscrc).
  OBS_PROJECT   Override the target project (default: home:<OBS_USER>:perch).
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

# osc moved its config to ~/.config/osc/oscrc; older versions used ~/.oscrc.
# Checking only the old path made this script refuse to run on a machine
# where osc was perfectly well configured.
OSCRC=""
for candidate in "${XDG_CONFIG_HOME:-$HOME/.config}/osc/oscrc" "$HOME/.oscrc"; do
    [[ -f $candidate ]] && { OSCRC="$candidate"; break; }
done
if [[ -z $OSCRC ]]; then
    echo "error: osc is not configured (looked for ~/.config/osc/oscrc and ~/.oscrc). Run:" >&2
    echo "  osc -A https://api.opensuse.org login" >&2
    exit 1
fi

API="${OBS_API:-https://api.opensuse.org}"
USER="${OBS_USER:-$(awk -F= '/^user/ { gsub(/ /, "", $2); print $2; exit }' "$OSCRC")}"
PROJECT="${OBS_PROJECT:-home:$USER:perch}"
PACKAGE="perch"

echo ">> OBS project: $PROJECT"
echo ">> OBS package: $PACKAGE"

SCRATCH="$(mktemp -d -t perch-obs-XXXX)"
trap 'rm -rf "$SCRATCH"' EXIT

cd "$SCRATCH"

echo ">> checking out project..."
osc -A "$API" co "$PROJECT" || {
    echo "error: cannot access $PROJECT on $API." >&2
    echo "       If it does not exist yet, create the subproject first:" >&2
    echo "         osc -A $API meta prj $PROJECT -e" >&2
    exit 1
}

cd "$PROJECT"
if [[ ! -d "$PACKAGE" ]]; then
    echo ">> creating $PACKAGE package..."
    osc -A "$API" mkpac "$PACKAGE"
fi
cd "$PACKAGE"

VERSION="$(grep -m1 '^version' "$REPO_ROOT/pyproject.toml" | cut -d'"' -f2)"
TARBALL="perch-${VERSION}.tar.gz"
TARBALL_URL="https://github.com/milnet01/perch/archive/v${VERSION}/${TARBALL}"

# Copy the spec. Re-runs overwrite.
cp "$REPO_ROOT/packaging/rpm/perch.spec" ./

echo ">> fetching $TARBALL_URL"
if ! curl -fsSL -o "$TARBALL" "$TARBALL_URL"; then
    echo "error: could not fetch $TARBALL_URL" >&2
    echo "       Is v$VERSION tagged and pushed on GitHub?" >&2
    exit 1
fi

# Drop a stale _service and any older tarball -- OBS keeps whatever was
# committed before, and a leftover source is a build that succeeds against
# the wrong version.
for stale in _service $(ls perch-*.tar.gz 2>/dev/null | grep -Fxv "$TARBALL"); do
    [[ -e $stale ]] && osc rm --force "$stale" >/dev/null 2>&1 || true
done

osc add perch.spec "$TARBALL" 2>/dev/null || true

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
