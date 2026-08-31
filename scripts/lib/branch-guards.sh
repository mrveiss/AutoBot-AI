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
# Source this file -- do not execute it. Resolve it from your own location
# (${BASH_SOURCE[0]}), not via `git rev-parse` -- an ambient GIT_DIR makes
# that answer the caller's CWD instead of the repository root (#15245):
#     source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/../../scripts/lib/branch-guards.sh"

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
# inflate the count without carrying information. A branch whose additions are
# ALL below it is `unproven`, never `landed` -- see branch_content_presence.
BRANCH_CONTENT_MIN_LINE_CHARS="${BRANCH_CONTENT_MIN_LINE_CHARS:-8}"

# How many base commits carrying `(#issue)` to inspect when testing whether a
# branch's paths are covered by them. Bounds the cost on a long-lived umbrella.
BRANCH_ISSUE_COMMIT_SCAN_LIMIT="${BRANCH_ISSUE_COMMIT_SCAN_LIMIT:-50}"

# Minimum number of branches an enumeration must yield before a sweep's result
# means anything. A sweep whose enumeration broke reports zero problems, which
# is indistinguishable from a clean repository unless a floor says otherwise.
BRANCH_SWEEP_MIN_ENUMERATED="${BRANCH_SWEEP_MIN_ENUMERATED:-5}"

# Return 0 (true) when the branch name carries an archival prefix.
branch_is_archival() {
    local branch="$1" prefix
    for prefix in $BRANCH_ARCHIVAL_PREFIXES; do
        case "$branch" in "$prefix"*) return 0 ;; esac
    done
    return 1
}

# Fail when a sweep enumerated fewer branches than the floor. Callers run with
# `set -e`, so this aborts the job rather than letting an empty scan publish a
# report saying nothing is wrong.
branch_sweep_assert_reach() {
    local counted="$1" label="${2:-branch sweep}"
    if [ "$counted" -lt "$BRANCH_SWEEP_MIN_ENUMERATED" ]; then
        echo "::error::${label}: enumerated ${counted} branch(es), floor is" \
             "${BRANCH_SWEEP_MIN_ENUMERATED}. A sweep that scans nothing reports" \
             "clean over everything, so this is a failure, not a clean run." >&2
        return 1
    fi
    return 0
}

# Collapse whitespace so reflowed/reformatted lines still compare equal.
_branch_normalise_stream() {
    sed 's/[[:space:]]\{1,\}/ /g; s/^ //; s/ $//'
}

# Return 0 when <ref>'s tree is identical to <base>'s.
#
# This is the ONLY sound "there is nothing here to land" test. It is positive
# evidence about content. A zero-line content measurement is not: it equally
# means the measurement could not be made (#15366 review, blocking 1).
branch_tree_matches_base() {
    local base="$1" ref="$2" base_tree ref_tree
    base_tree=$(git rev-parse --verify --quiet "${base}^{tree}" 2>/dev/null) || return 1
    ref_tree=$(git rev-parse --verify --quiet "${ref}^{tree}" 2>/dev/null) || return 1
    [ -n "$base_tree" ] || return 1
    [ "$base_tree" = "$ref_tree" ]
}

# Print "<raw> <scorable> <present> <gone>" for a single path: added lines
# before the length filter, after it, how many of those are in base's copy, and
# 1 when base has no such path.
_branch_path_presence() {
    local base="$1" mb="$2" ref="$3" path="$4" tmp="$5" raw n m
    git diff --no-color "$mb" "$ref" -- "$path" 2>/dev/null \
        | sed -n 's/^+\([^+].*\)/\1/p' | _branch_normalise_stream | sort -u > "$tmp/raw"
    raw=$(wc -l < "$tmp/raw")
    awk -v k="$BRANCH_CONTENT_MIN_LINE_CHARS" 'length($0) >= k' "$tmp/raw" > "$tmp/add"
    n=$(wc -l < "$tmp/add")
    if [ "$n" -eq 0 ]; then
        printf '%s 0 0 0\n' "$raw"
        return 0
    fi
    if ! git cat-file -e "$base:$path" 2>/dev/null; then
        printf '%s %s 0 1\n' "$raw" "$n"
        return 0
    fi
    git show "$base:$path" 2>/dev/null | _branch_normalise_stream | sort -u > "$tmp/base"
    # `|| true` INSIDE the substitution: grep exits 1 when nothing matches --
    # the ordinary "none of these lines landed" case -- and callers run with
    # `set -o pipefail`, which would otherwise abort the sweep.
    m=$( { grep -Fxf "$tmp/base" "$tmp/add" 2>/dev/null || true; } | wc -l)
    printf '%s %s %s 0\n' "$raw" "$n" "$m"
}

