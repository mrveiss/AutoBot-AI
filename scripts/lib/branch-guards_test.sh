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

echo ""
echo "Passed: ${pass}  Failed: ${fail}"
[ "$fail" -eq 0 ]
