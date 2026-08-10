#!/usr/bin/env bash
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
#
# lint-conventions.sh — enforce repo conventions that prose alone cannot.
# Issue: #13876
#
#   --staged        check staged files only (pre-commit)
#   --range A..B    check files changed in a commit range (CI)
#   --all           check every tracked file (audit)
#   --require-denylist
#                   fail if no denylist is available, instead of skipping.
#                   CI MUST pass this: a missing list would otherwise turn the
#                   anonymisation check into a silent no-op.
#
# Checks
#   1. third-party product/company names in tracked content
#   2. research/audit docs cross-link the issue they belong to
#   3. commit subjects carry a type(scope) and an issue reference
#
# The denylist is deliberately NOT stored in this repo: a committed list of
# third-party names would itself violate the rule it enforces. Source order:
#   $CONVENTIONS_DENYLIST  ->  ~/.claude/state/forbidden-names.txt
# In CI, inject it from a masked secret into a temp file and point the env var
# at it. One name per line; blank lines and #-comments ignored.

set -uo pipefail

MODE="--staged"
REQUIRE_DENYLIST=0
RANGE=""

while [ $# -gt 0 ]; do
  case "$1" in
    --staged|--all)      MODE="$1" ;;
    --range)             MODE="--range"; RANGE="${2:-}"; shift ;;
    --require-denylist)  REQUIRE_DENYLIST=1 ;;
    -h|--help)           sed -n '5,26p' "$0"; exit 0 ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
  shift
done

cd "$(git rev-parse --show-toplevel)" || { echo "not a git repo" >&2; exit 2; }

FAILURES=0
fail()  { FAILURES=$((FAILURES+1)); printf '  \033[31mFAIL\033[0m  %s\n' "$1"; }
ok()    { printf '  \033[32mok\033[0m    %s\n' "$1"; }
note()  { printf '  ----  %s\n' "$1"; }

# ── file list ────────────────────────────────────────────────────────────────
case "$MODE" in
  --staged) mapfile -t FILES < <(git diff --cached --name-only --diff-filter=ACMR) ;;
  --range)  [ -n "$RANGE" ] || { echo "--range needs A..B" >&2; exit 2; }
            mapfile -t FILES < <(git diff --name-only --diff-filter=ACMR "$RANGE") ;;
  --all)    mapfile -t FILES < <(git ls-files) ;;
esac

# Drop deleted/absent paths so a rename never reads a missing file.
EXISTING=()
for f in "${FILES[@]}"; do [ -f "$f" ] && EXISTING+=("$f"); done

echo "lint-conventions: ${#EXISTING[@]} file(s) in scope ($MODE)"

# ── check 1: third-party names ───────────────────────────────────────────────
DENYLIST="${CONVENTIONS_DENYLIST:-$HOME/.claude/state/forbidden-names.txt}"
echo
echo "[1] third-party names in tracked content"
if [ ! -r "$DENYLIST" ]; then
  if [ "$REQUIRE_DENYLIST" -eq 1 ]; then
    fail "no denylist at '$DENYLIST' — refusing to report a pass on an unrun check"
  else
    note "no denylist at '$DENYLIST' — check SKIPPED (not passed). CI must use --require-denylist"
  fi
elif [ ${#EXISTING[@]} -eq 0 ]; then
  ok "no files in scope"
else
  # Build one alternation so the tree is walked once, not once per name.
  PATTERN=$(grep -vE '^\s*(#|$)' "$DENYLIST" | sed 's/[][\.*^$(){}?+|/]/\\&/g' | paste -sd'|' -)
  if [ -z "$PATTERN" ]; then
    note "denylist is empty — nothing to match"
  else
    HITS=$(grep -rniE "$PATTERN" -- "${EXISTING[@]}" 2>/dev/null || true)
    if [ -n "$HITS" ]; then
      # Report location only. Echoing the matched line would reproduce the very
      # name we are trying to keep out of logs and CI output.
      while IFS= read -r h; do fail "third-party name at ${h%%:*}:$(printf '%s' "$h" | cut -d: -f2)"; done \
        <<< "$HITS"
    else
      ok "no third-party names found"
    fi
  fi
fi

# ── check 2: research/audit docs cross-link their issue ──────────────────────
echo
echo "[2] research/audit docs cross-link an issue"
DOCS=()
for f in "${EXISTING[@]}"; do
  case "$f" in docs/research/*.md|docs/audit/*.md) [ "$(basename "$f")" = "_index.md" ] || DOCS+=("$f") ;; esac
done
if [ ${#DOCS[@]} -eq 0 ]; then
  ok "no research/audit docs in scope"
else
  for f in "${DOCS[@]}"; do
    if grep -qE '#[0-9]{3,}' "$f"; then ok "$f"
    else fail "$f has no issue cross-link (#NNNN) — an umbrella-scale doc must name its umbrella"; fi
  done
fi

# ── check 3: commit subject format ───────────────────────────────────────────
echo
echo "[3] commit subject format"
SUBJECTS=""
case "$MODE" in
  --range)  SUBJECTS=$(git log --format=%s "$RANGE" 2>/dev/null) ;;
  --staged) [ -r .git/COMMIT_EDITMSG ] && SUBJECTS=$(head -1 .git/COMMIT_EDITMSG) ;;
esac
if [ -z "$SUBJECTS" ]; then
  ok "no commit subjects in scope"
else
  while IFS= read -r s; do
    [ -n "$s" ] || continue
    case "$s" in
      "Merge "*|"Revert "*|chore:\ claim\ worktree*) ok "skipped: ${s:0:52}"; continue ;;
    esac
    if ! printf '%s' "$s" | grep -qE '^[a-z]+(\([a-z0-9._-]+\))?: .+'; then
      fail "subject not '<type>(scope): <description>': ${s:0:56}"
    elif ! printf '%s' "$s" | grep -qE '#[0-9]{3,}'; then
      fail "subject has no issue reference: ${s:0:56}"
    else
      ok "${s:0:60}"
    fi
  done <<< "$SUBJECTS"
fi

echo
if [ "$FAILURES" -gt 0 ]; then
  echo "lint-conventions: $FAILURES violation(s)"
  exit 1
fi
echo "lint-conventions: clean"
