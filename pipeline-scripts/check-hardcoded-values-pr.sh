#!/bin/bash
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
#
# CI wrapper for the hardcoded-values pre-commit hook.
# Issue #6725 (Phase 3 of #6715): runs the same hook against PR-changed
# files so devs can't bypass the check by skipping pre-commit locally.
#
# Inputs (env, all optional — sensible defaults derive from git):
#   BASE_SHA          explicit PR base SHA
#   HEAD_SHA          explicit head SHA (default: HEAD)
#   GITHUB_BASE_REF   target branch name on PR runs (set automatically by GH Actions)
#   GITHUB_SHA        commit SHA on push runs (set automatically by GH Actions)
#
# Behavior: if no relevant files changed, exits 0. Otherwise invokes the
# hook in argv mode against the changed-files list.

set -euo pipefail

BASE_SHA="${BASE_SHA:-}"
HEAD_SHA="${HEAD_SHA:-${GITHUB_SHA:-HEAD}}"

if [ -z "$BASE_SHA" ] && [ -n "${GITHUB_BASE_REF:-}" ]; then
    # PR context — translate the base branch name to a SHA via the fetched ref.
    BASE_SHA=$(git rev-parse "origin/${GITHUB_BASE_REF}" 2>/dev/null || true)
fi

if [ -n "$BASE_SHA" ]; then
    base="$BASE_SHA"
else
    base="${HEAD_SHA}^"
fi

# Filter to files that still exist (deleted files would be in the diff).
files=$(git diff --name-only "$base" "$HEAD_SHA" -- '*.py' '*.ts' '*.vue' \
    | while read -r f; do [ -f "$f" ] && printf '%s\n' "$f"; done \
    || true)

if [ -z "$files" ]; then
    echo "No changed Python/TS/Vue files — skipping hardcoded-value check."
    exit 0
fi

count=$(echo "$files" | wc -l)
echo "Checking $count changed file(s) for hardcoded values..."

HOOK="$(dirname "$0")/../autobot-infrastructure/shared/scripts/hooks/pre-commit-hardcoded-values"
# shellcheck disable=SC2086
bash "$HOOK" $files
