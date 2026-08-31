#!/usr/bin/env bash
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
#
# Unit tests for scripts/lib/branch-guards.sh -- the safe-pruning guards that
# close the #10035 branch-deletion race. Run: bash scripts/lib/branch-guards_test.sh
#
# `git` and `gh` are stubbed so the tests are hermetic (no network, no repo).

set -uo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=scripts/lib/branch-guards.sh
source "${HERE}/branch-guards.sh"

pass=0
fail=0

check() {
    local name="$1" expected="$2" actual="$3"
    if [ "$expected" = "$actual" ]; then
        pass=$((pass + 1))
    else
        fail=$((fail + 1))
        echo "  FAIL: ${name} -- expected [${expected}], got [${actual}]"
    fi
}

echo "== extract_issue_number =="
# Regressions for #10035: a date and an MVA work-item must NOT be read as issues.
check "date token not matched"   "" "$(extract_issue_number 'chore/triage-delta-2026-06-12')"
check "MVA work-item not matched" "" "$(extract_issue_number 'MVA-3847-fix')"
check "feature slug not matched"  "" "$(extract_issue_number 'feat/gantt-timeline-view')"
check "embedded number not matched" "" "$(extract_issue_number 'fix/apexcharts-514-types')"
# Legitimate issue/hotfix branches must still resolve.
check "issue- prefix"   "9943"  "$(extract_issue_number 'issue-9943')"
check "issue/ prefix"   "9943"  "$(extract_issue_number 'issue/9943')"
check "hotfix- prefix"  "1234"  "$(extract_issue_number 'hotfix-1234')"
check "issue- with suffix" "10035" "$(extract_issue_number 'issue-10035-branch-prune')"

echo "== branch_recently_pushed =="
# Stub git so the tip timestamp is controllable.
NOW=$(date +%s)
git() {
    case "$*" in
        "log -1 --format=%ct fresh")  echo "$NOW" ;;
        "log -1 --format=%ct old")    echo "$((NOW - 50 * 3600))" ;;  # 50h ago
        "log -1 --format=%ct gone")   return 1 ;;                      # unknown ref
        "log -1 --format=%ct empty")  return 0 ;;                      # exit 0, prints nothing
        *) command git "$@" ;;
    esac
}
branch_recently_pushed fresh && r=yes || r=no
check "fresh branch is recent"      "yes" "$r"
branch_recently_pushed old && r=yes || r=no
check "old branch is not recent"    "no"  "$r"
branch_recently_pushed gone && r=yes || r=no
check "missing ref is not recent"   "no"  "$r"
branch_recently_pushed empty && r=yes || r=no
check "empty timestamp is not recent" "no" "$r"
# Threshold is configurable.
BRANCH_MIN_AGE_HOURS=72
branch_recently_pushed old && r=yes || r=no
check "old within 72h window"       "yes" "$r"
BRANCH_MIN_AGE_HOURS=24
unset -f git

echo "== branch_has_open_pr =="
gh() {
    # Echo a PR number only for the branch named "with-pr".
    case "$*" in
        *"--head with-pr"*) echo "4242" ;;
        *) echo "" ;;
    esac
}
branch_has_open_pr with-pr && r=yes || r=no
check "open PR detected"            "yes" "$r"
branch_has_open_pr no-pr && r=yes || r=no
check "no open PR"                  "no"  "$r"
unset -f gh

echo "== branch_is_archival =="
branch_is_archival 'rescued/stash-2026-05-10-18b82cecd' && r=yes || r=no
check "rescued/ is archival"          "yes" "$r"
branch_is_archival 'release/changelog-v0.5.2' && r=yes || r=no
check "release/changelog- is archival" "yes" "$r"
branch_is_archival 'issue-15036-sweeps' && r=yes || r=no
check "issue branch is not archival"  "no"  "$r"
branch_is_archival 'rescued-but-not-really' && r=yes || r=no
check "prefix needs its separator"    "no"  "$r"

# ---------------------------------------------------------------------------
# Content tests run against a real, throwaway repository.
#
# GIT_DIR and friends are scrubbed for the whole block: an ambient GIT_DIR would
# aim every `git` call below at the caller's real repository and commit into it
# (#15353). Every command also names its repo with `git -C`.
# ---------------------------------------------------------------------------
unset GIT_DIR GIT_WORK_TREE GIT_INDEX_FILE GIT_OBJECT_DIRECTORY GIT_COMMON_DIR
TESTREPO=$(mktemp -d)
trap 'rm -rf "$TESTREPO"' EXIT
git -C "$TESTREPO" init -q -b base
git -C "$TESTREPO" config user.email t@example.invalid
git -C "$TESTREPO" config user.name t
printf 'alpha_line_one\nalpha_line_two\n' > "$TESTREPO/kept.txt"
printf 'moved_line_one\n' > "$TESTREPO/moved.txt"
git -C "$TESTREPO" add -A
git -C "$TESTREPO" commit -qm 'chore(seed): initial tree (#13224)'

