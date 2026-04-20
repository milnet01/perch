#!/usr/bin/env bash
# Re-extract translatable strings into translations/perch_<locale>.ts.
#
# Run after adding or changing any user-visible string. The generated
# files are XML; commit them alongside the source change per the no-doc-
# debt rule — translators merge their own ``translation`` elements later.
#
# Compile to .qm at install time with ``pyside6-lrelease``; see
# ``docs/08-ui.md`` §Localization.

set -eu

cd "$(dirname "$0")/.."

pyside6-lupdate -extensions py src/perch \
    -ts translations/perch_en.ts \
    -source-language en_US \
    "$@"

echo "done — run 'pyside6-lrelease translations/*.ts' to produce .qm files"
