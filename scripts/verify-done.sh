#!/usr/bin/env bash
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
#
# verify-done.sh — the sole authority on whether work is actually finished.
# Issue: #13879 (rebuild of the implementation removed in #13877)
#
#   --branch <name>    branch to judge (default: current)
#   --base <ref>       integration branch (default: origin/Dev_new_gui)
#   --leftovers-only   audit stranded worktrees only
#
# Exit 0 = verified. Anything else = not done.
#
# DESIGN RULE, learned the hard way: this script emits DELETE INSTRUCTIONS, so
# a wrong verdict costs work. The first version OR-ed two weak signals and a
# one-character typo in the base ref reported 17 worktrees as landed where 3
# were — `git cherry` fatally errored, stderr was discarded, and empty output
# read as "nothing unlanded".
#
# Therefore:
#   * every git invocation is status-checked; an unusable result is FATAL
#   * "landed" requires ALL signals to agree, never any one of them
#   * "no commits yet" is a distinct state from "landed" — they are opposites
#   * commits are compared by PATCH ID (git cherry), never by subject text

set -uo pipefail

BASE="${VERIFY_DONE_BASE:-origin/Dev_new_gui}"
BRANCH=""
LEFTOVERS_ONLY=0

while [ $# -gt 0 ]; do
  case "$1" in
    --branch)         BRANCH="${2:-}"; [ -n "$BRANCH" ] || { echo "--branch needs a value" >&2; exit 2; }; shift ;;
    --base)           BASE="${2:-}";   [ -n "$BASE" ]   || { echo "--base needs a value" >&2; exit 2; }; shift ;;
    --leftovers-only) LEFTOVERS_ONLY=1 ;;
    -h|--help)        sed -n '5,26p' "$0"; exit 0 ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
  shift
done

cd "$(git rev-parse --show-toplevel 2>/dev/null)" 2>/dev/null || { echo "not a git repo" >&2; exit 2; }
[ -n "$BRANCH" ] || BRANCH=$(git branch --show-current 2>/dev/null)

FAILURES=0
fail() { FAILURES=$((FAILURES+1)); printf '  FAIL  %s\n' "$1"; }
ok()   { printf '  ok    %s\n' "$1"; }
info() { printf '  --    %s\n' "$1"; }

# The base must resolve before ANY verdict is possible. Without this the audit
# below silently degrades into "everything looks landed".
if ! git rev-parse --verify --quiet "${BASE}^{commit}" >/dev/null; then
  echo "FATAL: base ref '${BASE}' does not resolve in this clone." >&2
  echo "  Every landed/unlanded verdict depends on it, and a failed comparison" >&2
  echo "  is indistinguishable from 'no unlanded commits'. Refusing to emit a" >&2
  echo "  delete instruction from a comparison that could not run." >&2
  exit 1
fi

echo "verify-done: branch '${BRANCH:-<none>}' against '$BASE'"

