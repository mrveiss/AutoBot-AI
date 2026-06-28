#!/usr/bin/env bash
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
#
# Shared guards for safe automated branch pruning.
#
# Prevents the #10035 failure class -- a freshly-pushed, unmerged branch being
# deleted because:
#   (a) a token in its name was misread as a GitHub issue number
#       (e.g. the year in `chore/triage-delta-2026-06-12`, or the work-item id
#        in `MVA-3847-fix`), or
#   (b) it was pushed seconds ago and its PR does not exist yet (push->PR gap), or
#   (c) it still has an open PR.
#
# Source this file -- do not execute it:
#     source "$(git rev-parse --show-toplevel)/scripts/lib/branch-guards.sh"

# Minimum age (hours) a branch must reach before automated pruning may delete
# it. Protects in-flight work whose PR has not been created yet. Override via
# the BRANCH_MIN_AGE_HOURS environment variable.
BRANCH_MIN_AGE_HOURS="${BRANCH_MIN_AGE_HOURS:-24}"

# Extract a GitHub issue number from a branch name.
#
# ONLY AutoBot `issue-NNNN` / `hotfix-NNNN` branches carry a GitHub issue
# number. Date-stamped chores, Paperclip `MVA-NNNN` work-items, and feature
# slugs must NOT match -- a wrong match deletes an unrelated branch (#10035).
# Branches without an issue/hotfix token are intentionally left to the
# merged-ancestor detection instead.
#
# Prints the issue number, or nothing when the branch carries none.
extract_issue_number() {
    local branch="$1"
    printf '%s' "$branch" \
        | grep -oP '(?:^|[-_/])(?:issue|hotfix)[-_/]\K[0-9]+' \
        | head -1 || true
}

# Return 0 (true) when the ref's tip commit is younger than
# BRANCH_MIN_AGE_HOURS. `ref` must be resolvable (e.g. `origin/<branch>` for a
# remote branch, `<branch>` for a local one). A missing/unreadable ref is
# treated as "not recent" so it does not block legitimate cleanup.
branch_recently_pushed() {
    local ref="$1"
    local last_ts now_ts age_h
    last_ts=$(git log -1 --format=%ct "$ref" 2>/dev/null || echo 0)
    # git may exit 0 yet print nothing for an edge/ambiguous ref -- treat an
    # empty or non-numeric timestamp as "not recent" (do not let it bypass the
    # numeric comparison, which would abort with rc=2 under set -e callers).
    [[ "$last_ts" =~ ^[0-9]+$ ]] || return 1
    [ "$last_ts" -eq 0 ] && return 1
    now_ts=$(date +%s)
    age_h=$(( (now_ts - last_ts) / 3600 ))
    [ "$age_h" -lt "$BRANCH_MIN_AGE_HOURS" ]
}

# Return 0 (true) when an open PR has this branch as its head. Requires an
# authenticated `gh`. On any error it returns false (no open PR found) rather
# than blocking cleanup -- callers combine it with other guards.
branch_has_open_pr() {
    local branch="$1"
    local pr
    pr=$(gh pr list --head "$branch" --state open --json number -q '.[0].number' 2>/dev/null || true)
    [ -n "$pr" ]
}

# Print the number of a merged PR that ACTUALLY closes the given issue, or
# nothing when none exists. Requires an authenticated `gh`.
#
# A bare `gh pr list --search "$issue_number"` over-matches (#10114): the search
# index hits the number anywhere -- title, body, comments -- and even in a
# superstring like `#19943` when searching for `9943`. A branch for an issue
# whose number merely appears in some unrelated merged PR would then pass the
# merge-confirmation gate. To avoid that, this filters the candidate PRs to
# those whose `closingIssuesReferences` contains the EXACT issue number. On any
# error it prints nothing so callers fall through to "no merged PR found"
# (which keeps the branch -- the safe default).
merged_pr_for_issue() {
    local issue_number="$1"
    [ -n "$issue_number" ] || return 0
    gh pr list --search "$issue_number" --state merged \
        --json number,closingIssuesReferences 2>/dev/null \
        | jq -r --argjson n "$issue_number" \
            'map(select(any(.closingIssuesReferences[]?; .number == $n)))
             | .[0].number // empty' 2>/dev/null \
        || true
}
