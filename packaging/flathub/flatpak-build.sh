#!/usr/bin/env bash
# flatpak-build.sh — build + install + smoke-test the Perch Flatpak locally.
#
# Mirrors what Flathub's builders do, so a green local run is the strongest
# pre-submission signal available without submitting.
#
#   packaging/flathub/flatpak-build.sh          # build + install --user + smoke
#   packaging/flathub/flatpak-build.sh --run    # ...then launch the tray app
#   LOCAL=0 packaging/flathub/flatpak-build.sh  # build the manifest AS SUBMITTED
#
# The build phase runs with NO network -- every source is sha256- or
# commit-pinned, the same constraint Flathub imposes. A dependency that slips
# to an offline-unbuildable sdist fails HERE rather than in review.
#
# Requires: flatpak-builder, and from Flathub:
#   flatpak install flathub org.kde.Platform//6.11 org.kde.Sdk//6.11 \
#       io.qt.PySide.BaseApp//6.11
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$HERE/../.." && pwd)"
APP_ID="io.github.milnet01.Perch"
MANIFEST="$HERE/${APP_ID}.yml"
BUILDDIR="${BUILDDIR:-$HERE/.build}"
REPODIR="${REPODIR:-$HERE/.repo}"

if [[ ! -f "$HERE/python3-deps.yaml" ]]; then
    echo "!! python3-deps.yaml missing -- run generate-pip-sources.sh first" >&2
    exit 1
fi

# LOCAL=1 (the default, for dev iteration) builds the CURRENT checkout: it
# rewrites the perch module's git source to file://$REPO at branch HEAD, so
# committed-but-unpushed work can be validated without pushing and re-pinning.
# The committed manifest stays tag+commit pinned for submission.
#
# LOCAL=0 builds it verbatim -- which is what Flathub builds, and the only
# mode that proves anything about the submission. The two CAN disagree: a
# dependency bump in HEAD is invisible to a manifest still pinned to an older
# tag, so every default build stays green while the submission build fails.
# LOCAL=0 is the pre-submit path.
#
# NOTE: a git source builds COMMITTED state -- commit before a LOCAL build.
if [[ "${LOCAL:-1}" == "1" ]]; then
    BRANCH="$(git -C "$REPO" rev-parse --abbrev-ref HEAD)"
    MANIFEST="$HERE/.local-manifest.yml"
    REPO="$REPO" BRANCH="$BRANCH" SRC="$HERE/${APP_ID}.yml" OUT="$MANIFEST" \
        "${PYTHON:-python3}" - <<'PY'
import os, sys, yaml
m = yaml.safe_load(open(os.environ["SRC"]))
repo, branch = os.environ["REPO"], os.environ["BRANCH"]
rewritten = 0
for mod in m["modules"]:
    if isinstance(mod, dict) and mod.get("name") == "perch":
        mod["sources"] = [{"type": "git", "url": f"file://{repo}", "branch": branch}]
        rewritten += 1
# Rename or nest the module and the rewrite matches nothing: the script would
# print its LOCAL banner and build the PINNED TAG instead of the working tree.
if rewritten != 1:
    sys.exit(f"manifest rewrite matched {rewritten} 'perch' modules, expected 1")
yaml.safe_dump(m, open(os.environ["OUT"], "w"), sort_keys=False)
PY
    echo ">> LOCAL build: perch source = file://$REPO @ $BRANCH (HEAD)"
else
    echo ">> SUBMISSION build: manifest verbatim (pinned tag + commit)"
fi

# flatpak-builder clones the git source and runs `git lfs install` in the
# clone. On a machine with a global core.hooksPath (this one uses
# ~/.claude/githooks for the push gate), that clone inherits the hooks
# directory, git-lfs finds a pre-push hook it did not write, refuses to
# overwrite it, and the module fails with exit 2 -- nothing to do with the
# manifest. Neutralising the global git config for the build subprocesses
# avoids it. Flathub's builders have no such global config, so this is a
# local-environment fix and changes nothing about what is built.
#
# The caveat: it also hides global git identity and proxy settings from the
# build. Nothing here commits or fetches through a proxy, so that is free
# today; a module that needed either would have to narrow this.
export GIT_CONFIG_GLOBAL=/dev/null

echo ">> flatpak-builder: build (offline; all sources pinned)"
flatpak-builder \
    --user --force-clean --disable-rofiles-fuse \
    --repo="$REPODIR" \
    "$BUILDDIR" "$MANIFEST"

echo ">> install --user from the local repo"
flatpak-builder --user --force-clean --install \
    "$BUILDDIR" "$MANIFEST"

# --- Smoke. Two checks, because they fail differently. -----------------------
# `--check-config` returns BEFORE any Qt import (see src/perch/__main__.py), so
# on its own it proves the config layer and nothing about Qt. The import check
# is what catches a Qt wheel whose shared-library dependencies the runtime does
# not ship -- an ImportError before any window appears, which is the failure
# mode a display-less build cannot otherwise see.
echo ">> smoke 1/2: perch --version and --check-config"
flatpak run --command=perch "$APP_ID" --version
flatpak run --command=perch "$APP_ID" --check-config

echo ">> smoke 2/2: the runtime imports resolve inside the sandbox"
flatpak run --command=python3 "$APP_ID" -c \
    'import PySide6.QtWidgets, qasync, sdbus, Xlib, tomlkit; print("PERCH_IMPORTS_OK")'

cat <<'EOT'

>> Build + smoke green.

   Manual checks a headless build cannot make (do these before submitting):
     - tray icon appears on a real Plasma session, and its menu opens
     - the KWin script installs to ~/.local/share/kwin/scripts/ on first run
     - a window's geometry is remembered and restored across a close/reopen
     - the config dialog opens and saves

   Run the GUI with: packaging/flathub/flatpak-build.sh --run
EOT

if [[ "${1:-}" == "--run" ]]; then
    echo ">> launching"
    flatpak run "$APP_ID"
fi
