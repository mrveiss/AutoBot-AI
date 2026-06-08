#!/usr/bin/env bash
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
#
# Cleanup stale git worktrees and branches whose GitHub issues are closed.
# Usage: scripts/cleanup-worktrees.sh [--dry-run] [--branches-only]
#
# Handles:
#   1. Worktrees under .worktrees/ for closed issues
#   2. Local branches (any prefix) for closed issues
#   3. Remote branches for closed issues (squash-merge aware)
#
# Fixes: #7104, #2508

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
WORKTREES_DIR="${REPO_ROOT}/.worktrees"
DRY_RUN=false
BRANCHES_ONLY=false
BASE_BRANCH="Dev_new_gui"

for arg in "$@"; do
    case "$arg" in
        --dry-run)
            DRY_RUN=true
            ;;
        --branches-only)
            BRANCHES_ONLY=true
            ;;
        --help|-h)
            echo "Usage: $0 [--dry-run] [--branches-only]"
            echo ""
            echo "Removes git worktrees and branches whose GitHub issues are closed."
            echo ""
            echo "Options:"
            echo "  --dry-run        Show what would be cleaned without making changes"
            echo "  --branches-only  Skip worktree cleanup, only clean branches"
            echo "  --help           Show this help message"
            exit 0
            ;;
        *)
            echo "Error: unknown argument '$arg'" >&2
            echo "Run '$0 --help' for usage." >&2
            exit 1
            ;;
    esac
done

if ! command -v gh &>/dev/null; then
    echo "Error: GitHub CLI (gh) is required but not found." >&2
    exit 1
fi

wt_removed=0
wt_skipped=0
br_local_removed=0
br_remote_removed=0
errors=0

# ---------- Phase 1: Worktree cleanup ----------

if ! $BRANCHES_ONLY; then
    echo "=== Phase 1: Worktree cleanup ==="

    if [ ! -d "$WORKTREES_DIR" ]; then
        echo "  No .worktrees/ directory found. Skipping."
    else
        if $DRY_RUN; then
            echo "  (dry-run mode -- no changes will be made)"
        fi
        echo ""

        for worktree_path in "$WORKTREES_DIR"/*/; do
            [ -d "$worktree_path" ] || continue

            dir_name="$(basename "$worktree_path")"

            # Extract issue number from directory name (e.g., issue-2467 -> 2467)
            if [[ "$dir_name" =~ issue-([0-9]+) ]]; then
                issue_number="${BASH_REMATCH[1]}"
            else
                echo "  SKIP  ${dir_name} -- cannot extract issue number"
                wt_skipped=$((wt_skipped + 1))
                continue
            fi

            # Check issue state via GitHub CLI
            issue_state=""
            issue_state=$(gh issue view "$issue_number" --json state --jq '.state' 2>/dev/null) || true

            if [ -z "$issue_state" ]; then
                echo "  ERROR ${dir_name} -- could not fetch state for issue #${issue_number}"
                errors=$((errors + 1))
                continue
            fi

            if [ "$issue_state" = "CLOSED" ]; then
                # Read actual branch name from worktree (not hardcoded prefix)
                branch_name=$(git -C "$worktree_path" branch --show-current 2>/dev/null) || true

                if $DRY_RUN; then
                    echo "  WOULD REMOVE  ${dir_name}  (issue #${issue_number} is closed, branch: ${branch_name:-unknown})"
                else
                    echo "  REMOVING      ${dir_name}  (issue #${issue_number} is closed)"
                    if git -C "$REPO_ROOT" worktree remove --force "$worktree_path" 2>/dev/null; then
                        # Delete local branch if it exists
                        if [ -n "$branch_name" ]; then
                            git -C "$REPO_ROOT" branch -D "$branch_name" 2>/dev/null && \
                                echo "    Deleted local branch: ${branch_name}" || true
                            # Delete remote branch if it exists
                            git -C "$REPO_ROOT" push origin --delete "$branch_name" 2>/dev/null && \
                                echo "    Deleted remote branch: ${branch_name}" || true
                        fi
                    else
                        echo "    WARNING: git worktree remove failed; attempting manual cleanup"
                        rm -rf "$worktree_path"
                        git -C "$REPO_ROOT" worktree prune
                    fi
                fi
                wt_removed=$((wt_removed + 1))
            else
                echo "  KEEP          ${dir_name}  (issue #${issue_number} is ${issue_state})"
                wt_skipped=$((wt_skipped + 1))
            fi
        done
    fi
    echo ""
fi

# ---------- Phase 2: Merged branch cleanup ----------

echo "=== Phase 2: Merged branch cleanup ==="
if $DRY_RUN; then
    echo "  (dry-run mode -- no changes will be made)"
fi

# Delete local branches already merged into base branch
merged_local=$(git -C "$REPO_ROOT" branch --merged "$BASE_BRANCH" \
    | grep -v "${BASE_BRANCH}\|main\|master" \
    | sed 's/^[* +]*//' || true)

