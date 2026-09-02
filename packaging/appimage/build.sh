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
echo ">> [1/6] building wheel"
python3 -m pip wheel "$REPO" --no-deps -w "$WORK/wheels" >/dev/null
WHEEL="$(ls "$WORK/wheels"/perch-*.whl)"

# 2. AppDir via python-appimage ------------------------------------------------
echo ">> [2/6] assembling AppDir (python-appimage, $MANYLINUX_TAG, cp$PYVER)"
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
echo ">> [3/6] harvesting portable Qt/xcb system libs (AlmaLinux 8)"
HARV="$WORK/harvested"; mkdir -p "$HARV"
cp "$HERE/harvest-libs.sh" "$WORK/harvest.sh"   # mount a copy so the repo file's SELinux label is untouched
# :z relabels the bind mounts for container access on SELinux-enforcing hosts
# (harmless no-op elsewhere); without it the container cannot read/exec them.
"$CONTAINER" run --rm \
  -v "$APPDIR":/appdir:ro,z -v "$HARV":/out:z -v "$WORK/harvest.sh":/harvest.sh:ro,z \
  almalinux:8 bash /harvest.sh
HOSTLIST="$WORK/host-provided.txt"
mv "$HARV/host-provided.txt" "$HOSTLIST"     # a manifest, not a library to bundle
mkdir -p "$APPDIR/usr/lib/perch-runtime-libs"
cp -a "$HARV/." "$APPDIR/usr/lib/perch-runtime-libs/"

# 4. AppImage runtime stub -----------------------------------------------------
echo ">> [4/6] obtaining AppImage runtime"
RUNTIME="$WORK/runtime-x86_64"
if [[ -n "${PERCH_APPIMAGE_RUNTIME:-}" ]]; then
  cp "$PERCH_APPIMAGE_RUNTIME" "$RUNTIME"
  echo "   using PERCH_APPIMAGE_RUNTIME=$PERCH_APPIMAGE_RUNTIME"
else
  # --retry does not bound a stalled-but-open connection, which is the
  # documented failure here; the timeouts are what make it fail over.
  curl -fsSL --retry 3 --retry-delay 3 --connect-timeout 10 --max-time 180 \
    https://github.com/AppImage/type2-runtime/releases/download/continuous/runtime-x86_64 \
    -o "$RUNTIME"
fi
chmod +x "$RUNTIME"

# 5. pack ----------------------------------------------------------------------
echo ">> [5/6] packing $OUT"
# ensure_appimagetool() extracts appimagetool into the cache and returns its
# AppRun; one call does both.
AT="$($WORK/bvenv/bin/python -c 'from python_appimage.utils.deps import ensure_appimagetool; print(ensure_appimagetool())')"
env ARCH=x86_64 "$AT" --no-appstream --runtime-file "$RUNTIME" "$APPDIR" "$DIST/$OUT"

# 6. verify self-containment ---------------------------------------------------
# `--version` exits before touching Qt (see src/perch/__main__.py), so it proves
# nothing about the bundle's whole reason for existing. This does: extract the
# AppImage on a BARE ubuntu:22.04 (no Qt, no xcb-util, no xkbcommon) and require
# every bundled .so to resolve, except the sonames harvest-libs.sh deliberately
# leaves to the host. An unresolved name outside that set is a library we forgot
# to bundle -- i.e. an AppImage that dies with "could not load the Qt platform
# plugin xcb" on a machine that is not this one.
echo ">> [6/6] verifying self-containment (bare ubuntu:22.04)"
"$DIST/$OUT" --appimage-extract-and-run --version
"$CONTAINER" run --rm \
  -v "$DIST/$OUT":/perch.AppImage:ro,z -v "$HOSTLIST":/host-provided.txt:ro,z \
  ubuntu:22.04 bash -euo pipefail -c '
    cd /tmp && /perch.AppImage --appimage-extract >/dev/null
    APPDIR=/tmp/squashfs-root
    PYDIR=$(find "$APPDIR/opt" -maxdepth 1 -name "python3.*" -type d -print -quit)
    PYVER=$(basename "$PYDIR")
    SP="$PYDIR/lib/$PYVER/site-packages"
    # The same search path entrypoint.sh and harvest-libs.sh use, so this asks
    # what the AppImage itself would resolve at runtime.
    export LD_LIBRARY_PATH="$APPDIR/usr/lib/perch-runtime-libs:$APPDIR/usr/lib:$SP/PySide6/Qt/lib:$SP/PySide6:$SP/shiboken6:$PYDIR/lib"

    # Scope: what Perch actually loads. Qt also ships plugins for databases,
    # GTK dialogs, speech and a Wayland compositor whose dependencies are
    # deliberately absent -- Perch never loads them, so their unresolved
    # sonames are not evidence of anything.
    TARGETS="$SP/PySide6/Qt/plugins/platforms/libqxcb.so"
    for lib in Core Gui Widgets DBus; do
      TARGETS="$TARGETS $SP/PySide6/Qt/lib/libQt6$lib.so.6"
    done
    for t in $TARGETS; do
      [ -e "$t" ] || { echo "ERROR: $t is not in the bundle" >&2; exit 1; }
    done

    # shellcheck disable=SC2086
    ldd $TARGETS 2>/dev/null | awk "/not found/ {print \$1}" | sort -u > /tmp/unresolved.txt
    if comm -23 /tmp/unresolved.txt <(sort /host-provided.txt) | grep .; then
      echo "ERROR: the xcb platform plugin needs the sonames above, and they" >&2
      echo "       resolve from neither the bundle nor the documented" >&2
      echo "       host-provided set. Add them to harvest-libs.sh." >&2
      exit 1
    fi
    echo "   self-contained: the xcb plugin and Qt core resolve"
  '
echo ">> done: $DIST/$OUT"
