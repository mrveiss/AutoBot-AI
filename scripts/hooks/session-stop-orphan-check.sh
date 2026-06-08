#!/bin/bash
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# Session Stop Orphan Check
# Detects work not linked to a GitHub issue and auto-creates one.
# Called by Claude Code Stop hook.
#
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss

set -euo pipefail

cd "$(git rev-parse --show-toplevel 2>/dev/null)" || exit 0

# Skip if a git operation is in progress (race condition with in-progress commits)
if [ -f "$(git rev-parse --git-dir 2>/dev/null)/index.lock" ]; then
  exit 0
fi

BRANCH=$(git branch --show-current 2>/dev/null || echo "unknown")

# Skip if we're inside a worktree (worktrees are actively used for parallel work)
GIT_COMMON_DIR="$(git rev-parse --git-common-dir 2>/dev/null)"
ACTUAL_GIT_DIR="$(git rev-parse --git-dir 2>/dev/null)"
if [ "$GIT_COMMON_DIR" != "$ACTUAL_GIT_DIR" ]; then
  exit 0
fi

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

# 3b. Skip if this branch already has a merged PR (stale false positive)
MERGED_PR=$(gh pr list --head "$BRANCH" --state merged --json number --jq '.[0].number // empty' 2>/dev/null || true)
if [ -n "$MERGED_PR" ]; then
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

# 5. Deduplicate: check for existing open orphan issue on this branch
EXISTING_ISSUE=$(gh issue list \
  --label "orphaned-work" \
  --state open \
  --search "Orphaned work on $BRANCH" \
  --json number,title \
  --jq ".[0].number // empty" \
  2>/dev/null || true)

if [ -n "$EXISTING_ISSUE" ]; then
  # Update existing issue with a comment instead of creating duplicate
  COMMENT="## Updated Orphan Detection

**Detected at:** $(date -Iseconds)
"
  if [ -n "$ORPHAN_COMMITS" ]; then
    COMMENT+="
### Current orphaned commits
\`\`\`
$ORPHAN_COMMITS
\`\`\`
"
  fi
  if [ -n "$UNCOMMITTED" ]; then
    COMMENT+="
### Current uncommitted changes
\`\`\`
$UNCOMMITTED
\`\`\`
"
  fi

  gh issue comment "$EXISTING_ISSUE" --body "$COMMENT" 2>/dev/null || true
  echo "ORPHANED WORK DETECTED - Updated existing issue: #$EXISTING_ISSUE"
  exit 0
fi

# 6. No existing issue — create a new one
TITLE="Orphaned work on $BRANCH"

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
