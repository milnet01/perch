#!/usr/bin/env bash
# build.sh — build a self-contained Perch AppImage: download → chmod +x → run,
# with NO dependencies for the user to install. Everything the GUI needs (the
# Python interpreter, PySide6/Qt, and the xcb/glib/glvnd system libraries) is
# bundled inside the single .AppImage file.
#
# Strategy
#   1. Build the perch wheel.
#   2. python-appimage assembles an AppDir around a portable manylinux_2_28
#      interpreter (glibc 2.28 floor → runs on Ubuntu 20.04+, Debian 10+,
#      Fedora, openSUSE, ...) with perch + its deps pip-installed in.
#   3. harvest-libs.sh (in an AlmaLinux 8 container) bundles the system libs the
#      Qt xcb plugin needs but that python-appimage leaves out — sourced from
#      old glibc so they stay portable. See that script for the why.
#   4. appimagetool packs the AppDir into the final single file.
#
# Requirements: python3, podman (or docker), and network access for pip + the
# base image. The AppImage runtime stub is fetched from GitHub; if that is
# unreachable (some networks stall on the release CDN), point
#   PERCH_APPIMAGE_RUNTIME=/path/to/runtime-x86_64
# at a local copy and the download is skipped. In GitHub Actions the download
# just works — this is the intended CI build (see .github/workflows/).
#
# Env knobs:
#   PYTHON_VERSION   interpreter minor to bundle (default 3.12)
#   CONTAINER        container engine (default: podman, else docker)
#   PERCH_APPIMAGE_RUNTIME  local AppImage runtime stub to use instead of fetching
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
REPO="$(cd "$HERE/../.." && pwd)"
PYVER="${PYTHON_VERSION:-3.12}"
MANYLINUX_TAG="manylinux_2_28_x86_64"      # glibc 2.28 floor; bump in lockstep with docs/10-packaging.md
CONTAINER="${CONTAINER:-$(command -v podman || command -v docker)}"
[[ -n "$CONTAINER" ]] || { echo "ERROR: need podman or docker" >&2; exit 1; }

VERSION="$(cd "$REPO" && python3 -c 'import tomllib,sys; print(tomllib.load(open("pyproject.toml","rb"))["project"]["version"])')"
OUT="Perch-${VERSION}-x86_64.AppImage"
DIST="$REPO/dist"; mkdir -p "$DIST"      # dist/ is gitignored
WORK="$(mktemp -d)"; trap 'rm -rf "$WORK"' EXIT
echo ">> Perch $VERSION  ->  dist/$OUT  (workdir $WORK)"

# 1. wheel ---------------------------------------------------------------------
echo ">> [1/5] building wheel"
python3 -m pip wheel "$REPO" --no-deps -w "$WORK/wheels" >/dev/null
WHEEL="$(ls "$WORK/wheels"/perch-*.whl)"

# 2. AppDir via python-appimage ------------------------------------------------
echo ">> [2/5] assembling AppDir (python-appimage, $MANYLINUX_TAG, cp$PYVER)"
python3 -m venv "$WORK/bvenv"
"$WORK/bvenv/bin/pip" install -q --upgrade pip python-appimage
RECIPE="$WORK/recipe"; mkdir -p "$RECIPE"
cp "$HERE/perch.desktop" "$HERE/entrypoint.sh" "$RECIPE/"
cp "$REPO/data/icons/hicolor/scalable/apps/io.github.milnet01.Perch.svg" "$RECIPE/perch.svg"
echo "$WHEEL" > "$RECIPE/requirements.txt"
( cd "$WORK" && "$WORK/bvenv/bin/python" -m python_appimage build app \
    --no-packaging -l "$MANYLINUX_TAG" -p "$PYVER" -n Perch "$RECIPE" )
APPDIR="$WORK/Perch-x86_64"
[[ -d "$APPDIR" ]] || { echo "ERROR: AppDir not produced" >&2; exit 1; }

# 3. harvest + fold portable system libs ---------------------------------------
echo ">> [3/5] harvesting portable Qt/xcb system libs (AlmaLinux 8)"
HARV="$WORK/harvested"; mkdir -p "$HARV"
cp "$HERE/harvest-libs.sh" "$WORK/harvest.sh"   # mount a copy so the repo file's SELinux label is untouched
# :z relabels the bind mounts for container access on SELinux-enforcing hosts
# (harmless no-op elsewhere); without it the container cannot read/exec them.
"$CONTAINER" run --rm \
  -v "$APPDIR":/appdir:ro,z -v "$HARV":/out:z -v "$WORK/harvest.sh":/harvest.sh:ro,z \
  almalinux:8 bash /harvest.sh
mkdir -p "$APPDIR/usr/lib/perch-runtime-libs"
cp -a "$HARV/." "$APPDIR/usr/lib/perch-runtime-libs/"

# 4. AppImage runtime stub -----------------------------------------------------
echo ">> [4/5] obtaining AppImage runtime"
RUNTIME="$WORK/runtime-x86_64"
if [[ -n "${PERCH_APPIMAGE_RUNTIME:-}" ]]; then
  cp "$PERCH_APPIMAGE_RUNTIME" "$RUNTIME"
  echo "   using PERCH_APPIMAGE_RUNTIME=$PERCH_APPIMAGE_RUNTIME"
else
  curl -fsSL --retry 3 --retry-delay 3 \
    https://github.com/AppImage/type2-runtime/releases/download/continuous/runtime-x86_64 \
    -o "$RUNTIME"
fi
chmod +x "$RUNTIME"

# 5. pack ----------------------------------------------------------------------
echo ">> [5/5] packing $OUT"
"$WORK/bvenv/bin/python" - "$WORK" <<'PY'
import sys, subprocess
from python_appimage.utils.deps import ensure_appimagetool
print(ensure_appimagetool())   # extracts appimagetool into the cache; prints its AppRun
PY
AT="$($WORK/bvenv/bin/python -c 'from python_appimage.utils.deps import ensure_appimagetool; print(ensure_appimagetool())')"
env ARCH=x86_64 "$AT" --no-appstream --runtime-file "$RUNTIME" "$APPDIR" "$DIST/$OUT"

# smoke test -------------------------------------------------------------------
echo ">> smoke test: $OUT --version"
"$DIST/$OUT" --appimage-extract-and-run --version
echo ">> done: $DIST/$OUT"
