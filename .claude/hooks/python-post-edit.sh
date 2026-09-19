#!/usr/bin/env bash
# python-post-edit.sh — PostToolUse hook for Edit/Write.
#
# When a .py file is edited or written, run ruff check (report-only, no --fix)
# so Claude sees any issues in the next tool result instead of discovering them
# later in CI. Silent on success.
#
# No-op outside the project root, outside Python files, or when ruff isn't
# installed (e.g. before M1 creates the dev venv). Without jq it cannot read
# the payload at all, so it says so on stderr instead of going silent.

set -euo pipefail

cd "${CLAUDE_PROJECT_DIR:-.}" 2>/dev/null || exit 0

if ! command -v jq >/dev/null 2>&1; then
    echo "[python-post-edit] jq not installed; post-edit ruff check skipped" >&2
    exit 0
fi

# Parse the hook payload (JSON on stdin) for the edited file path.
file_path=$(jq -r '.tool_input.file_path // empty' 2>/dev/null || true)

[ -z "$file_path" ] && exit 0
[[ "$file_path" == *.py ]] || exit 0
[ -f "$file_path" ] || exit 0
[ -f pyproject.toml ] || exit 0

# Only run if ruff is reachable. Before M1's dev env exists, ruff may be absent
# from PATH — that's fine, silent no-op.
command -v ruff >/dev/null 2>&1 || exit 0

# Report-only. Don't --fix; mutating files mid-hook confuses the edit history.
# Keep output tight: if clean, say nothing.
if ! output=$(ruff check "$file_path" 2>&1); then
    echo "[python-post-edit] ruff flagged issues in $file_path:"
    echo "$output" | sed 's/^/  /'
fi

exit 0
