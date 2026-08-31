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

# ---------------------------------------------------------------------------
# Landing evidence (#15036)
#
# This repository SQUASH-merges. A squash merge creates a commit on the base
# that is not a descendant of the branch's commits, so both
# `git merge-base --is-ancestor <branch> <base>` and `git branch --merged` are
# false for every branch this repository has ever merged. Any sweep that uses
# either as its landed/unlanded test reports 100% false positives -- which is
# what #11703, #13603 and #4324 each produced, and why their reports were
# ignored.
#
# What is sound, in descending order of strength:
#   1. An `issue-NNNN`/`hotfix-NNNN` branch whose closing PR is merged. This is
#      the same check `branch-cleanup.yml` already trusts to DELETE a branch, so
#      it is more than strong enough to suppress a report.
#   2. A branch that adds nothing relative to its merge-base.
#   3. An archival ref that is not a line of work at all (see below).
# Everything else is UNPROVEN, and is reported with its per-file numbers rather
# than with a verdict. Content scoring alone cannot decide it: calibrated on
# #14078's 18 hand-verified rescued stashes, confirmed-landed changes scored as
# low as 53% while confirmed-unlanded scored 47-48%. The ranges overlap, so the
# count is evidence for a human, never a verdict.
# ---------------------------------------------------------------------------

# Branch-name prefixes that are archival records rather than lines of work, and
# so are never reported as stranded. `rescued/stash-*` are point-in-time
# snapshots of rescued working trees (#14078); `release/changelog-*` hold the
# only copy of released changelog content (#15167). Override via the
# BRANCH_ARCHIVAL_PREFIXES environment variable (space separated).
BRANCH_ARCHIVAL_PREFIXES="${BRANCH_ARCHIVAL_PREFIXES:-rescued/ release/changelog-}"

# Added lines shorter than this are ignored when counting content presence:
# `}`, `else:` and bare imports match somewhere in almost any file and would
# inflate the count without carrying information.
BRANCH_CONTENT_MIN_LINE_CHARS="${BRANCH_CONTENT_MIN_LINE_CHARS:-8}"

# Return 0 (true) when the branch name carries an archival prefix.
branch_is_archival() {
    local branch="$1" prefix
    for prefix in $BRANCH_ARCHIVAL_PREFIXES; do
        case "$branch" in "$prefix"*) return 0 ;; esac
    done
    return 1
}

# Collapse whitespace so reflowed/reformatted lines still compare equal.
_branch_normalise_stream() {
    sed 's/[[:space:]]\{1,\}/ /g; s/^ //; s/ $//'
}

# Print "<present> <total> <paths_gone>" for the lines <branch> adds relative to
# its merge-base with <base>, counted against <base>'s own copy of each file.
# A path that no longer exists in <base> is counted as gone -- that is a landing
# outcome (the file moved or was retired), not a stranded one.
branch_content_presence() {
    local base="$1" branch="$2" mb tmp path total=0 present=0 gone=0 n m
    mb=$(git merge-base "$base" "$branch" 2>/dev/null) || { printf '0 0 0\n'; return 0; }
    tmp=$(mktemp -d)
    while IFS= read -r path; do
        [ -n "$path" ] || continue
        git diff --no-color "$mb" "$branch" -- "$path" 2>/dev/null \
            | sed -n 's/^+\([^+].*\)/\1/p' | _branch_normalise_stream \
            | awk -v k="$BRANCH_CONTENT_MIN_LINE_CHARS" 'length($0) >= k' \
            | sort -u > "$tmp/add"
        n=$(wc -l < "$tmp/add")
        [ "$n" -gt 0 ] || continue
        if git cat-file -e "$base:$path" 2>/dev/null; then
            git show "$base:$path" 2>/dev/null | _branch_normalise_stream | sort -u > "$tmp/base"
            # `|| true` INSIDE the substitution: grep exits 1 when nothing
            # matches -- the ordinary "none of these lines landed" case -- and
            # callers run with `set -o pipefail`, which would abort the sweep.
            m=$( { grep -Fxf "$tmp/base" "$tmp/add" 2>/dev/null || true; } | wc -l)
        else
            gone=$((gone + 1))
            m=0
        fi
        total=$((total + n))
        present=$((present + m))
    done < <(git diff --name-only "$mb" "$branch" 2>/dev/null)
    rm -rf "$tmp"
    printf '%s %s %s\n' "$present" "$total" "$gone"
}

