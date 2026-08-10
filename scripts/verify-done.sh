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
    -h|--help)        sed -n '5,24p' "$0"; exit 0 ;;
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
#          4 patch-ids say landed, but the base has since changed the same
#            files, so content equality cannot confirm it — keep, verify by hand
branch_state() {
  local dir="$1" br="refs/heads/$2" ahead cherry rc line mark sha substantive=0 unlanded=0 wt_dirty
  ahead=$(git -C "$dir" rev-list --count "${BASE}..${br}" 2>/dev/null) || return 3
  [ -n "$ahead" ] || return 3
  # "Nothing ahead of base" is NOT landed. A freshly created worktree and a
  # fast-forward-merged branch are indistinguishable here — both have every
  # commit reachable from base. The ambiguity is resolved conservatively:
  # keeping a removable worktree costs disk, deleting an active one costs work.
  # Squash merges (how this repo lands) leave the branch ahead with matching
  # patch-ids, so the real landed case is still detected below.
  [ "$ahead" -eq 0 ] && return 2

  # MERGE COMMITS ARE INVISIBLE TO `git cherry` (#13879). It omits them
  # entirely, so content that exists ONLY in a merge — a conflict resolution
  # when a branch is updated off base, or an evil merge — is represented by no
  # line below and cannot be judged. A live branch here carries 5 such files.
  # Unjudgeable is not landed: report "cannot verify" rather than authorize a
  # deletion of work no signal has looked at.
  local m mfiles mlist unlock_hint
  mlist=$(git -C "$dir" rev-list --merges "${BASE}..${br}" 2>/dev/null) || return 3
  for m in $mlist; do
    mfiles=$(git -C "$dir" diff-tree -c -r --no-commit-id --name-only "$m" 2>/dev/null) || return 3
    [ -z "$mfiles" ] || return 3
  done

  # Patch-id equivalence per commit. `+` = no equivalent upstream, `-` = present.
  # Subject text is never consulted: a generic `docs:`/`chore:` subject collides
  # across branches and is not evidence of anything.
  cherry=$(git -C "$dir" cherry "$BASE" "$br" 2>/dev/null); rc=$?
  [ "$rc" -eq 0 ] || return 3
  [ -z "$cherry" ] && return 3          # no output at all is unverifiable

  # EMPTY COMMITS ARE NOT EVIDENCE (#13879). An empty commit has an empty
  # patch, so `git cherry` marks it `-` against ANY empty commit upstream —
  # and the worktree rules mandate an empty claim commit on creation, while
  # empty commits reach the base routinely (3 of the last 300, one of them a
  # claim commit). Counting those as "landed" reports a just-claimed worktree
  # as deletable: the precise failure this script exists to prevent, reborn.
  # Only commits that actually change something can testify either way.
  local names
  while IFS= read -r line; do
    [ -n "$line" ] || continue
    mark=${line%% *}; sha=${line##* }
    # Status-checked: a FAILED diff-tree is otherwise indistinguishable from an
    # empty commit, and skipping a `+` commit on that basis drops `unlanded` to
    # zero and authorizes a deletion.
    # --root is load-bearing: without it `diff-tree` prints NOTHING for a
    # parentless commit and exits 0, so the empty-commit filter below would
    # skip a genuinely unlanded root commit (unrelated-history merge, subtree
    # import, shallow-clone boundary) and the branch would read as landed.
    # `git cherry` judges root commits with full-tree semantics, so this makes
    # the two agree.
    names=$(git -C "$dir" diff-tree --root -r --no-commit-id --name-only "$sha" 2>/dev/null) || return 3
    [ -n "$names" ] || continue
    substantive=$((substantive + 1))
    [ "$mark" = "+" ] && unlanded=$((unlanded + 1))
  done <<< "$cherry"

  # Only empty commits ahead of base — a claimed but unworked worktree.
  [ "$substantive" -eq 0 ] && return 2
  [ "$unlanded" -gt 0 ] && return 1

  # PATCH-ID EQUIVALENCE IS NOT CONTENT EQUIVALENCE (#13879). Two failures:
  #
  #   * `git patch-id` STRIPS WHITESPACE, so a whitespace-only fix — semantic
  #     in Python, YAML, Makefiles — collides with any upstream commit whose
  #     stripped diff matches. Verified: a 4-space dedent and an unrelated
  #     retab of the same line share patch-id 04e3cb9a…, and `git cherry`
  #     calls the branch commit landed while base still holds the bug.
  #   * `git cherry` answers "was this patch ever applied", not "is it in the
  #     base NOW". Work that merged and was later reverted reads as landed
  #     forever — and the merged-PR signal is true then too, so the two
  #     signals are not independent for that case.
  #
  # So confirm the content actually is in the base tree before saying landed.
  local -a touched=()
  local rl c tf
  rl=$(git -C "$dir" rev-list "${BASE}..${br}" 2>/dev/null) || return 3
  if [ -n "$rl" ]; then
    # ONE COMMIT PER CALL. `git diff-tree` accepts at most two tree-ishes: with
    # three or more it exits 0 and prints NOTHING (verified), so passing the
    # whole rev-list left `touched` empty and skipped this guard entirely —
    # inert on 8 of 18 live worktrees and wrong on 12, including the branch
    # that introduced it (ahead=9). Two revs is just as bad: it diffs the two
    # trees and reports only the tip. -m makes merges contribute their own diff.
    tf=$(mktemp) || return 3
    for c in $rl; do
      if ! git -C "$dir" diff-tree -r --root -m --no-commit-id --name-only -z "$c" >>"$tf" 2>/dev/null; then
        rm -f "$tf"; return 3
      fi
    done
    # sort -zu: `-m` emits a merge's paths once per parent, and a long-lived
    # branch that merges base repeatedly accumulates thousands of duplicates —
    # enough to cross ARG_MAX and degrade the guard to "keep" permanently.
    sort -zu "$tf" -o "$tf" 2>/dev/null || true
    while IFS= read -r -d '' f; do
      # :(literal) — a path beginning with ':' is otherwise parsed as pathspec
      # magic even after --, and silently compares equal.
      [ -n "$f" ] && touched+=(":(literal)$f")
    done < "$tf"
    rm -f "$tf"
    # The function has already proven substantive > 0, so a non-empty rev-list
    # with nothing touched is impossible unless a git call misbehaved. Treat it
    # as unverifiable rather than letting it fall through to "landed".
    [ "${#touched[@]}" -eq 0 ] && return 3
  fi
  # Verdict stays conservative (never delete), but the REASON must be accurate:
  # "has unlanded commits" would be a false statement about a branch whose work
  # landed and whose files the base has simply moved on in. Distinct code 4.
  if [ "${#touched[@]}" -gt 0 ]; then
    git -C "$dir" diff --quiet "$BASE" "$br" -- "${touched[@]}" 2>/dev/null || return 4
  fi
  return 0
}

if [ "$LEFTOVERS_ONLY" -eq 0 ]; then
  echo
  echo "[1] working tree"
  # Status-checked like every other git call here: if this fails, empty output
  # would read as "clean" and mask uncommitted work behind a VERIFIED.
  if ! WT_STATUS=$(git status --porcelain 2>&1); then
    fail "git status failed — cannot confirm the tree is clean: $WT_STATUS"
  elif [ -n "$WT_STATUS" ]; then
    fail "uncommitted changes present:"
    printf '%s\n' "$WT_STATUS" | head -10 | sed 's/^/          /'
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
  if ! command -v gh >/dev/null 2>&1 || ! command -v jq >/dev/null 2>&1; then
    fail "gh or jq unavailable — PR state cannot be verified, so 'done' cannot be claimed"
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
      4) info "commits match by patch-id; the base has since changed the same files, so exact content equality cannot be confirmed" ;;
      2) info "no commits ahead of $BASE (already fast-forwarded or squashed in)" ;;
      *) fail "cannot compare '$BRANCH' against '$BASE' — refusing to call it done" ;;
    esac
  else
    info "skipped — only meaningful once the PR is merged"
  fi