# Print "<present> <total> <gone> <reason>" for the lines <ref> adds relative to
# its merge-base with <base>, counted against <base>'s own copy of each file.
#
# `reason` exists because "measured zero" and "could not measure" are different
# facts and the caller must not conflate them (#15366 review, blocking 1):
#   measured         -- total > 0, the numbers mean what they say
#   no-merge-base    -- unrelated histories or a shallow/broken fetch
#   no-added-lines   -- the diff is deletions, renames or mode changes only
#   short-lines-only -- every added line is below the length threshold
# Only `measured` carries information; the other three are absence of evidence,
# and the caller reports all of them as unproven.
branch_content_presence() {
    local base="$1" ref="$2" mb tmp path reason
    local raw=0 total=0 present=0 gone=0 p_raw p_n p_m p_gone
    mb=$(git merge-base "$base" "$ref" 2>/dev/null) || mb=""
    if [ -z "$mb" ]; then
        printf '0 0 0 no-merge-base\n'
        return 0
    fi
    tmp=$(mktemp -d)
    while IFS= read -r path; do
        [ -n "$path" ] || continue
        read -r p_raw p_n p_m p_gone \
            <<< "$(_branch_path_presence "$base" "$mb" "$ref" "$path" "$tmp")"
        raw=$((raw + p_raw))
        total=$((total + p_n))
        present=$((present + p_m))
        gone=$((gone + p_gone))
    done < <(git diff --name-only "$mb" "$ref" 2>/dev/null)
    rm -rf "$tmp"
    reason=measured
    if [ "$total" -eq 0 ]; then reason=short-lines-only; fi
    if [ "$raw" -eq 0 ]; then reason=no-added-lines; fi
    printf '%s %s %s %s\n' "$present" "$total" "$gone" "$reason"
}