# Print the number of a MERGED PR whose head ref is this branch, or nothing.
# This is the most direct landing evidence there is -- the branch itself went
# through review and was merged -- and unlike `merged_pr_for_issue` it does not
# depend on GitHub having recorded a closing-issue link.
merged_pr_for_branch() {
    local branch="$1"
    [ -n "$branch" ] || return 0
    gh pr list --head "$branch" --state merged --json number \
        -q '.[0].number // empty' 2>/dev/null || true
}

# Print the abbreviated SHA of a commit on <base> whose subject carries
# `(#<issue>)`, or nothing.
#
# WHY THIS EXISTS ALONGSIDE `merged_pr_for_issue`. That helper filters on
# `closingIssuesReferences`, which is empty for this repository's merged PRs --
# closing keywords do not create the link here -- so it answers "no" for every
# issue and can never suppress anything. The repository's real issue-to-commit
# linkage is the commit-subject convention `<type>(scope): <desc> (#issue)`,
# which the squash-merge preserves on the base branch. The trailing `)` makes
# the fixed-string match unambiguous: `(#1322)` cannot match `(#13224)`.
base_commit_for_issue() {
    local base="$1" issue="$2"
    [ -n "$issue" ] || return 0
    git log "$base" --fixed-strings --grep="(#${issue})" \
        --format='%h' -n 1 2>/dev/null || true
}

# Print landing evidence derived from an issue number, or nothing. Split out of
# `branch_landing_evidence` to keep both functions inside the 30-line limit.
_branch_issue_evidence() {
    local base="$1" issue="$2" pr sha
    [ -n "$issue" ] || return 0
    pr=$(merged_pr_for_issue "$issue")
    if [ -n "$pr" ]; then
        printf 'PR #%s merged, closing issue #%s' "$pr" "$issue"
        return 0
    fi
    sha=$(base_commit_for_issue "$base" "$issue")
    if [ -n "$sha" ]; then
        printf '%s on %s carries (#%s)' "$sha" "$base" "$issue"
    fi
    return 0
}

# Print "<status>|<evidence>" for <branch> against <base>. Status is `landed`,
# `archival` or `unproven`; reporting sweeps must report only `unproven`, and
# must print the evidence alongside so triage does not have to re-derive it.
#
# <branch> is the branch NAME (prefix and issue-number rules read names, not
# refs). <ref> is the revision to read content from and defaults to <branch>;
# callers sweeping remote branches pass `origin/<branch>`.
branch_landing_evidence() {
    local base="$1" branch="$2" ref="${3:-$2}" pr detail present total gone
    if branch_is_archival "$branch"; then
        printf 'archival|point-in-time record, not a line of work\n'
        return 0
    fi
    pr=$(merged_pr_for_branch "$branch")
    if [ -n "$pr" ]; then
        printf 'landed|PR #%s merged with this branch as its head\n' "$pr"
        return 0
    fi
    detail=$(_branch_issue_evidence "$base" "$(extract_issue_number "$branch")")
    if [ -n "$detail" ]; then
        printf 'landed|%s\n' "$detail"
        return 0
    fi
    # Pre-seeded so a `read` that returns 1 on an unexpected EOF cannot leave
    # the arithmetic below comparing an unset variable under `set -eu`.
    present=0
    total=0
    gone=0
    read -r present total gone <<< "$(branch_content_presence "$base" "$ref")" || true
    if [ "$total" -eq 0 ]; then
        printf 'landed|adds nothing relative to %s\n' "$base"
        return 0
    fi
    printf 'unproven|%s/%s added lines present in %s, %s path(s) gone\n' \
        "$present" "$total" "$base" "$gone"
}
