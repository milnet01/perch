#!/usr/bin/env bash
# AUR submission — push packaging/aur/PKGBUILD (or packaging/aur/perch-git/)
# to the matching AUR repository.
#
# Preconditions:
#   * SSH key registered on your AUR account at
#     https://aur.archlinux.org/account/  (add your public key under
#     "My Account" → "SSH Public Key").
#   * git knows to use that key for aur.archlinux.org. Either:
#       - Put it in ~/.ssh/config:
#           Host aur.archlinux.org
#               IdentityFile ~/.ssh/aur_ed25519
#               User aur
#       - Or ensure your default SSH identity is the registered one.
#   * The package does not yet exist on AUR → the first push creates
#     it; subsequent pushes update it.
#
# Idempotent: re-runs overwrite the AUR-side branch with the current
# packaging/aur/<pkg>/ contents plus a fresh .SRCINFO.

set -euo pipefail

usage() {
    cat <<'HELP'
Usage: packaging/submit/aur.sh <perch|perch-git>

Pushes the selected PKGBUILD + .SRCINFO to
  ssh://aur@aur.archlinux.org/<pkgname>.git

Environment:
  AUR_DRY_RUN=1   Do everything except the final `git push`.
  AUR_REMOTE      Override the AUR remote URL.
HELP
}

if [[ $# -ne 1 ]]; then
    usage >&2
    exit 2
fi

case "$1" in
    -h|--help) usage; exit 0 ;;
    perch) PKG_DIR="packaging/aur" ; PKGNAME="perch" ;;
    perch-git) PKG_DIR="packaging/aur/perch-git" ; PKGNAME="perch-git" ;;
    *) usage >&2 ; exit 2 ;;
esac

REPO_ROOT="$(git -C "$(dirname "${BASH_SOURCE[0]}")" rev-parse --show-toplevel)"
cd "$REPO_ROOT"

if [[ ! -f "$PKG_DIR/PKGBUILD" ]]; then
    echo "error: missing $PKG_DIR/PKGBUILD" >&2
    exit 1
fi

if [[ ! -f "$PKG_DIR/.SRCINFO" ]]; then
    echo "error: missing $PKG_DIR/.SRCINFO — regenerate with 'makepkg --printsrcinfo > .SRCINFO'" >&2
    exit 1
fi

REMOTE="${AUR_REMOTE:-ssh://aur@aur.archlinux.org/$PKGNAME.git}"

# Use a scratch clone so the user's main checkout is not touched.
SCRATCH="$(mktemp -d -t perch-aur-$PKGNAME-XXXX)"
trap 'rm -rf "$SCRATCH"' EXIT

echo ">> cloning AUR remote: $REMOTE"
if ! git clone "$REMOTE" "$SCRATCH/repo" 2>/dev/null; then
    echo "   (AUR repo missing or empty — initialising new one)"
    git init "$SCRATCH/repo"
    git -C "$SCRATCH/repo" remote add origin "$REMOTE"
fi

# Copy PKGBUILD + .SRCINFO (and any extra files like perch.install).
cp "$PKG_DIR/PKGBUILD" "$SCRATCH/repo/PKGBUILD"
cp "$PKG_DIR/.SRCINFO" "$SCRATCH/repo/.SRCINFO"
[[ -f "$PKG_DIR/perch.install" ]] && cp "$PKG_DIR/perch.install" "$SCRATCH/repo/perch.install"

git -C "$SCRATCH/repo" add -A
if git -C "$SCRATCH/repo" diff --cached --quiet; then
    echo ">> no changes to submit — AUR repo is already current."
    exit 0
fi

# Reuse the user's global git identity; AUR rejects pushes without an
# author. Falls back to milnet01 if none is set locally.
git -C "$SCRATCH/repo" commit -m "release: $PKGNAME $(grep -m1 '^pkgver=' $PKG_DIR/PKGBUILD | cut -d= -f2)"

echo ">> staged commit in scratch clone:"
git -C "$SCRATCH/repo" --no-pager log -1 --stat

if [[ "${AUR_DRY_RUN:-0}" == "1" ]]; then
    echo ">> AUR_DRY_RUN=1 — skipping push."
    exit 0
fi

read -r -p ">> push to $REMOTE ? [y/N] " confirm
case "$confirm" in
    y|Y|yes|YES) ;;
    *) echo "aborted."; exit 1 ;;
esac

git -C "$SCRATCH/repo" push -u origin master
echo ">> pushed. AUR listing: https://aur.archlinux.org/packages/$PKGNAME"