# Print the number of a MERGED PR whose head ref is this branch AND whose merged
# head commit still accounts for <ref>'s current tip. Prints nothing otherwise.
#
# THE NAME ALONE IS NOT ENOUGH (#15366 review, blocking 3). Branches here are
# not reliably deleted, so a head-ref name gets reused and a branch gets pushed
# further after its PR merged. Asking only "did a PR with this head name ever
# merge" then reports `landed` over commits nobody reviewed. The tip must equal,
# or be an ancestor of, the commit the PR actually merged.
#
# Using `--is-ancestor` HERE is correct and is not the #15036 defect: it compares
# the branch against that PR's own recorded head, not against a squash-merged
# base, so no squash rewrite sits between the two commits.
#
# <base_branch>, when given, also requires the PR to have targeted it -- a PR
# merged into some other target says nothing about this base.
merged_pr_for_branch() {
    local branch="$1" ref="${2:-$1}" base_branch="${3:-}" tip rows pr oid
    [ -n "$branch" ] || return 0
    tip=$(git rev-parse --verify --quiet "${ref}^{commit}" 2>/dev/null) || return 0
    [ -n "$tip" ] || return 0
    rows=$(gh pr list --head "$branch" --state merged \
        --json number,headRefOid,baseRefName 2>/dev/null \
        | jq -r --arg b "$base_branch" \
            '.[] | select($b == "" or .baseRefName == $b)
                 | "\(.number) \(.headRefOid)"' 2>/dev/null) || rows=""
    [ -n "$rows" ] || return 0
    while read -r pr oid; do
        [ -n "$oid" ] || continue
        if [ "$oid" = "$tip" ] || git merge-base --is-ancestor "$tip" "$oid" 2>/dev/null; then
            printf '%s' "$pr"
            return 0
        fi
    done <<< "$rows"
    return 0
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
#
# On its own this is NOT evidence that a given branch landed -- see
# branch_paths_covered_for_issue.
base_commit_for_issue() {
    local base="$1" issue="$2"
    [ -n "$issue" ] || return 0
    git log "$base" --fixed-strings --grep="(#${issue})" \
        --format='%h' -n 1 2>/dev/null || true
}

# Return 0 when every path <ref> changes is also changed by some commit on
# <base> carrying `(#issue)`.
#
# WHY A BARE `(#issue)` MATCH IS NOT ENOUGH (#15366 review, blocking 2). The
# issue number comes from the BRANCH NAME, so every sibling branch off one
# umbrella issue matches the same commit. This repository decomposes work into
# exactly that shape -- lanes off a single issue -- so `issue-15036-lane-a`
# would read as landed the moment `lane-b` merged. Requiring the landed
# commits to have touched this branch's own files ties the evidence to this
# branch's content, and sibling lanes touching different files no longer alias.
branch_paths_covered_for_issue() {
    local base="$1" ref="$2" issue="$3" mb tmp sha path paths=0 rc=0
    [ -n "$issue" ] || return 1
    mb=$(git merge-base "$base" "$ref" 2>/dev/null) || return 1
    [ -n "$mb" ] || return 1
    tmp=$(mktemp -d)
    git log "$base" --fixed-strings --grep="(#${issue})" --format='%H' \
        -n "$BRANCH_ISSUE_COMMIT_SCAN_LIMIT" 2>/dev/null > "$tmp/shas"
    while IFS= read -r sha; do
        [ -n "$sha" ] || continue
        git show --name-only --format='' "$sha" 2>/dev/null
    done < "$tmp/shas" | sort -u > "$tmp/covered"
    while IFS= read -r path; do
        [ -n "$path" ] || continue
        paths=$((paths + 1))
        grep -Fxq "$path" "$tmp/covered" 2>/dev/null || rc=1
    done < <(git diff --name-only "$mb" "$ref" 2>/dev/null)
    rm -rf "$tmp"
    # A branch changing nothing has no content to tie to the commit.
    [ "$paths" -gt 0 ] || rc=1
    return "$rc"
}

# Print landing evidence derived from an issue number, or nothing. Split out of
# `branch_landing_evidence` to keep both functions inside the 30-line limit.
_branch_issue_evidence() {
    local base="$1" issue="$2" ref="$3" pr sha
    [ -n "$issue" ] || return 0
    pr=$(merged_pr_for_issue "$issue")
    if [ -n "$pr" ]; then
        printf 'PR #%s merged, closing issue #%s' "$pr" "$issue"
        return 0
    fi
    sha=$(base_commit_for_issue "$base" "$issue")
    [ -n "$sha" ] || return 0
    if branch_paths_covered_for_issue "$base" "$ref" "$issue"; then
        printf '%s on %s carries (#%s) and covers every path this branch changes' \
            "$sha" "$base" "$issue"
    fi
    return 0
}

# Print "<status>|<evidence>" for <branch> against <base>. Status is `landed`,
# `archival` or `unproven`; reporting sweeps must report only `unproven`, and
# must print the evidence alongside so triage does not have to re-derive it.
#
# `landed` is only ever printed on POSITIVE evidence: an identical tree, a
# merged PR that accounts for this tip, or base commits that carry this
# branch's issue AND touched its files. Absence of a measurement is `unproven`.
#
# <branch> is the branch NAME (prefix and issue-number rules read names, not
# refs). <ref> is the revision to read content from and defaults to <branch>;
# callers sweeping remote branches pass `origin/<branch>`.
branch_landing_evidence() {
    local base="$1" branch="$2" ref="${3:-$2}" pr detail present total gone reason
    if branch_is_archival "$branch"; then
        printf 'archival|point-in-time record, not a line of work\n'
        return 0
    fi
    if branch_tree_matches_base "$base" "$ref"; then
        printf 'landed|tree is identical to %s\n' "$base"
        return 0
    fi
    pr=$(merged_pr_for_branch "$branch" "$ref" "${base##*/}")
    if [ -n "$pr" ]; then
        printf 'landed|PR #%s merged, and it accounts for this tip\n' "$pr"
        return 0
    fi
    detail=$(_branch_issue_evidence "$base" "$(extract_issue_number "$branch")" "$ref")
    if [ -n "$detail" ]; then
        printf 'landed|%s\n' "$detail"
        return 0
    fi
    present=0; total=0; gone=0; reason=no-added-lines
    read -r present total gone reason <<< "$(branch_content_presence "$base" "$ref")" || true
    if [ "$total" -eq 0 ]; then
        printf 'unproven|no content could be measured (%s)\n' "$reason"
        return 0
    fi
    printf 'unproven|%s/%s added lines present in %s, %s path(s) gone\n' \
        "$present" "$total" "$base" "$gone"
}
