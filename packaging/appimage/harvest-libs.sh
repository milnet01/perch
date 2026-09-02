#!/bin/bash
# harvest-libs.sh — runs INSIDE an AlmaLinux 8 container (glibc 2.28, the same
# baseline the python-appimage manylinux_2_28 interpreter was built on).
#
# Why this exists: python-appimage bundles the interpreter + PySide6 wheel, but
# NOT the system shared libraries the Qt "xcb" platform plugin and the glib/dbus
# stack dlopen at runtime (libxcb-cursor, libxkbcommon-x11, the glvnd EGL/GL
# dispatchers, ...). A bare desktop may not ship those, so Perch's window would
# fail with "could not load the Qt platform plugin xcb". We must bundle them —
# and they must come from an OLD-glibc environment or they would themselves fail
# on older targets. Hence: harvest here, not from the (newer) build host.
#
# It computes the full ldd closure over every bundled .so, then copies each
# resolved SYSTEM lib that is not on the host-provided EXCLUDE set. build.sh
# folds the result into AppDir/usr/lib/perch-runtime-libs.
#
# Mounts (set by build.sh): /appdir = the AppDir (ro), /out = output dir.
set -euo pipefail

# A failure here leaves the container without the libs, ldd resolves nothing,
# and the harvest is silently empty -- which ships as an AppImage that dies with
# "could not load the Qt platform plugin xcb". So these must NOT be tolerated.
dnf -y -q install epel-release
dnf -y -q install \
    libxcb libX11 libX11-xcb libXau libxkbcommon libxkbcommon-x11 \
    xcb-util xcb-util-image xcb-util-keysyms xcb-util-renderutil xcb-util-wm \
    fontconfig freetype libpng dbus-libs \
    libglvnd libglvnd-egl libglvnd-glx libglvnd-opengl \
    libffi openssl-libs bzip2-libs xz-libs sqlite-libs zlib expat \
    ncurses-libs readline gdbm-libs libtirpc
# xcb-util-cursor lives in EPEL on EL8; don't fail the whole run if it is absent.
dnf -y -q install xcb-util-cursor 2>/dev/null || echo "WARN: xcb-util-cursor unavailable" >&2

APPDIR=/appdir
OUT=/out
mkdir -p "$OUT"

# Resolve the interpreter's Python minor from the bundled tree (future-proof).
PYDIR=$(find "$APPDIR/opt" -maxdepth 1 -name 'python3.*' -type d -print -quit)
[[ -n "$PYDIR" ]] || { echo "ERROR: no python3.* under $APPDIR/opt" >&2; exit 1; }
PYVER=$(basename "$PYDIR")               # e.g. python3.12
SP="$PYDIR/lib/$PYVER/site-packages"

# Bundled lib dirs so ldd resolves the Qt/Python .so against the AppImage's own
# copies, leaving only genuine SYSTEM libs to resolve from the container.
export LD_LIBRARY_PATH="$SP/PySide6/Qt/lib:$SP/PySide6:$SP/shiboken6:$PYDIR/lib:$APPDIR/usr/lib"

# Host-provided sonames — glibc core, the GL/DRM driver stack, and the X core
# libs every X server already ships. These must NOT be bundled (bundling libGL
# or libX11 breaks hardware accel / conflicts with the live X server).
EXCLUDE=$(cat <<'EOF'
ld-linux-x86-64.so.2 libc.so.6 libdl.so.2 libm.so.6 libpthread.so.0 librt.so.1
libutil.so.1 libnsl.so.1 libresolv.so.2
libgcc_s.so.1 libstdc++.so.6
libGLU.so.1 libdrm.so.2 libglapi.so.0 libgbm.so.1
libX11.so.6 libxcb.so.1 libX11-xcb.so.1 libXext.so.6
EOF
)
is_excluded() { local s="$1"; for e in $EXCLUDE; do [[ "$s" == "$e" ]] && return 0; done; return 1; }

mapfile -t SOS < <(find "$APPDIR" \( -name '*.so' -o -name '*.so.*' \))
for so in "${SOS[@]}"; do
  ldd "$so" 2>/dev/null | awk '/=> \// {print $3}' || true
done | sort -u | while read -r path; do
  [[ -e "$path" ]] || continue
  case "$path" in "$APPDIR"/*) continue;; esac   # already inside the AppImage
  soname=$(basename "$path")
  is_excluded "$soname" && continue
  real=$(readlink -f "$path")
  cp -a "$real" "$OUT/$(basename "$real")"
  [[ "$(basename "$real")" != "$soname" ]] && ln -sf "$(basename "$real")" "$OUT/$soname" || true
done

# The host-provided contract: sonames the bundle deliberately does NOT carry,
# so build.sh's bare-container check knows which unresolved names are expected.
# shellcheck disable=SC2086  # EXCLUDE is a whitespace-separated list; splitting is the point
printf '%s\n' $EXCLUDE > "$OUT/host-provided.txt"

COUNT=$(find "$OUT" -name '*.so*' | wc -l)
# Zero means every ldd above resolved nothing -- a bundle with no system libs in
# it builds and packs cleanly and then fails on the user's machine.
[[ "$COUNT" -gt 0 ]] || { echo "ERROR: harvested 0 libraries" >&2; exit 1; }
echo "harvested $COUNT files into perch-runtime-libs"
