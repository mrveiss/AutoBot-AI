#!/usr/bin/env bash
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
#
# Reaping rules for `.session/HANDOFF-<branch>.md` files (#13848).
#
# A handoff exists for exactly one reader: the next session deciding whether to
# continue an unmerged branch. Once that branch is gone the file has no reader,
# but nothing removed it -- so the mandatory "read predecessor handoffs" start
# step grew a 100% false-positive rate, which is how a step stops being done.
#
# The reaper is deliberately conservative: it disposes of *landed* work only. A
# handoff whose branch is gone but whose status is `blocked` or `partial`
# describes work that did not land, and is reported for a human to turn into an
# issue -- never deleted.
#
# Source this file -- do not execute it:
#     source "$(git rev-parse --show-toplevel)/scripts/lib/session-handoffs.sh"

# Branch name a handoff file belongs to: `HANDOFF-issue-1234.md` -> `issue-1234`.
handoff_branch_name() {
    local path="$1" base
    base="$(basename "$path")"
    base="${base#HANDOFF-}"
    printf '%s' "${base%.md}"
}

# First word of the handoff's `status:` field, lowercased.
#
# The schema allows a qualifier after the keyword ("complete (design phase
# only)"), so only the leading token is significant. Prints nothing when the
# field is absent or ambiguous -- an unparseable handoff is never reaped.
#
# Scoped deliberately, because a first-match-anywhere search reaps live work:
# `.session/README.md` documents the schema as a literal `status: complete |
# blocked | partial` line, and pasting that template while filling a handoff in
# is the natural way to write one. A naive `grep -m1 '^status:'` reads the
# pasted template instead of the real field and reports `complete` for a
# handoff that actually says `blocked`. So:
#
#   * fenced blocks are skipped entirely -- a quoted schema is not a field;
#   * only the leading `key: value` block is read, never later prose;
#   * two competing top-level `status:` lines print nothing rather than
#     guessing, and so does a value still carrying the schema's `|`.
#
# Every one of those cases falls through to `keep-unlanded`: a handoff we
# cannot read with certainty is stranded work, never a delete.
handoff_status() {
    local path="$1" line
    [ -f "$path" ] || return 0
    line="$(awk '
        /^[[:space:]]*```/ { fence = !fence; next }
        fence               { next }
        /^[[:space:]]*$/    { if (seen) exit; next }
        /^[[:space:]]*#/    { if (seen) exit; next }
        /^[Ss][Tt][Aa][Tt][Uu][Ss][[:space:]]*:/ {
            seen = 1
            if (found++) { ambiguous = 1; exit }
            value = $0
            next
        }
        /^[A-Za-z_][A-Za-z0-9_]*[[:space:]]*:/ { seen = 1; next }
        { if (seen) exit }
        END { if (!ambiguous && found == 1) print value }
    ' "$path" 2>/dev/null || true)"
    [ -n "$line" ] || return 0
    line="${line#*:}"
    case "$line" in
        *"|"*) return 0 ;;
    esac
    line="$(printf '%s' "$line" | tr '[:upper:]' '[:lower:]' | awk '{print $1}')"
    printf '%s' "$line"
}

# Branch-existence check, with three outcomes rather than two:
#
#   0  the branch exists locally or on origin
#   1  git answered, and the branch is gone
#   2  git could not answer (not a repository, corrupt refs, ...)
#
# The third case is the point. `git show-ref --verify --quiet` exits 1 for "no
# such ref" and >=2 for a hard failure, and collapsing both into false lets a
# broken git turn every handoff into "branch gone" -- deleting the whole
# directory in one sweep. Callers must treat 2 as "cannot determine", not as
# permission to reap.
handoff_branch_exists() {
    local branch="$1" rc
    git show-ref --verify --quiet "refs/heads/${branch}"
    rc=$?
    [ "$rc" -eq 0 ] && return 0
    [ "$rc" -gt 1 ] && return 2
    git show-ref --verify --quiet "refs/remotes/origin/${branch}"
    rc=$?
    [ "$rc" -eq 0 ] && return 0
    [ "$rc" -gt 1 ] && return 2

    # Case-insensitive fallback. The branch name is recovered from the handoff's
    # *filename*, and a filename that differs only in case from the real branch
    # would otherwise read as "branch gone" and reap a handoff whose branch is
    # very much alive. Git refs are case-sensitive, so this cannot be folded
    # into the lookups above -- it is a separate, deliberately loose second pass.
    local lower refs
    lower="$(printf '%s' "$branch" | tr '[:upper:]' '[:lower:]')"
    refs="$(git for-each-ref --format='%(refname:short)' refs/heads refs/remotes/origin 2>/dev/null)"
    rc=$?
    [ "$rc" -ne 0 ] && return 2
    if printf '%s\n' "$refs" | sed 's|^origin/||' | tr '[:upper:]' '[:lower:]' \
        | grep -Fxq "$lower"; then
        return 0
    fi
    return 1
}

# Disposition for one handoff file. Prints exactly one of:
#
#   keep-live      the branch still exists -- the handoff still has a reader
#   keep-unknown   git could not say whether the branch exists; without that
#                  answer no delete is justified
#   keep-unlanded  the branch is gone but the handoff says the work did not
#                  land (`blocked` / `partial`, or no parseable status): this is
#                  stranded work and needs an issue, not a delete
#   reap           the branch is gone and the handoff records completed work
handoff_disposition() {
    local path="$1" branch status rc
    branch="$(handoff_branch_name "$path")"
    handoff_branch_exists "$branch"
    rc=$?
    if [ "$rc" -eq 0 ]; then
        printf 'keep-live'
        return 0
    fi
    if [ "$rc" -ge 2 ]; then
        printf 'keep-unknown'
        return 0
    fi
    status="$(handoff_status "$path")"
    if [ "$status" = "complete" ]; then
        printf 'reap'
    else
        printf 'keep-unlanded'
    fi
}

# Walk a `.session/` directory and act on every handoff in it.
#
#   reap_session_handoffs <session-dir> [--dry-run]
#
# Prints one line per file and a summary. Exit status is 0 even when files are
# kept: keeping is a normal outcome, not a failure.
reap_session_handoffs() {
    local session_dir="$1" dry_run="${2:-}"
    local reaped=0 kept_live=0 kept_unlanded=0 kept_unknown=0
    local path branch disposition

    if [ ! -d "$session_dir" ]; then
        echo "  No ${session_dir} directory found. Skipping."
        return 0
    fi

    for path in "$session_dir"/HANDOFF-*.md; do
        [ -e "$path" ] || continue
        branch="$(handoff_branch_name "$path")"
        disposition="$(handoff_disposition "$path")"
        case "$disposition" in
            keep-live)
                echo "  KEEP     HANDOFF-${branch}.md  (branch ${branch} still exists)"
                kept_live=$((kept_live + 1))
                ;;
            keep-unknown)
                echo "  KEEP     HANDOFF-${branch}.md  (git could not resolve branch ${branch} -- refusing to reap on an unanswered question)"
                kept_unknown=$((kept_unknown + 1))
                ;;
            keep-unlanded)
                echo "  STRANDED HANDOFF-${branch}.md  (branch ${branch} is gone, status='$(handoff_status "$path")' -- file an issue, do not delete)"
                kept_unlanded=$((kept_unlanded + 1))
                ;;
            reap)
                if [ "$dry_run" = "--dry-run" ]; then
                    echo "  WOULD REAP  HANDOFF-${branch}.md  (branch ${branch} gone, work complete)"
                else
                    rm -f "$path"
                    echo "  REAPED   HANDOFF-${branch}.md  (branch ${branch} gone, work complete)"
                fi
                reaped=$((reaped + 1))
                ;;
        esac
    done

    echo "  handoffs: reaped=${reaped} kept-live=${kept_live} stranded=${kept_unlanded} unresolved=${kept_unknown}"
    return 0
}
