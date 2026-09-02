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

# Scope: work that has not left this machine yet -- uncommitted changes plus any
# commits ahead of the upstream. Looking at the working tree alone went silent
# the moment the turn committed, which is the normal flow and the case that
# matters. Untracked files stay excluded (scratch files, research output).
diff_files=$(git diff HEAD --name-only 2>/dev/null || true)
if git rev-parse --abbrev-ref --symbolic-full-name '@{upstream}' >/dev/null 2>&1; then
    diff_files=$(printf '%s\n%s\n' "$diff_files" \
        "$(git diff '@{upstream}..HEAD' --name-only 2>/dev/null || true)" | sort -u)
fi
diff_files=$(echo "$diff_files" | sed '/^$/d')

[ -z "$diff_files" ] && exit 0

code_changed=$(echo "$diff_files" | grep -E '^(src/perch/|perch/|data/)' || true)
docs_changed=$(echo "$diff_files" | grep -E '^docs/' || true)
claude_changed=$(echo "$diff_files" | grep -E '^CLAUDE\.md$' || true)

# If code changed and neither docs nor CLAUDE.md did, emit a reminder.
if [ -n "$code_changed" ] && [ -z "$docs_changed" ] && [ -z "$claude_changed" ]; then
    cat <<EOF
[docs-drift-check] Heads up: unpushed work modifies code but not docs.

Changed code paths:
$(echo "$code_changed" | sed 's/^/  /')

Perch's hard rule (CLAUDE.md, CONTRIBUTING.md): docs/ must match code at
every commit. Before finishing, confirm one of:
  1. The relevant docs/ file has been updated alongside this code, OR
  2. The change is purely internal (no behavior change) and no doc applies.

Deferring the doc update to a later turn is not an option -- the rule forbids
documentation debt by name. If (1), ignore this reminder. If (2), say so
explicitly to the user.
EOF
fi

exit 0
