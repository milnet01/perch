#! /bin/bash
# AppImage entry point (python-appimage template). Runs BEFORE launching the
# bundled interpreter, so it is where we widen the library search path.
#
#   perch-runtime-libs  the system libs harvested from AlmaLinux 8 that the
#                       Qt xcb platform plugin + glib/dbus stack need but that
#                       a bare desktop may not ship (xcb-util*, xkbcommon,
#                       glvnd EGL/GL dispatchers, ...). See build.sh.
#   usr/lib             where the manylinux base keeps the interpreter's own
#                       libs (libffi, libssl, ...); our harvested libs link
#                       against some of these, so it must be on the path too.
#
# Every child inherits LD_LIBRARY_PATH, so a HOST program Perch spawns (browser,
# file manager, compositor CLI) would be resolved against the bundled AlmaLinux 8
# libraries. Record what the host had first; src/perch/hostenv.py restores it for
# those spawns.
export PERCH_HOST_LD_LIBRARY_PATH="${LD_LIBRARY_PATH:-}"
# {{ python-executable }} expands to ${APPDIR}/usr/bin/python3.<minor>.
export LD_LIBRARY_PATH="${APPDIR}/usr/lib/perch-runtime-libs:${APPDIR}/usr/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
"{{ python-executable }}" -m perch "$@"
