#!/bin/bash
# Session Stop Orphan Check
# Detects work not linked to a GitHub issue and auto-creates one.
# Called by Claude Code Stop hook.
#
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss

set -euo pipefail

cd "$(git rev-parse --show-toplevel 2>/dev/null)" || exit 0

BRANCH=$(git branch --show-current 2>/dev/null || echo "unknown")

# Whitelisted commit prefixes that don't need issue refs
WHITELIST="^(docs|chore|style|ci|merge|Merge)"

# 1. Find commits from last 8 hours without #NNN issue references
ORPHAN_COMMITS=$(git log --oneline --since="8 hours ago" \
  --author="$(git config user.name 2>/dev/null || echo '.')" 2>/dev/null \
  | grep -vE '#[0-9]{3,}' \
  | grep -vE "$WHITELIST" \
  || true)

# 2. Check for uncommitted changes (staged + unstaged + untracked in src dirs)
UNCOMMITTED=$(git status --porcelain 2>/dev/null \
  | grep -E '^\s*(M|A|D|R|\?\?)' \
  | grep -vE '(node_modules|__pycache__|\.pyc|dist/|\.claude/|\.git/)' \
  | head -20 \
  || true)

# 3. If nothing found, clean exit
if [ -z "$ORPHAN_COMMITS" ] && [ -z "$UNCOMMITTED" ]; then
  exit 0
fi

# 4. Build issue body
BODY="## Orphaned Work Detected

This issue was auto-created by the session-stop orphan check because work was found that is not linked to any GitHub issue.

**Branch:** \`$BRANCH\`
**Detected at:** $(date -Iseconds)
"

if [ -n "$ORPHAN_COMMITS" ]; then
  BODY+="
### Commits without issue references

\`\`\`
$ORPHAN_COMMITS
\`\`\`
"
fi

if [ -n "$UNCOMMITTED" ]; then
  BODY+="
### Uncommitted changes

\`\`\`
$UNCOMMITTED
\`\`\`
"
fi

BODY+="
### Action Required

Review this work and either:
1. Link it to an existing issue by amending commit messages
2. Continue the work in a new session referencing this issue
3. Close if the work was intentional and already tracked elsewhere
"

# 5. Create the issue
TITLE="Orphaned work on $BRANCH: $(echo "$ORPHAN_COMMITS $UNCOMMITTED" | head -1 | cut -c1-60)"

ISSUE_URL=$(gh issue create \
  --title "$TITLE" \
  --body "$BODY" \
  --label "orphaned-work" \
  2>&1) || {
  # If label doesn't exist or gh fails, try without label
  ISSUE_URL=$(gh issue create \
    --title "$TITLE" \
    --body "$BODY" \
    2>&1) || {
    echo "WARNING: Could not create GitHub issue for orphaned work"
    echo "Orphan commits: $ORPHAN_COMMITS"
    echo "Uncommitted: $UNCOMMITTED"
    exit 0
  }
}

echo "ORPHANED WORK DETECTED - Created issue: $ISSUE_URL"
echo "Review and link this work before starting a new session."
