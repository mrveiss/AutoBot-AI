#!/usr/bin/env bash
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
#
# lint-conventions.sh — enforce repo conventions that prose alone cannot.
# Issue: #13876
#
#   --staged             files staged for commit (pre-commit)
#   --range A..B         files changed between two refs (CI)
#   --all                every tracked file (audit)
#   --commit-msg FILE    subject-format check only (commit-msg stage)
#   --require-denylist   fail if no usable denylist, instead of skipping
#
# Checks
#   1. third-party product/company names in tracked content
#   2. research/audit docs cross-link the issue they belong to
#   3. commit subjects carry a type(scope) and an issue reference
#
# Governing rule: a check that CANNOT RUN reports FAIL or SKIPPED — never a
# pass. Every git/grep invocation here is status-checked, because the failure
# mode that matters is a guard that silently reports clean.
#
# The denylist is deliberately NOT stored in this repo: a committed list of
# third-party names would itself violate the rule it enforces. Source order:
#   $CONVENTIONS_DENYLIST  ->  ~/.claude/state/forbidden-names.txt
# In CI, inject it from a masked secret into a runner-local temp file.
# One entry per line; blank lines and #-comments ignored; CR and surrounding
# whitespace stripped (a secret pasted into a web form often carries CRLF).

set -uo pipefail

MODE="--staged"
REQUIRE_DENYLIST=0
RANGE=""
MSG_FILE=""

while [ $# -gt 0 ]; do
  case "$1" in
    --staged|--all)      MODE="$1" ;;
    --range)             MODE="--range"; RANGE="${2:-}"; shift ;;
    --commit-msg)        MODE="--commit-msg"; MSG_FILE="${2:-}"; shift ;;
    --require-denylist)  REQUIRE_DENYLIST=1 ;;
    -h|--help)           sed -n '5,27p' "$0"; exit 0 ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
  shift
done

cd "$(git rev-parse --show-toplevel)" || { echo "not a git repo" >&2; exit 2; }

FAILURES=0
fail() { FAILURES=$((FAILURES+1)); printf '  FAIL  %s\n' "$1"; }
ok()   { printf '  ok    %s\n' "$1"; }
note() { printf '  ----  %s\n' "$1"; }
die()  { printf '  FATAL %s\n' "$1" >&2; exit 1; }

# ── commit-msg mode: subject only, nothing else is knowable here ─────────────
if [ "$MODE" = "--commit-msg" ]; then
  [ -n "$MSG_FILE" ] && [ -r "$MSG_FILE" ] || die "--commit-msg needs a readable file"
  SUBJECT=$(head -1 "$MSG_FILE")
  case "$SUBJECT" in
    "Merge "*|"Revert "*|"fixup!"*|"squash!"*|chore:\ claim\ worktree*)
      echo "lint-conventions: subject exempt"; exit 0 ;;
  esac
  if ! printf '%s' "$SUBJECT" | grep -qE '^[a-z]+(\([a-z0-9._-]+\))?: .+'; then
    echo "  FAIL  subject is not '<type>(scope): <description>'"; exit 1
  fi
  if ! printf '%s' "$SUBJECT" | grep -qE '#[0-9]{3,}'; then
    echo "  FAIL  subject carries no issue reference (#NNNN)"; exit 1
  fi
  echo "lint-conventions: subject ok"; exit 0
fi

# ── file list — every git call status-checked (H2) ──────────────────────────
case "$MODE" in
  --staged)
    LIST=$(git diff --cached --name-only --diff-filter=ACMR) \
      || die "git diff --cached failed — cannot determine scope, refusing to report clean" ;;
  --all)
    LIST=$(git ls-files) \
      || die "git ls-files failed — cannot determine scope, refusing to report clean" ;;
  --range)
    [ -n "$RANGE" ] || die "--range needs A..B"
    BASE_REF="${RANGE%%...*}"; BASE_REF="${BASE_REF%%..*}"
    HEAD_REF="${RANGE##*..}"
    for r in "$BASE_REF" "$HEAD_REF"; do
      git rev-parse --verify --quiet "${r}^{commit}" >/dev/null \
        || die "'$r' does not resolve in this clone. A shallow checkout cannot compare against the base — set 'fetch-depth: 0' on actions/checkout."
    done
    # Three-dot: changes introduced by HEAD since the merge-base, so files that
    # other merged PRs touched on the base never enter this PR's scope (M5).
    LIST=$(git diff --name-only --diff-filter=ACMR "${BASE_REF}...${HEAD_REF}") \
      || die "git diff failed for $RANGE" ;;
esac

