#!/usr/bin/env bash
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
#
# Canonical base/head resolution and changed-file scoping for CI guards (#13984).
#
# Five changed-files guards each resolved a base ref and status-checked their
# own git calls, and now all source this instead:
# pipeline-scripts/check-pre-commit-hook-pr.sh,
# .github/workflows/code-quality.yml,
# .github/workflows/enforce-precommit.yml, scripts/lint-conventions.sh
# and scripts/verify-done.sh. All of them encode the same hard-won rules, so the
# next correction had to be applied five times or the copies drifted.
#
# Source this file -- do not execute it. Resolve it from your own location
# (${BASH_SOURCE[0]}), not via `git rev-parse` -- an ambient GIT_DIR makes
# that answer the caller's CWD instead of the repository root (#15245):
#
#     source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/../../scripts/lib/git-scope.sh"
#
# THE RULES, and what each one cost to learn
# ------------------------------------------
#
# * On a `pull_request` the checkout is the MERGE commit. HEAD^1 is the base tip
#   as of the event and HEAD^2 is the pull request head, so `HEAD^1..HEAD` is
#   exactly this pull request's changes. Resolving `origin/<base>` instead uses
#   the base's CURRENT tip, which drags every PR merged in the meantime into the
#   diff -- worst on a re-run, where HEAD is frozen and origin/<base> is fetched
#   fresh (#13880).
# * The event payload's base.sha is NOT guaranteed to be in the clone under
#   `fetch-depth: 2`, whereas HEAD^1 always is. So the payload is a FALLBACK,
#   never the first choice.
# * An unresolvable ref must be FATAL. actions/checkout defaults to
#   `fetch-depth: 1`, the base commit is then absent, `git diff` fatals, and a
#   `|| true` turns that into an empty file list which every caller reads as
#   "nothing changed" and reports clean. Four CI steps were green no-ops for
#   exactly this reason (#13880).
# * A failed `git diff` and an empty `git diff` must be told apart at the source.
#   They are indistinguishable to every caller once the output is a variable.
#
# Every function here is under 30 lines and independently testable; see
# scripts/lib/git-scope_test.sh.

if [ -n "${_AUTOBOT_GIT_SCOPE_LOADED:-}" ]; then
    return 0
fi
_AUTOBOT_GIT_SCOPE_LOADED=1

# Emit a fatal message and fail. Callers running under `set -e` stop here; the
# non-zero return matters for callers that do not.
#
# GITHUB_ACTIONS is honoured so a failure inside a workflow surfaces as an
# annotation rather than a line of log nobody reads.
git_scope_die() {
    if [ -n "${GITHUB_ACTIONS:-}" ]; then
        printf '::error::%s\n' "$*" >&2
    else
        printf 'FATAL: %s\n' "$*" >&2
    fi
    return 1
}

# True when $1 names a resolvable commit.
git_scope_have_commit() {
    [ -n "${1:-}" ] || return 1
    git cat-file -e "${1}^{commit}" 2>/dev/null
}

# Resolve the base ref for "what did this change set touch?".
#
# Args: $1 head ref (default: $GITHUB_SHA, else HEAD)
#       $2 optional event-payload base sha (github.event.pull_request.base.sha)
#
# Order, first match wins -- this is the UNION of what the five call sites did,
# not a pick of one of them:
#   1. merge-commit parents (the only source that is always present and always
#      scoped to this pull request alone)
#   2. the event payload's base sha, when it actually resolves in this clone
#   3. origin/$GITHUB_BASE_REF, the branch-name route
#   4. <head>^, the last resort
# Prints the base ref on success; fatal when nothing resolves, because "no base"
# must never degrade into "no changes".
git_scope_resolve_base() {
    local head="${1:-${GITHUB_SHA:-HEAD}}" event_base="${2:-}"
    if git_scope_have_commit "${head}^2" && git_scope_have_commit "${head}^1"; then
        printf '%s\n' "${head}^1"
        return 0
    fi
    if git_scope_have_commit "$event_base"; then
        printf '%s\n' "$event_base"
        return 0
    fi
    local from_branch
    if [ -n "${GITHUB_BASE_REF:-}" ] && from_branch=$(git rev-parse --verify --quiet "origin/${GITHUB_BASE_REF}^{commit}" 2>/dev/null) \
        && [ -n "$from_branch" ]; then
        printf '%s\n' "$from_branch"
        return 0
    fi
    if git_scope_have_commit "${head}^"; then
        printf '%s\n' "${head}^"
        return 0
    fi
    git_scope_die "cannot resolve a base commit for '${head}' — refusing to report an uncomputed scope as 'no changes'. A shallow checkout cannot diff against the base; set 'fetch-depth: 0' (or 2 for a merge ref) on actions/checkout."
}

