#!/bin/bash
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# Closure-gate wiring check: verify new modules added in this PR have production callers.
# Single source of truth referenced by /implement, /issue, /batch-implement skills.
#
# Usage:
#   check-new-module-callers.sh [--base-branch REF] [--allow-deferral FILE]
#
# Defaults:
#   --base-branch origin/Dev_new_gui
#   --allow-deferral (optional) file containing deferred issue refs like "#7234"
#
# Exit codes:
#   0 — all new modules have ≥1 production caller
#   1 — new module(s) found with zero callers (unless deferred)

set -euo pipefail

BASE_BRANCH="origin/Dev_new_gui"
ALLOW_DEFERRAL_FILE=""

# Parse options
while (( $# > 0 )); do
  case "$1" in
    --base-branch) BASE_BRANCH="$2"; shift 2 ;;
    --allow-deferral) ALLOW_DEFERRAL_FILE="$2"; shift 2 ;;
    *) echo "usage: $0 [--base-branch REF] [--allow-deferral FILE]" >&2; exit 1 ;;
  esac
done

# Find new source files in this PR (added compared to base branch)
NEW_FILES=$(git diff "$BASE_BRANCH"...HEAD --diff-filter=A --name-only 2>/dev/null || echo "")

# Filter to production code only
NEW_MODULES=$(echo "$NEW_FILES" | grep -E '\.(py|ts|vue)$' | grep -vE '_test\.(py|ts)|\.test\.(ts|vue)|/tests/|/__tests__/|conftest|fixtures' || true)

if [ -z "$NEW_MODULES" ]; then
  echo "✅ No new source modules to check."
  exit 0
fi

# Load deferred (future-wiring) issues if provided
DEFERRED_ISSUES=""
if [ -n "$ALLOW_DEFERRAL_FILE" ] && [ -f "$ALLOW_DEFERRAL_FILE" ]; then
  DEFERRED_ISSUES=$(grep "^#" "$ALLOW_DEFERRAL_FILE" 2>/dev/null | sed 's/^#//' | tr '\n' '|' | sed 's/|$//' || true)
fi

FAILED=0

# Check each new module for production callers
while IFS= read -r module; do
  # Extract module stem (filename without extension)
  STEM=$(basename "$module" | sed 's/\.[^.]*$//')

  # Check if this is deferred (tracked in a follow-up issue)
  if [ -n "$DEFERRED_ISSUES" ] && echo "$module" | grep -qE "$DEFERRED_ISSUES"; then
    echo "⏭️  $module — wiring deferred (issue referenced)"
    continue
  fi

  # Count import statements referencing this module (simple grep, not AST)
  # Look for: from X import, import X, import ... X, /X/index
  CALLER_COUNT=$(grep -r "from.*${STEM}\|import.*${STEM}" . \
    --include="*.py" --include="*.ts" --include="*.vue" 2>/dev/null \
    | grep -v "^${module}:" \
    | grep -vE '(__pycache__|node_modules|\.worktrees|dist)' \
    | wc -l || echo 0)

  if [ "$CALLER_COUNT" -eq 0 ]; then
    echo "❌ $module — no callers"
    FAILED=1
  else
    echo "✅ $module — $CALLER_COUNT callers"
  fi
done <<< "$NEW_MODULES"

echo ""
if [ $FAILED -eq 1 ]; then
  cat >&2 << 'HEREDOC'
⚠️  New module(s) with no production callers found.

Before closing the issue:
  1. File a follow-up issue to track wiring (label: tech-debt)
  2. Add its number to .wiring-deferral.txt: echo "#XXXX" >> .wiring-deferral.txt
  3. Re-run: check-new-module-callers.sh --allow-deferral .wiring-deferral.txt

HEREDOC
  exit 1
fi

echo "✅ All new modules have callers — ready to merge."
exit 0