if [ -n "$merged_local" ]; then
    while IFS= read -r branch; do
        [ -z "$branch" ] && continue
        if $DRY_RUN; then
            echo "  WOULD DELETE local merged: ${branch}"
        else
            git -C "$REPO_ROOT" branch -d "$branch" 2>/dev/null && \
                echo "  Deleted local merged: ${branch}" || \
                echo "  SKIP (in use by worktree): ${branch}"
        fi
        br_local_removed=$((br_local_removed + 1))
    done <<< "$merged_local"
else
    echo "  No merged local branches found."
fi
echo ""

# ---------- Phase 3: Orphaned branch cleanup ----------

echo "=== Phase 3: Orphaned branch cleanup (closed issues) ==="
if $DRY_RUN; then
    echo "  (dry-run mode -- no changes will be made)"
fi

# Fetch latest remote state
git -C "$REPO_ROOT" fetch --prune 2>/dev/null || true

# Check local branches with issue numbers for closed issues
local_branches=$(git -C "$REPO_ROOT" branch | sed 's/^[* +]*//' | grep -v "${BASE_BRANCH}\|main\|master" || true)

if [ -n "$local_branches" ]; then
    while IFS= read -r branch; do
        [ -z "$branch" ] && continue
        issue_number=$(echo "$branch" | grep -oP '\d{4,}' | head -1) || true
        [ -z "$issue_number" ] && continue

        issue_state=$(gh issue view "$issue_number" --json state --jq '.state' 2>/dev/null) || true
        if [ "$issue_state" = "CLOSED" ]; then
            # Verify work is merged (check for merged PR)
            merged_pr=$(gh pr list --search "$issue_number" --state merged --json number -q '.[0].number' 2>/dev/null) || true
            if [ -n "$merged_pr" ]; then
                if $DRY_RUN; then
                    echo "  WOULD DELETE local: ${branch}  (#${issue_number} closed, PR #${merged_pr} merged)"
                else
                    git -C "$REPO_ROOT" branch -D "$branch" 2>/dev/null && \
                        echo "  Deleted local: ${branch}  (#${issue_number} closed, PR #${merged_pr} merged)" || \
                        echo "  SKIP (in use by worktree): ${branch}"
                fi
                br_local_removed=$((br_local_removed + 1))
            else
                echo "  KEEP  ${branch}  (#${issue_number} closed but no merged PR found -- verify manually)"
            fi
        fi
    done <<< "$local_branches"
fi

# Check remote branches with issue numbers for closed issues
remote_branches=$(git -C "$REPO_ROOT" branch -r | sed 's|^ *origin/||' \
    | grep -v "HEAD\|${BASE_BRANCH}\|main\|master" || true)

if [ -n "$remote_branches" ]; then
    while IFS= read -r branch; do
        [ -z "$branch" ] && continue
        issue_number=$(echo "$branch" | grep -oP '\d{4,}' | head -1) || true
        [ -z "$issue_number" ] && continue

        issue_state=$(gh issue view "$issue_number" --json state --jq '.state' 2>/dev/null) || true
        if [ "$issue_state" = "CLOSED" ]; then
            merged_pr=$(gh pr list --search "$issue_number" --state merged --json number -q '.[0].number' 2>/dev/null) || true
            if [ -n "$merged_pr" ]; then
                if $DRY_RUN; then
                    echo "  WOULD DELETE remote: origin/${branch}  (#${issue_number} closed, PR #${merged_pr} merged)"
                else
                    git -C "$REPO_ROOT" push origin --delete "$branch" 2>/dev/null && \
                        echo "  Deleted remote: origin/${branch}  (#${issue_number} closed, PR #${merged_pr} merged)" || \
                        echo "  ERROR deleting remote: origin/${branch}"
                fi
                br_remote_removed=$((br_remote_removed + 1))
            else
                echo "  KEEP  origin/${branch}  (#${issue_number} closed but no merged PR found -- verify manually)"
            fi
        fi
    done <<< "$remote_branches"
fi

# Final prune
if ! $DRY_RUN; then
    git -C "$REPO_ROOT" fetch --prune 2>/dev/null || true
fi

# ---------- Summary ----------

echo ""
echo "=== Summary ==="
if $DRY_RUN; then
    echo "  (dry-run -- no changes were made)"
    echo "  Worktrees to remove:       ${wt_removed}"
    echo "  Worktrees to keep:         ${wt_skipped}"
    echo "  Local branches to delete:  ${br_local_removed}"
    echo "  Remote branches to delete: ${br_remote_removed}"
else
    echo "  Worktrees removed:         ${wt_removed}"
    echo "  Worktrees kept:            ${wt_skipped}"
    echo "  Local branches deleted:    ${br_local_removed}"
    echo "  Remote branches deleted:   ${br_remote_removed}"
fi
if [ "$errors" -gt 0 ]; then
    echo "  Errors:                    ${errors}"
fi
