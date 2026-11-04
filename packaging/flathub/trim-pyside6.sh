#!/usr/bin/env bash
# trim-pyside6.sh — cut the PySide6-Essentials wheel down to what Perch loads.
#
# The wheel ships QML, Quick, Designer, the Qt tools and most of Qt's
# plugins. Perch imports QtCore, QtGui, QtWidgets and QtNetwork only, and
# draws through the wayland or xcb platform plugin. Everything else goes.
#
# Libraries, bindings and plugins are KEEP lists, so a module a future wheel
# adds is dropped by default rather than shipped by accident. flatpak-build.sh
# then checks with ldd that nothing kept needs a library this removed.
#
# Run by the manifest's perch module, from its git clone:
#   bash packaging/flathub/trim-pyside6.sh "$FLATPAK_DEST"
set -euo pipefail
shopt -s nullglob

sites=("$1"/lib/python3*/site-packages/PySide6)
[[ ${#sites[@]} -eq 1 && -d "${sites[0]}/Qt/lib" ]] || {
    echo "trim-pyside6: expected one PySide6 under $1/lib/python3*/site-packages" >&2
    exit 1
}
P="${sites[0]}"
Q="$P/Qt"

# Qt libraries: Perch's four modules; what they and the kept plugins link
# (DBus for the tray, Svg for the icon engine, OpenGL and the Wayland and
# xcb platform libraries); and ICU, which QtCore links.
for f in "$Q"/lib/*; do
    case "${f##*/}" in
        libicu*|libQt6Core.*|libQt6Gui.*|libQt6Widgets.*|libQt6Network.*) ;;
        libQt6DBus.*|libQt6Svg.*|libQt6OpenGL.*) ;;
        libQt6WaylandClient.*|libQt6WlShellIntegration.*|libQt6XcbQpa.*) ;;
        *) rm -rf "$f" ;;
    esac
done

# Python bindings: the four Perch imports, plus DBus and Svg.
for f in "$P"/Qt*.abi3.so "$P"/Qt*.pyi; do
    case "${f##*/}" in
        QtCore.*|QtGui.*|QtWidgets.*|QtNetwork.*|QtDBus.*|QtSvg.*) ;;
        *) rm -f "$f" ;;
    esac
done
rm -f "$P"/libpyside6qml.*

# Developer tools, headers and code generators: an app never runs them.
rm -rf "$P"/assistant "$P"/designer "$P"/linguist "$P"/lrelease \
    "$P"/lupdate "$P"/qmlformat "$P"/qmllint "$P"/qmlls "$P"/svgtoqml \
    "$P"/include "$P"/typesystems "$P"/glue "$P"/doc "$P"/scripts \
    "$Q"/libexec "$Q"/metatypes "$Q"/qml

# Plugins: the platform plugins and their Wayland and xcb integrations, the
# platform themes (the portal theme supplies the dark or light colour
# scheme), input methods, the SVG icon engine, image formats and TLS.
for d in "$Q"/plugins/*; do
    case "${d##*/}" in
        platforms|platformthemes|platforminputcontexts) ;;
        iconengines|imageformats|tls|xcbglintegrations) ;;
        wayland-decoration-client|wayland-graphics-integration-client) ;;
        wayland-shell-integration) ;;
        *) rm -rf "$d" ;;
    esac
done
for f in "$Q"/plugins/platforms/*; do
    case "${f##*/}" in
        libqwayland.so|libqxcb.so|libqoffscreen.so|libqminimal.so) ;;
        *) rm -f "$f" ;;
    esac
done
# These two link Qt modules removed above (Quick and QML, and Qt Pdf).
rm -f "$Q"/plugins/platforminputcontexts/libqtvirtualkeyboardplugin.so \
    "$Q"/plugins/imageformats/libqpdf.so

# Translations: Qt's own dialogs use qtbase_*; the rest serve removed tools.
for f in "$Q"/translations/*; do
    case "${f##*/}" in
        qtbase_*) ;;
        *) rm -f "$f" ;;
    esac
done
