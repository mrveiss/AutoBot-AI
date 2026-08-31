#!/bin/bash
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# Session Stop Orphan Check
# Two kinds of orphan, deliberately handled differently:
#   main tree  — commits not linked to a GitHub issue; auto-creates one
#   worktree   — commits the PR base never received; reported, never filed
# The branch is already the record for parked work, so filing there would add
# backlog without adding closure.
# Called by Claude Code Stop hook.
#
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss

set -euo pipefail

# shellcheck source=scripts/lib/git-root.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/../lib/git-root.sh" || exit 0

cd "$(git_repo_root)" || exit 0

# Skip if a git operation is in progress (race condition with in-progress commits)
if [ -f "$(git rev-parse --git-dir 2>/dev/null)/index.lock" ]; then
  exit 0
fi

BRANCH=$(git branch --show-current 2>/dev/null || echo "unknown")

# The branch PRs target, which is not necessarily the remote default branch.
# Best-effort: the candidate list is a guess, not the branch's real PR target.
# `gh pr view --json baseRefName` would be authoritative but costs an API call
# before we know a PR exists at all. For a branch stacked on another unmerged
# branch this inflates the reported commit count; it never causes a false report.
pr_base() {
  local candidate
  for candidate in "${ORPHAN_CHECK_BASE:-}" Dev_new_gui develop main master; do
    [ -n "$candidate" ] || continue
    if git rev-parse --verify --quiet "origin/$candidate" >/dev/null 2>&1; then
      printf 'origin/%s' "$candidate"
      return 0
    fi
  done
  return 1
}

# A worktree branch carrying commits the base never received. Surfaced, never
# filed: an auto-filed issue would add backlog while closing nothing, and the
# branch already records the work.
report_parked_branch() {
  local base ahead dirty pr_states
  # Detached HEAD prints nothing and exits 0, so the "unknown" fallback at the
  # BRANCH assignment never fires — the empty case has to be caught here.
  if [ -z "$BRANCH" ] || [ "$BRANCH" = "unknown" ]; then
    return 0
  fi
  base=$(pr_base) || return 0

  ahead=$(git rev-list --count "$base"..HEAD 2>/dev/null || echo 0)
  dirty=$(git status --porcelain 2>/dev/null \
    | grep -cvE '(node_modules|__pycache__|\.pyc|dist/)' || true)
  case "$ahead" in ''|*[!0-9]*) ahead=0 ;; esac
  case "$dirty" in ''|*[!0-9]*) dirty=0 ;; esac
  # Commits ahead is the parked-work signal. A merely dirty tree is normal
  # mid-task state and fires on every Stop, so it is an addendum, never a cause.
  [ "$ahead" -gt 0 ] || return 0

  # One request, not two: this runs on every Stop of an active worktree session.
  # A non-zero exit means gh is offline, unauthenticated, or rate-limited — that
  # is inconclusive, not "no PR", and guessing would report work that has landed.
  pr_states=$(gh pr list --head "$BRANCH" --state all --limit 20 --json state \
    --jq '.[].state' 2>/dev/null) || return 0

  # MERGED means these commits are rebase leftovers; OPEN means it is already in
  # the pipeline. A closed-unmerged PR leaves the work parked, so it still reports.
  if printf '%s\n' "$pr_states" | grep -qxE 'MERGED|OPEN'; then
    return 0
  fi

  echo "PARKED WORK on $BRANCH: $ahead commit(s) ahead of $base, no PR open."
  # `|| true` is load-bearing under `set -e`: a false test in a `&&` list that
  # ends a function aborts the whole hook at the call site, silently.
  [ "$dirty" -gt 0 ] && echo "  plus $dirty uncommitted path(s)." || true
  echo "  Finished work returns nothing until it lands. Open a PR for it,"
  echo "  or rank what to land next:  ~/.claude/scripts/drain-parked.sh"
}

# Inside a worktree this used to exit immediately — blind to the case that
# actually costs work, since every code-touching task runs in a worktree.
GIT_COMMON_DIR="$(git rev-parse --git-common-dir 2>/dev/null)"
ACTUAL_GIT_DIR="$(git rev-parse --git-dir 2>/dev/null)"
if [ "$GIT_COMMON_DIR" != "$ACTUAL_GIT_DIR" ]; then
  report_parked_branch
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