FILES=()
[ -n "$LIST" ] && mapfile -t FILES <<< "$LIST"
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
    note "no denylist at '$DENYLIST' — SKIPPED (not passed). CI must use --require-denylist"
  fi
else
  # Strip CR and surrounding whitespace before anything else: a denylist pasted
  # into a web form or touched on Windows carries CRLF, and 'Name\r' matches
  # nothing while still looking like a configured guard (H4).
  PATTERN=$(tr -d '\r' < "$DENYLIST" \
            | sed 's/^[[:space:]]*//; s/[[:space:]]*$//' \
            | grep -vE '^(#|$)' \
            | sed 's/[][\.*^$(){}?+|/]/\\&/g' \
            | paste -sd'|' -)
  if [ -z "$PATTERN" ]; then
    # The most likely secret misconfiguration is an empty or comment-only list,
    # which is exactly what --require-denylist exists to catch (M3).
    if [ "$REQUIRE_DENYLIST" -eq 1 ]; then
      fail "denylist '$DENYLIST' has no usable entries — refusing to report a pass on an unrun check"
    else
      note "denylist has no usable entries — SKIPPED (not passed)"
    fi
  elif [ ${#EXISTING[@]} -eq 0 ]; then
    ok "no files in scope"
  else
    # -e guards an entry beginning with '-'; rc>1 is a grep ERROR, which must
    # never be read as "no match" (H3).
    HITS=$(grep -rnIE -e "$PATTERN" -- "${EXISTING[@]}" 2>/dev/null)
    rc=$?
    if [ "$rc" -gt 1 ]; then
      fail "grep exited $rc — the denylist did not compile. Treating as UNRUN, not clean"
    elif [ "$rc" -eq 0 ]; then
      # Location only. Echoing the matched line would reproduce the very name
      # this rule keeps out of logs and CI output.
      while IFS= read -r h; do
        [ -n "$h" ] && fail "third-party name at $(printf '%s' "$h" | cut -d: -f1-2)"
      done <<< "$HITS"
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
  case "$f" in
    docs/research/*.md|docs/audit/*.md)
      [ "$(basename "$f")" = "_index.md" ] || DOCS+=("$f") ;;
  esac
done
if [ ${#DOCS[@]} -eq 0 ]; then
  ok "no research/audit docs in scope"
else
  for f in "${DOCS[@]}"; do
    if grep -qE '#[0-9]{3,}' "$f"; then ok "$f"
    else fail "$f has no issue cross-link (#NNNN) — an umbrella-scale doc must name its umbrella"; fi
  done
fi

# ── check 3: commit subjects (range mode only) ──────────────────────────────
# Reported by SHA, not by subject text: subjects are covered by the
# anonymisation rule, so echoing them here would defeat check 1 (M6).
echo
echo "[3] commit subject format"
if [ "$MODE" != "--range" ]; then
  note "subjects are checked at the commit-msg stage, not here"
else
  # Author is carried alongside the subject so bot-authored commits can be
  # exempted: this repo's own auto-fix workflows (generated types, formatting)
  # push commits with no issue number, and without this every PR that touches
  # an OpenAPI schema fails a required check on a commit no human wrote.
  LOGLINES=$(git log --format='%h%x1f%s%x1f%an' "${BASE_REF}..${HEAD_REF}") \
    || die "git log failed for $RANGE"
  if [ -z "$LOGLINES" ]; then
    ok "no commits in range"
  else
    BAD=0; SEEN=0
    while IFS= read -r line; do
      [ -n "$line" ] || continue
      SEEN=$((SEEN+1))
      sha=${line%%$'\x1f'*}
      rest=${line#*$'\x1f'}
      subj=${rest%%$'\x1f'*}
      author=${rest#*$'\x1f'}
      case "$subj" in
        "Merge "*|"Revert "*|chore:\ claim\ worktree*) continue ;;
      esac
      case "$author" in
        *'[bot]') continue ;;
      esac
      if ! printf '%s' "$subj" | grep -qE '^[a-z]+(\([a-z0-9._-]+\))?: .+'; then
        fail "commit $sha: subject is not '<type>(scope): <description>'"; BAD=1
      elif ! printf '%s' "$subj" | grep -qE '#[0-9]{3,}'; then
        fail "commit $sha: no issue reference"; BAD=1
      fi
    done <<< "$LOGLINES"
    [ "$BAD" -eq 0 ] && ok "$SEEN commit(s) conform"
  fi
fi

echo
if [ "$FAILURES" -gt 0 ]; then
  echo "lint-conventions: $FAILURES violation(s)"
  exit 1
fi
echo "lint-conventions: clean"
