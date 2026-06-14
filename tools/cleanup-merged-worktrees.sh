#!/usr/bin/env bash
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
#
# Wrapper script for worktree cleanup (Issue #7104, Phase 2)
#
# Usage: tools/cleanup-merged-worktrees.sh [--dry-run] [--branches-only]
#
# This script delegates to scripts/cleanup-worktrees.sh which:
#   1. Removes worktrees (.worktrees/*/) for closed issues
#   2. Deletes local branches for closed/merged issues
#   3. Deletes remote branches for closed/merged issues
#
# Intended use: Call from batch-implement post-merge phase (Issue #7104, Phase 3).
#
# Issue #7104: tooling — stale worktrees accumulate; chronic issue-6806 on main blocks gh pr merge
#

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
CLEANUP_SCRIPT="${REPO_ROOT}/scripts/cleanup-worktrees.sh"

if [ ! -f "$CLEANUP_SCRIPT" ]; then
    echo "Error: cleanup script not found at $CLEANUP_SCRIPT" >&2
    exit 1
fi

exec "$CLEANUP_SCRIPT" "$@"