# ── landed? ──────────────────────────────────────────────────────────────────
# Returns: 0 landed | 1 unlanded | 2 no commits | 3 unverifiable
branch_state() {
  local dir="$1" br="$2" ahead cherry rc
  ahead=$(git -C "$dir" rev-list --count "${BASE}..${br}" 2>/dev/null) || return 3
  [ -n "$ahead" ] || return 3
  # "Nothing ahead of base" is NOT landed. A freshly created worktree and a
  # fast-forward-merged branch are indistinguishable here — both have every
  # commit reachable from base. The ambiguity is resolved conservatively:
  # keeping a removable worktree costs disk, deleting an active one costs work.
  # Squash merges (how this repo lands) leave the branch ahead with matching
  # patch-ids, so the real landed case is still detected below.
  [ "$ahead" -eq 0 ] && return 2
  # Patch-id equivalence for EVERY commit. `+` marks one with no equivalent in
  # base. Subject text is never consulted: a generic `docs:`/`chore:` tip
  # subject collides across branches and is not evidence of anything.
  cherry=$(git -C "$dir" cherry "$BASE" "$br" 2>/dev/null); rc=$?
  [ "$rc" -eq 0 ] || return 3
  [ -z "$cherry" ] && return 3          # no output at all is unverifiable
  printf '%s\n' "$cherry" | grep -q '^+' && return 1
  return 0
}

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
  echo "[3] pull request state"
  PR_STATE=""
  if ! command -v gh >/dev/null 2>&1; then
    fail "gh unavailable — PR state cannot be verified, so 'done' cannot be claimed"
  else
    PR=$(gh pr list --head "$BRANCH" --state all --limit 1 --json number,state 2>/dev/null)
    if [ -z "$PR" ] || [ "$PR" = "[]" ]; then
      fail "no PR for '$BRANCH' — work does not land without one"
    else
      NUM=$(printf '%s' "$PR" | jq -r '.[0].number')
      PR_STATE=$(printf '%s' "$PR" | jq -r '.[0].state')
      case "$PR_STATE" in
        MERGED) ok "PR #$NUM merged" ;;
        OPEN)   fail "PR #$NUM still OPEN — not done until it lands" ;;
        *)      fail "PR #$NUM is $PR_STATE" ;;
      esac
    fi
  fi

  echo
  echo "[4] the work is in the base"
  # Deliberately NOT "is the remote branch still pushed". This repo has
  # delete_branch_on_merge=true, so after a merge the remote ref is gone and
  # that check could never pass for the case it exists to verify (#13879).
  if [ "$PR_STATE" = "MERGED" ]; then
    case "$(branch_state . "$BRANCH"; echo $?)" in
      0) ok "every commit is present in $BASE" ;;
      1) fail "PR is merged but commits are still missing from $BASE — fetch, or the merge did not include them" ;;
      2) info "no commits ahead of $BASE (already fast-forwarded or squashed in)" ;;
      *) fail "cannot compare '$BRANCH' against '$BASE' — refusing to call it done" ;;
    esac
  else
    info "skipped — only meaningful once the PR is merged"
  fi
fi

# ── stranded worktree audit ─────────────────────────────────────────────────
echo
echo "[5] stranded worktrees"
STRANDED=0; SEEN=0
SELF=$(git rev-parse --show-toplevel)

# `git worktree list --porcelain` (no -z; this git does not support it) emits
# `worktree <path>` lines. Stripping that fixed prefix keeps paths containing
# spaces intact — verified. The listing is captured with its status checked:
# an enumeration that fails must not read as "no worktrees", which is how the
# original produced a clean bill of health for a tree it never looked at.
if ! WT_LIST=$(git worktree list --porcelain 2>&1); then
  fail "cannot enumerate worktrees: $WT_LIST"
else
  while IFS= read -r dir; do
    [ -n "$dir" ] || continue
    [ "$dir" = "$SELF" ] && continue          # never audit the tree we stand in
    wb=$(git -C "$dir" branch --show-current 2>/dev/null) || continue
    [ -n "$wb" ] || continue
    case "$wb" in main|master|Dev_new_gui) continue ;; esac
    SEEN=$((SEEN+1))
    branch_state "$dir" "$wb"
    case $? in
      0) fail "worktree '$wb' has landed but still exists at $dir — remove it"; STRANDED=$((STRANDED+1)) ;;
      1) ok "'$wb' has unlanded commits — keep" ;;
      2) ok "'$wb' has no commits yet — a session may just have started; keep" ;;
      *) fail "'$wb' cannot be verified against $BASE — investigate, do not delete" ;;
    esac
  done < <(printf '%s\n' "$WT_LIST" | sed -n 's/^worktree //p')
  [ "$SEEN" -eq 0 ] && ok "no feature worktrees present"
fi

echo
if [ "$FAILURES" -gt 0 ]; then
  echo "verify-done: NOT DONE — $FAILURES check(s) failed"
  exit 1
fi
echo "verify-done: VERIFIED"