# A branch whose additions base already contains, forked before base grew them.
git -C "$TESTREPO" checkout -q -b already-there HEAD
printf 'gamma_addition_here\n' >> "$TESTREPO/kept.txt"
git -C "$TESTREPO" commit -qam 'add gamma'
git -C "$TESTREPO" checkout -q base
printf 'gamma_addition_here\n' >> "$TESTREPO/kept.txt"
git -C "$TESTREPO" commit -qam 'base gains the same line'

# A branch whose additions are nowhere in base -- the contrast case. Without it
# a guard that suppressed everything would still pass every assertion above.
git -C "$TESTREPO" checkout -q -b truly-stranded base
printf 'delta_never_landed_anywhere\nepsilon_never_landed_either\n' >> "$TESTREPO/kept.txt"
git -C "$TESTREPO" commit -qam 'stranded work'

# A branch touching a path base has since removed.
git -C "$TESTREPO" checkout -q -b touches-gone-path base
printf 'zeta_line_on_a_doomed_file\n' >> "$TESTREPO/moved.txt"
git -C "$TESTREPO" commit -qam 'edit the doomed file'
git -C "$TESTREPO" checkout -q base
git -C "$TESTREPO" rm -q moved.txt
git -C "$TESTREPO" commit -qm 'retire moved.txt'

# A branch that adds nothing at all.
git -C "$TESTREPO" branch -q empty-branch base

echo "== base_commit_for_issue =="
sha=$(cd "$TESTREPO" && base_commit_for_issue base 13224)
check "issue in a base commit subject" "yes" "$([ -n "$sha" ] && echo yes || echo no)"
sha=$(cd "$TESTREPO" && base_commit_for_issue base 1322)
check "prefix number does not match"   "no"  "$([ -n "$sha" ] && echo yes || echo no)"
sha=$(cd "$TESTREPO" && base_commit_for_issue base 999991)
check "absent issue finds nothing"     "no"  "$([ -n "$sha" ] && echo yes || echo no)"
sha=$(cd "$TESTREPO" && base_commit_for_issue base "")
check "empty issue finds nothing"      "no"  "$([ -n "$sha" ] && echo yes || echo no)"

echo "== branch_content_presence =="
check "landed content counted present" "1 1 0" "$(cd "$TESTREPO" && branch_content_presence base already-there)"
check "stranded content counted absent" "0 2 0" "$(cd "$TESTREPO" && branch_content_presence base truly-stranded)"
check "removed path reported gone"     "0 1 1" "$(cd "$TESTREPO" && branch_content_presence base touches-gone-path)"
check "no additions is all-zero"       "0 0 0" "$(cd "$TESTREPO" && branch_content_presence base empty-branch)"

echo "== branch_landing_evidence =="
# `gh` is stubbed so no test reaches the network; only `with-merged-pr` has one.
gh() {
    case "$*" in
        *"--head with-merged-pr"*) echo "4242" ;;
        *) echo "" ;;
    esac
}
ev=$(cd "$TESTREPO" && branch_landing_evidence base 'rescued/stash-x' 'base')
check "archival short-circuits"        "archival" "${ev%%|*}"
ev=$(cd "$TESTREPO" && branch_landing_evidence base 'with-merged-pr' 'truly-stranded')
check "merged PR on the head ref wins" "landed"   "${ev%%|*}"
ev=$(cd "$TESTREPO" && branch_landing_evidence base 'issue-13224' 'truly-stranded')
check "base commit carrying (#issue)"  "landed"   "${ev%%|*}"
ev=$(cd "$TESTREPO" && branch_landing_evidence base 'empty-branch')
check "adding nothing is landed"       "landed"   "${ev%%|*}"

# THE CONTRAST. A branch with no PR, no issue number, and content absent from
# base must still be reported -- that is the only reason the sweep exists.
ev=$(cd "$TESTREPO" && branch_landing_evidence base 'truly-stranded')
check "stranded branch stays reported" "unproven" "${ev%%|*}"
check "and carries its numbers"        "0/2 added lines present in base, 0 path(s) gone" "${ev#*|}"

# A high score is evidence, never a verdict: it must NOT suppress the report.
ev=$(cd "$TESTREPO" && branch_landing_evidence base 'already-there')
check "100% content is still unproven" "unproven" "${ev%%|*}"
unset -f gh

# The callers are workflow steps running `set -euo pipefail`. `grep` exits 1
# when NO added line landed -- the most important case the sweep has -- and
# under pipefail that aborted the whole job instead of reporting the branch.
# Asserted in a real strict-mode subshell, since this suite does not run with -e.
strict=$(bash -c '
    set -euo pipefail
    source "'"$HERE"'/branch-guards.sh"
    cd "'"$TESTREPO"'"
    branch_content_presence base truly-stranded
' 2>/dev/null || echo "ABORTED")
check "zero matches survives pipefail" "0 2 0" "$strict"

echo ""
echo "Passed: ${pass}  Failed: ${fail}"
[ "$fail" -eq 0 ]
