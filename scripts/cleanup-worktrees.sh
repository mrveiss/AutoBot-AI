#!/usr/bin/env bash
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
#
# Cleanup stale git worktrees under .worktrees/ whose GitHub issues are closed.
# Usage: scripts/cleanup-worktrees.sh [--dry-run]

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
WORKTREES_DIR="${REPO_ROOT}/.worktrees"
DRY_RUN=false

for arg in "$@"; do
    case "$arg" in
        --dry-run)
            DRY_RUN=true
            ;;
        --help|-h)
            echo "Usage: $0 [--dry-run]"
            echo ""
            echo "Removes git worktrees under .worktrees/ whose GitHub issues are closed."
            echo ""
            echo "Options:"
            echo "  --dry-run   Show what would be cleaned without making changes"
            echo "  --help      Show this help message"
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

if [ ! -d "$WORKTREES_DIR" ]; then
    echo "No .worktrees/ directory found. Nothing to clean."
    exit 0
fi

removed=0
skipped=0
errors=0

echo "Scanning worktrees in ${WORKTREES_DIR}..."
if $DRY_RUN; then
    echo "(dry-run mode -- no changes will be made)"
fi
echo ""

for worktree_path in "$WORKTREES_DIR"/*/; do
    # Skip if glob matched nothing
    [ -d "$worktree_path" ] || continue

    dir_name="$(basename "$worktree_path")"

    # Extract issue number from directory name (e.g., issue-2467 -> 2467)
    issue_number=""
    if [[ "$dir_name" =~ issue-([0-9]+) ]]; then
        issue_number="${BASH_REMATCH[1]}"
    else
        echo "  SKIP  ${dir_name} -- cannot extract issue number"
        skipped=$((skipped + 1))
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
        if $DRY_RUN; then
            echo "  WOULD REMOVE  ${dir_name}  (issue #${issue_number} is closed)"
        else
            echo "  REMOVING      ${dir_name}  (issue #${issue_number} is closed)"
            if git -C "$REPO_ROOT" worktree remove --force "$worktree_path" 2>/dev/null; then
                # Also delete the local branch if it exists
                branch_name="fix/issue-${issue_number}"
                git -C "$REPO_ROOT" branch -D "$branch_name" 2>/dev/null || true
            else
                echo "    WARNING: git worktree remove failed; attempting manual cleanup"
                rm -rf "$worktree_path"
                git -C "$REPO_ROOT" worktree prune
            fi
        fi
        removed=$((removed + 1))
    else
        echo "  KEEP          ${dir_name}  (issue #${issue_number} is ${issue_state})"
        skipped=$((skipped + 1))
    fi
done

echo ""
echo "--- Summary ---"
if $DRY_RUN; then
    echo "Would remove: ${removed}"
else
    echo "Removed:      ${removed}"
fi
echo "Kept:         ${skipped}"
if [ "$errors" -gt 0 ]; then
    echo "Errors:       ${errors}"
fi
