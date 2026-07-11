#!/bin/bash
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
#
# Gate 2 of the closure gates (#11599): block `gh issue close N` while the
# codebase still forward-references #N as the tracker for future work.
# Post-mortem #6828: a merged docstring pointed at #6828 for "broader
# unification" — closing #6828 made that pointer dangle. The phrase even
# wrapped across two source lines, so this gate classifies on
# whitespace-normalized file content, not single lines.
#
# Usage: pipeline-scripts/check-issue-close-refs.sh <issue-number>
#   exit 0 — no forward-tracking references (historical mentions listed as info)
#   exit 1 — forward-tracking references found → closure BLOCKED until a real
#            follow-up issue exists and each reference is updated to it
set -euo pipefail

if [ $# -ne 1 ] || ! [[ "$1" =~ ^[0-9]+$ ]]; then
  echo "Usage: $0 <issue-number>" >&2
  exit 2
fi
N="$1"
ROOT=$(git rev-parse --show-toplevel)
cd "$ROOT"
SELF="pipeline-scripts/check-issue-close-refs.sh"

EXCLUDES=(--exclude-dir=.git --exclude-dir=.worktrees --exclude-dir=node_modules
  --exclude-dir=dist --exclude-dir=build --exclude-dir=__pycache__
  --exclude-dir=.venv --exclude-dir=venv)

# Forward-tracking phrasings: the code points at #N as where FUTURE work lives.
FORWARD="(tracked in|tracking issue|TODO ?\(?|FIXME ?\(?|deferred to|deferred in|follow-?up( issue)?( in| is|:)?|will be (addressed|done|fixed|implemented) in)[^#]{0,40}#${N}([^0-9]|$)"

blocked=0
historical=""
while IFS= read -r f; do
  [ "$f" = "./$SELF" ] && continue
  # Classify on whitespace-normalized content so wrapped phrases still match.
  if tr '\n' ' ' < "$f" | grep -qE "$FORWARD"; then
    if [ "$blocked" -eq 0 ]; then
      echo "❌ Forward-tracking references to #${N} — CLOSURE BLOCKED:"
      blocked=1
    fi
    echo "  $f"
    grep -n "#${N}" "$f" | sed 's/^/    /' | head -5
  else
    historical+=$(grep -Hn "#${N}" "$f" | head -3)$'\n'
  fi
done < <(grep -rIl "${EXCLUDES[@]}" "#${N}" . || true)

if [ -n "${historical//[$'\n ']/}" ]; then
  echo ""
  echo "ℹ️  Historical mentions of #${N} (do not block closure):"
  printf '%s' "$historical" | sed '/^$/d' | head -20
fi

if [ "$blocked" -eq 1 ]; then
  echo ""
  echo "Fix: file a real follow-up issue, update each reference to point at it,"
  echo "then re-run this gate."
  exit 1
fi

echo ""
echo "✅ Gate 2 clear: no forward-tracking references to #${N}."
