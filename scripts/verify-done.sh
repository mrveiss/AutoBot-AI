#!/usr/bin/env bash
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
#
# verify-done.sh — the sole authority on whether work is actually finished.
# Issue: #13876
#
# No agent may claim "done", "clean", or "closed out" without a zero exit from
# this script and its output pasted as evidence. It exists because completion
# was self-reported: a campaign was declared fully closed while dangling
# branches and worktrees remained.
#
#   --branch <name>   branch to judge (default: current)
#   --leftovers-only  skip branch checks, audit only for stranded worktrees
#   --base <ref>      integration branch (default: origin/Dev_new_gui)
#
# Exit 0 = verified. Any other exit = not done. There is no third outcome, and
# a check that cannot run is a FAILURE, never a silent pass.

set -uo pipefail

BASE="${VERIFY_DONE_BASE:-origin/Dev_new_gui}"
BRANCH=""
LEFTOVERS_ONLY=0

while [ $# -gt 0 ]; do
  case "$1" in
    --branch)         BRANCH="${2:-}"; shift ;;
    --base)           BASE="${2:-}"; shift ;;
    --leftovers-only) LEFTOVERS_ONLY=1 ;;
    -h|--help)        sed -n '5,20p' "$0"; exit 0 ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
  shift
done

cd "$(git rev-parse --show-toplevel)" || { echo "not a git repo" >&2; exit 2; }
[ -n "$BRANCH" ] || BRANCH=$(git branch --show-current 2>/dev/null)

FAILURES=0
fail() { FAILURES=$((FAILURES+1)); printf '  \033[31mFAIL\033[0m  %s\n' "$1"; }
ok()   { printf '  \033[32mok\033[0m    %s\n' "$1"; }

echo "verify-done: branch '$BRANCH' against '$BASE'"

if [ "$LEFTOVERS_ONLY" -eq 0 ]; then
  echo
  echo "[1] working tree"
  if [ -n "$(git status --porcelain)" ]; then
    fail "uncommitted changes present:"
    git status --porcelain | head -10 | sed 's/^/          /'
  else
    ok "clean"
  fi

  echo
  echo "[2] branch is not an integration branch"
  case "$BRANCH" in
    main|master|Dev_new_gui) fail "'$BRANCH' is protected — work belongs on a feature branch" ;;
    "")                      fail "detached HEAD — no branch to verify" ;;
    *)                       ok "'$BRANCH'" ;;
  esac

  echo
  echo "[3] pushed and in sync with remote"
  if ! git rev-parse --verify --quiet "refs/remotes/origin/$BRANCH" >/dev/null; then
    fail "no remote branch origin/$BRANCH — nothing was pushed"
  else
    LOCAL=$(git rev-parse "$BRANCH")
    REMOTE=$(git rev-parse "origin/$BRANCH")
    if [ "$LOCAL" != "$REMOTE" ]; then
      fail "local $LOCAL != origin $REMOTE — the remote is not what you verified"
    else
      ok "origin/$BRANCH at ${LOCAL:0:9}"
    fi
  fi

  echo
  echo "[4] commits carry an issue reference"
  SUBJECTS=$(git log --format=%s "$BASE..$BRANCH" 2>/dev/null)
  if [ -z "$SUBJECTS" ]; then
    fail "no commits on '$BRANCH' beyond '$BASE' — there is nothing to be done"
  else
    BAD=0
    while IFS= read -r s; do
      [ -n "$s" ] || continue
      case "$s" in "Merge "*|chore:\ claim\ worktree*) continue ;; esac
      printf '%s' "$s" | grep -qE '#[0-9]{3,}' || { fail "no issue reference: ${s:0:56}"; BAD=1; }
    done <<< "$SUBJECTS"
    [ "$BAD" -eq 0 ] && ok "$(printf '%s' "$SUBJECTS" | grep -c .) commit(s) referenced"
  fi

  echo
  echo "[5] pull request state"
  if ! command -v gh >/dev/null 2>&1; then
    fail "gh unavailable — PR state cannot be verified, so 'done' cannot be claimed"
  else
    PR=$(gh pr list --head "$BRANCH" --state all --limit 1 --json number,state,mergedAt 2>/dev/null)
    if [ -z "$PR" ] || [ "$PR" = "[]" ]; then
      fail "no PR for '$BRANCH' — work does not land without one"
    else
      NUM=$(printf '%s' "$PR" | jq -r '.[0].number')
      STATE=$(printf '%s' "$PR" | jq -r '.[0].state')
      case "$STATE" in
        MERGED) ok "PR #$NUM merged" ;;
        OPEN)   fail "PR #$NUM still OPEN — not done until it lands" ;;
        *)      fail "PR #$NUM is $STATE" ;;
      esac
    fi
  fi
fi

# ── leftover audit ───────────────────────────────────────────────────────────
# Squash-merge aware: --is-ancestor reports a squash-merged branch as unmerged
# and its remote ref is already gone, so the subject is searched in the base.
echo
echo "[6] stranded worktrees"
STRANDED=0
while IFS= read -r wt; do
  [ -n "$wt" ] || continue
  WB=$(git -C "$wt" branch --show-current 2>/dev/null) || continue
  [ -n "$WB" ] || continue
  case "$WB" in main|master|Dev_new_gui) continue ;; esac
  SUBJ=$(git -C "$wt" log -1 --format=%s "$WB" 2>/dev/null)
  if [ -z "$(git cherry "$BASE" "$WB" 2>/dev/null | grep '^+')" ] \
     || git log "$BASE" --format=%s -n 400 2>/dev/null | grep -qxF "$SUBJ"; then
    fail "worktree '$WB' has landed but still exists at $wt — remove it"
    STRANDED=$((STRANDED+1))
  fi
done < <(git worktree list --porcelain | awk '/^worktree /{print $2}' | tail -n +2)
[ "$STRANDED" -eq 0 ] && ok "no landed worktree left behind"

echo
if [ "$FAILURES" -gt 0 ]; then
  echo "verify-done: NOT DONE — $FAILURES check(s) failed"
  exit 1
fi
echo "verify-done: VERIFIED"