fi

# ── stranded worktree audit ─────────────────────────────────────────────────
echo
echo "[5] worktree evidence"
# REPORT ONLY — this section never emits a delete instruction (#13879).
#
# Seven review rounds found thirteen defects here, and every one of them was a
# defect of the IMPERATIVE: a wrong "keep" costs disk, a wrong "remove it"
# costs work that exists nowhere else. The imperative also bought nothing —
# nobody pipes this into `xargs git worktree remove`; a human or an agent makes
# the call either way — so it carried all of the residual risk for none of the
# capability.
#
# Worse, the question is not answerable from git alone. `git status` is
# SPECIFIED to ignore assume-unchanged/skip-worktree entries, and
# `git worktree remove` uses the same blind check — so both blind spots
# compose: a worktree can hold hours of uncommitted work, report clean, and be
# removed with rc=0. Ignored files (.env, data/.slm_keys) are invisible to it
# too. A tool that cannot see what deletion destroys must not order deletion.
#
# So: print the evidence, mark candidates, and let the operator decide.
CANDIDATES=0; SEEN=0
SELF=$(git rev-parse --show-toplevel)

if ! WT_LIST=$(git worktree list --porcelain 2>&1); then
  fail "cannot enumerate worktrees: $WT_LIST"
else
  while IFS= read -r dir; do
    [ -n "$dir" ] || continue
    [ "$dir" = "$SELF" ] && continue
    wb=$(git -C "$dir" branch --show-current 2>/dev/null) || continue
    if [ -z "$wb" ]; then
      SEEN=$((SEEN+1)); info "detached HEAD at $dir — no branch to compare; cannot audit"
      continue
    fi
    case "$wb" in main|master|Dev_new_gui) continue ;; esac
    SEEN=$((SEEN+1))

    branch_state "$dir" "$wb"; bs=$?
    case $bs in
      0) verdict="every commit present in $BASE (patch-id AND tree content)" ;;
      1) verdict="has unlanded commits" ;;
      2) verdict="no commits yet, or only empty claim commits" ;;
      3) verdict="CANNOT BE VERIFIED — investigate" ;;
      4) verdict="landed by patch-id, but $BASE has since changed the same paths" ;;
    esac

    wt_dirty=$(git -C "$dir" status --porcelain 2>/dev/null | wc -l)
    wt_ignored=$(git -C "$dir" status --porcelain --ignored=matching 2>/dev/null | grep -c '^!!')
    # `git status` cannot see these by design, and neither can
    # `git worktree remove` — the pair that composes into silent data loss.
    idx_bits=$(git -C "$dir" ls-files -v 2>/dev/null | grep -c '^[a-zS]')
    locked=no
    awk -v d="worktree $dir" '$0==d{f=1;next} /^worktree /{f=0} f&&/^locked/{print;exit}' \
      <<< "$WT_LIST" | grep -q . && locked=yes
    merged_pr="(not queried)"
    if command -v gh >/dev/null 2>&1; then
      if pr=$(gh pr list --head "$wb" --state merged --limit 1 --json number --jq '.[0].number' 2>/dev/null); then
        merged_pr="${pr:-none}"
      else
        merged_pr="(gh failed)"
      fi
    fi

    printf '\n  %s\n' "$wb"
    printf '    landed        : %s\n' "$verdict"
    printf '    merged PR     : %s\n' "$merged_pr"
    printf '    uncommitted   : %s\n' "$wt_dirty"
    printf '    ignored       : %s%s\n' "$wt_ignored" \
      "$([ "${wt_ignored:-0}" -gt 0 ] && echo '  (deleted silently by git worktree remove)')"
    printf '    index bits    : %s assume-unchanged/skip-worktree%s\n' "$idx_bits" \
      "$([ "${idx_bits:-0}" -gt 0 ] && echo '  (invisible to git status AND to worktree remove)')"
    printf '    locked        : %s\n' "$locked"
    printf '    path          : %s\n' "$dir"

    if [ "$bs" -eq 0 ] && [ "$merged_pr" != "none" ] && [ "$merged_pr" != "(gh failed)" ] \
       && [ "$merged_pr" != "(not queried)" ]; then
      CANDIDATES=$((CANDIDATES+1))
      printf '    => CANDIDATE for removal — operator decision. Inspect the counts above first.\n'
    fi
  done < <(printf '%s\n' "$WT_LIST" | sed -n 's/^worktree //p')
  echo
  [ "$SEEN" -eq 0 ] && ok "no feature worktrees present"
  info "$SEEN worktree(s) examined, $CANDIDATES candidate(s) for removal — nothing was instructed"
fi

echo
if [ "$FAILURES" -gt 0 ]; then
  echo "verify-done: NOT DONE — $FAILURES check(s) failed"
  exit 1
fi
echo "verify-done: VERIFIED"
