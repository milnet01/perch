#!/usr/bin/env bash
# generate-pip-sources.sh — regenerate packaging/flathub/python3-deps.yaml.
#
# Flathub's builders have NO network, so every dependency must arrive as a
# sha256-pinned source. This emits that closure. Re-run it whenever
# [project.dependencies] in pyproject.toml changes, and commit the result --
# a manifest whose dep includes are generated at submission time cannot be
# built, reviewed, or reproduced by anyone else.
#
#   packaging/flathub/generate-pip-sources.sh
#
# Choices, and why each one:
#   * Deps come from pyproject.toml's [project.dependencies], the single
#     source of truth, MINUS PySide6 -- io.qt.PySide.BaseApp supplies PySide6
#     and Qt, and flatpak-pip-generator refuses to pin PySide6 for exactly
#     that reason. Perch itself is not included; the manifest's own module
#     pip-installs it from its git clone.
#   * --runtime runs pip inside org.kde.Sdk so the wheels match that Sdk's
#     python ABI. A wheel built for the wrong ABI installs and then fails to
#     import, which is the expensive way to find out.
#   * --prefer-wheels is DERIVED from a resolver dry run, never hand-listed.
#     The generator errors on a --prefer-wheels package that ships no wheel,
#     so the list must be the has-a-wheel subset; deriving it means a new
#     sdist-only dependency needs no edit here.
#   * --wheel-arches is x86_64 only, matching flathub.json's only-arches.
#     aarch64 is a follow-up: it needs the whole closure re-resolved for that
#     arch, and sdbus is the one native package in it.
#
# Requires: flatpak with org.kde.Sdk//6.11, and an interpreter carrying
# `requirements-parser` and `PyYAML` (the generator's own dependencies).
# Network is needed HERE; the build it feeds is offline.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$HERE/../.." && pwd)"
RUNTIME_BRANCH="${RUNTIME_BRANCH:-6.11}"
SDK="org.kde.Sdk//${RUNTIME_BRANCH}"
GENERATOR="${GENERATOR:-$HERE/.flatpak-pip-generator.py}"
# Pinned to a commit, not `master`: this script downloads and EXECUTES the file,
# so a moving ref means every run can execute different unreviewed code. Bump the
# ref deliberately, then re-run with REFETCH=1.
GEN_REF="${GEN_REF:-dda10aa5949811589747e6e485da6ae2e86b5d2b}"
GEN_URL="https://raw.githubusercontent.com/flatpak/flatpak-builder-tools/${GEN_REF}/pip/flatpak-pip-generator.py"

# The generator runs on the HOST interpreter (it only queries the Sdk for
# platform tags). Prefer an active venv, else the project's, else python3 --
# a distro python3 is usually PEP-668 externally-managed and cannot take the
# requirements-parser install.
PYGEN="${PYGEN:-${VIRTUAL_ENV:+$VIRTUAL_ENV/bin/python}}"
PYGEN="${PYGEN:-$REPO/.venv/bin/python}"
[[ -x "$PYGEN" ]] || PYGEN="python3"

cd "$REPO"

# Both are flatpak-pip-generator's own imports. Checked together so a fresh
# machine gets one complete instruction rather than discovering the second
# only after fixing the first.
MISSING=()
"$PYGEN" -c "import requirements" 2>/dev/null || MISSING+=(requirements-parser)
"$PYGEN" -c "import yaml" 2>/dev/null || MISSING+=(PyYAML)
if ((${#MISSING[@]})); then
    echo "!! '$PYGEN' lacks flatpak-pip-generator's dependencies: ${MISSING[*]}" >&2
    echo "   Install them into that interpreter:" >&2
    echo "     .venv/bin/python -m pip install ${MISSING[*]}" >&2
    exit 1
fi

if [[ "${REFETCH:-0}" == "1" || ! -f "$GENERATOR" ]]; then
    echo ">> fetching flatpak-pip-generator @ $GEN_REF"
    # -f so an HTTP error page is not cached as the generator and then executed.
    curl -fsSL --connect-timeout 10 --max-time 120 -o "$GENERATOR" "$GEN_URL" || {
        rm -f "$GENERATOR"
        echo "!! could not fetch $GEN_URL" >&2
        exit 1
    }
fi

if ! flatpak info "$SDK" >/dev/null 2>&1; then
    echo "!! $SDK is not installed -- flatpak install flathub $SDK" >&2
    exit 1
fi

# Runtime deps from pyproject, minus PySide6 (the BaseApp's job), PLUS the
# build backend. The backend is needed because the manifest pip-installs
# Perch with --no-build-isolation: with isolation on, pip would fetch
# hatchling from PyPI, and the Flathub builder has no network. Reading it
# from [build-system].requires keeps pyproject the single source of truth,
# so changing backends needs no edit here.
mapfile -t DEPS < <("$PYGEN" -c "
import tomllib
with open('pyproject.toml','rb') as f:
    data = tomllib.load(f)
for d in data['project']['dependencies']:
    if not d.lower().startswith('pyside6'):
        print(d)
for d in data['build-system']['requires']:
    print(d)
")
echo ">> ${#DEPS[@]} deps from pyproject.toml (runtime minus PySide6, plus build backend)"

echo ">> resolving closure to derive --prefer-wheels (has-a-wheel subset)"
PREFER="$("$PYGEN" -m pip install --dry-run --ignore-installed --quiet \
    --report /dev/stdout "${DEPS[@]}" \
    | "$PYGEN" -c "
import json, sys
report = json.load(sys.stdin)
wheels, sdists = [], []
for p in report['install']:
    name = p['metadata']['name']
    url = p.get('download_info', {}).get('url', '')
    (wheels if url.endswith('.whl') else sdists).append(name)
print(','.join(sorted(wheels)))
print('SDIST-ONLY:', ','.join(sorted(sdists)) or '(none)', file=sys.stderr)
")"
echo ">> prefer-wheels (has a wheel): ${PREFER:-(none)}"

echo ">> running flatpak-pip-generator inside $SDK"
rm -f "$HERE/python3-deps.yaml"
"$PYGEN" "$GENERATOR" \
    --runtime="$SDK" \
    ${PREFER:+--prefer-wheels="$PREFER"} \
    --wheel-arches=x86_64 \
    --yaml \
    -o "$HERE/python3-deps" \
    "${DEPS[@]}"

# The generator can exit 0 without writing (its restricted-module refusal
# path), so never take the exit code as proof.
if [[ ! -f "$HERE/python3-deps.yaml" ]]; then
    echo "!! generator produced no python3-deps.yaml -- see its output above" >&2
    exit 1
fi
echo ">> wrote $HERE/python3-deps.yaml ($(grep -c 'sha256' "$HERE/python3-deps.yaml") pinned sources)"
echo ">> review the diff, then build: packaging/flathub/flatpak-build.sh"
