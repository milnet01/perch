#!/usr/bin/env bash
# docs-drift-check.sh — Stop hook.
#
# Enforces Perch's hard "no documentation debt" rule (see CLAUDE.md, CONTRIBUTING.md):
# if this turn modified code but not docs, remind Claude before finishing.
#
# Silent when there's no drift. Never blocks — only reminds.

set -euo pipefail

cd "${CLAUDE_PROJECT_DIR:-.}" 2>/dev/null || exit 0

# Phase 0–3: no git repo yet, no src/ tree. Nothing to enforce.
git rev-parse --git-dir >/dev/null 2>&1 || exit 0

# Look at uncommitted changes (staged + unstaged, excluding untracked — those
# are often scratch files or research output we don't want to require doc updates for).
diff_files=$(git diff HEAD --name-only 2>/dev/null || true)

[ -z "$diff_files" ] && exit 0

code_changed=$(echo "$diff_files" | grep -E '^(src/perch/|perch/|data/)' || true)
docs_changed=$(echo "$diff_files" | grep -E '^docs/' || true)
claude_changed=$(echo "$diff_files" | grep -E '^CLAUDE\.md$' || true)

# If code changed and neither docs nor CLAUDE.md did, emit a reminder.
if [ -n "$code_changed" ] && [ -z "$docs_changed" ] && [ -z "$claude_changed" ]; then
    cat <<EOF
[docs-drift-check] Heads up: this turn modified code but not docs.

Changed code paths:
$(echo "$code_changed" | sed 's/^/  /')

Perch's hard rule (CLAUDE.md, CONTRIBUTING.md): docs/ must match code at
every commit. Before finishing, confirm one of:
  1. The relevant docs/ file has been updated in this turn, OR
  2. The change is purely internal (no behavior change) and no doc applies, OR
  3. You opened a tracking TODO for the doc update in a follow-up turn.

If (1), ignore this reminder. If (2) or (3), say so explicitly to the user.
EOF
fi

exit 0