# Resolve a base when the CALLER may have supplied one explicitly.
#
# An explicitly supplied base is AUTHORITATIVE: it is used verbatim, so a base
# that does not resolve fails loudly at the validation step instead of being
# silently replaced by a different scope. That is the whole difference between
# this and git_scope_resolve_base, whose $2 is the EVENT PAYLOAD's base.sha --
# documented as legitimately absent under `fetch-depth: 2`, and therefore a
# fallback rather than an instruction.
#
# Collapsing the two would reintroduce the failure this family keeps producing:
# a shallow clone's missing base quietly becoming "<head>^", a different and
# smaller scope, reported as a successful scan.
git_scope_resolve_base_explicit() {
    local head="${1:-${GITHUB_SHA:-HEAD}}" explicit="${2:-}"
    if [ -n "$explicit" ]; then
        printf '%s\n' "$explicit"
        return 0
    fi
    git_scope_resolve_base "$head"
}

# Every argument must name a resolvable commit, or die naming the first that
# does not. Callers pass BOTH ends of the range: a resolvable base and an
# unresolvable head fails just as silently as the reverse.
git_scope_require_commits() {
    local ref
    for ref in "$@"; do
        git_scope_have_commit "$ref" && continue
        git_scope_die "'${ref}' does not resolve in this clone. A shallow checkout cannot compare against the base — set 'fetch-depth: 0' on actions/checkout. Refusing to report 'no changed files' for a scope that could not be computed." || return 1
    done
}

# Split an `A..B` or `A...B` range string. $2 selects "base" or "head".
# Three-dot ranges are split on the three-dot separator FIRST: stripping `..`
# from `A...B` leaves a stray dot on the base ref, which then does not resolve.
git_scope_split_range() {
    local range="${1:-}" which="${2:-base}"
    case "$range" in
        *...*) [ "$which" = "base" ] && printf '%s\n' "${range%%...*}" || printf '%s\n' "${range##*...}" ;;
        *..*)  [ "$which" = "base" ] && printf '%s\n' "${range%%..*}"  || printf '%s\n' "${range##*..}" ;;
        *)     git_scope_die "'${range}' is not an A..B or A...B range" ;;
    esac
}

# Changed file names for <base>..<head>, optionally narrowed by pathspecs.
#
# git's own exit status is inspected and a failure is fatal. The distinction
# this preserves is the one that matters: an empty-but-successful diff is a
# legitimate "nothing in scope", a failed diff is not, and once the output is
# captured into a variable the two look identical.
git_scope_diff_names() {
    local base="${1:?base required}" head="${2:?head required}"
    shift 2
    local out
    if ! out=$(git diff --name-only --diff-filter=ACMRT "$base" "$head" ${1:+--} "$@"); then
        git_scope_die "git diff failed for ${base}..${head} — refusing to report clean." || return 1
    fi
    printf '%s' "${out:+$out
}"
}

# Changed file names for <base>...<head> (three-dot).
#
# Three-dot is "what HEAD introduced since the merge base", so files that other
# merged pull requests touched on the base never enter this change set's scope.
git_scope_diff_names_symmetric() {
    local base="${1:?base required}" head="${2:?head required}"
    shift 2
    local out
    if ! out=$(git diff --name-only --diff-filter=ACMRT "${base}...${head}" ${1:+--} "$@"); then
        git_scope_die "git diff failed for ${base}...${head} — refusing to report clean." || return 1
    fi
    printf '%s' "${out:+$out
}"
}

# Filter a newline-separated path list on stdin down to files that exist on
# disk. `git diff --name-only` still names deleted paths, and a checker handed
# one either crashes or -- worse -- reports something about a file that is not
# there.
git_scope_existing_files() {
    local path
    while IFS= read -r path; do
        [ -n "$path" ] && [ -f "$path" ] && printf '%s\n' "$path"
    done
    return 0
}

# Anti-no-op guard, for callers whose scope is NOT narrowed by a pathspec.
#
# The original defect was a broken range yielding "0 file(s) in scope" and three
# green checks. Any change set reaches such a caller with at least one file, so
# 0 means the range is wrong -- fail red rather than pass having scanned
# nothing. Callers that DO narrow by pathspec must not use this: for them zero
# files is a legitimate skip, and that is a per-caller policy, not a rule about
# ranges.
git_scope_require_nonempty() {
    local count="${1:-0}" label="${2:-the resolved range}"
    [ "$count" -gt 0 ] && return 0
    git_scope_die "0 files in scope for '${label}' — the range is wrong. Refusing to report clean on an unscanned tree." || return 1
}

# Validate an explicitly supplied base ref (a --base option or an env default).
# Same fatal shape as the rest: a base that does not resolve makes every
# later comparison silently degrade into "everything looks landed".
git_scope_require_base_ref() {
    local base="${1:?base required}"
    git rev-parse --verify --quiet "${base}^{commit}" >/dev/null && return 0
    git_scope_die "base ref '${base}' does not resolve in this clone. Every verdict depends on it, and a failed comparison is indistinguishable from 'nothing unlanded'." || return 1
}
