#!/usr/bin/env bash
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
#
# Fail when pipeline-scripts/hardcoded_values_baseline.txt has GROWN (#14371).
#
# The baseline records the hardcoded-value findings that already existed when
# the three detectors were merged, and hv_partition suppresses anything it
# lists. `--audit-baseline` checks one direction -- that no entry has been
# stranded by a fix -- so the file cannot reference what no longer exists.
# Nothing checked the other direction, and that was a one-line bypass of the
# entire gate:
#
#     hardcode a new fleet IP, and in the SAME change append
#     `1|ssot|autobot-backend/new_file.py|<ip>` to the baseline.
#
# hv_partition then suppresses it as already-known, ssot-coverage reports
# ssot_violations=0, and the pull request merges green over a violation the
# detector found correctly. The count-in-key design already made a bump on an
# EXISTING key cost something; a brand-new key was the more direct route and was
# undefended. The invariant was written in a comment in the library and asserted
# nowhere -- which is the same shape as every other defect this change fixes.
#
# Shrinking stays silent. Removals and decreases are how a fixed violation
# leaves, and a guard that blocked those would make the file unmaintainable.
#
# ONE addition route exists (#14919), and only one: an entry whose file this
# change leaves byte-identical to the base ref, carrying a `# reviewed: #<issue>`
# justification that this change itself adds directly above it. That is the
# detection-rule case -- a new rule matching code that was already there -- and
# it is separated from the bypass case mechanically, by the diff, not by a
# permission an appended line could grant itself. An addition in a file this
# change touches has no route at all. See the block above the adjudication loop.
#
# FAIL-CLOSED EVERYWHERE. An unresolvable base, an unreadable baseline on either
# side, or a parse failure is a FAILURE, never a skip: a guard that reads
# "cannot determine" as "clean" is precisely the class being fixed here.
#
# Usage: check_baseline_no_growth.sh
#   HEAD_SHA / GITHUB_SHA  head commit  (default HEAD)
#   BASE_SHA               event payload base, used only as a fallback

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# shellcheck source=scripts/lib/git-scope.sh
source "${PROJECT_ROOT}/scripts/lib/git-scope.sh" || {
    echo "FATAL: cannot load scripts/lib/git-scope.sh — refusing to report clean" >&2
    exit 1
}
# shellcheck source=scripts/lib/hardcoded-value-rules.sh
source "${PROJECT_ROOT}/scripts/lib/hardcoded-value-rules.sh" || {
    echo "FATAL: cannot load scripts/lib/hardcoded-value-rules.sh — refusing to report clean" >&2
    exit 1
}

BASELINE_REL="pipeline-scripts/hardcoded_values_baseline.txt"
HEAD_SHA="${HEAD_SHA:-${GITHUB_SHA:-HEAD}}"

cd "$PROJECT_ROOT"

# Base resolution is the canonical one built in this same change (#13984): the
# merge-commit rule, the payload fallback, the branch-name fallback and "an
# unresolvable ref is FATAL". A hardcoded origin/main would be wrong on every
# pull request in this repository, which targets Dev_new_gui.
base=$(git_scope_resolve_base "$HEAD_SHA" "${BASE_SHA:-}") || exit 1
git_scope_require_commits "$base" "$HEAD_SHA" || exit 1

if ! git cat-file -e "${base}:${BASELINE_REL}" 2>/dev/null; then
    # The baseline does not exist at the base ref, so this change is the one
    # introducing it and every key is new by construction. Not a bypass route:
    # deleting the file to reset it makes the detector itself fatal on the very
    # next run (hv_parse_baseline_into treats an absent baseline as FATAL), so a
    # delete-and-regrow lands red before it can land green.
    echo "check-baseline-no-growth: ${BASELINE_REL} does not exist at ${base} —"
    echo "  this change introduces it. Its contents are checked by --audit-baseline,"
    echo "  which fails on any entry the detector does not currently produce."
    exit 0
fi

OLD_BASELINE=$(mktemp)
trap 'rm -f "$OLD_BASELINE"' EXIT
if ! git show "${base}:${BASELINE_REL}" > "$OLD_BASELINE"; then
    echo "FATAL: cannot read ${BASELINE_REL} at ${base} — refusing to report clean" >&2
    exit 1
fi

set +e
growth=$(hv_baseline_growth "$OLD_BASELINE" "${PROJECT_ROOT}/${BASELINE_REL}")
rc=$?
set -e

# The verdict is settled BEFORE any reporting runs, so an unparseable or missing
# baseline exits through the designed FATAL rather than through whatever the
# first reporting command happens to do with it. Found by mutation: with the
# totals computed here, deleting the baseline exited 2 out of `awk` under
# `set -e` and never reached this case at all. Still fail-closed either way, but
# a guard whose failure path is accidental is one nobody can reason about.
case "$rc" in
    0|1) ;;  # a real verdict; reported below
    *)
        echo "FATAL: could not compare the baselines (exit ${rc}) — refusing to report clean" >&2
        exit 1
        ;;
esac

# Both files are known to parse by this point, so the totals cannot fail.
sum_of() { awk -F'|' '/^[0-9]/ { total += $1 } END { print total + 0 }' "$1"; }
old_total=$(sum_of "$OLD_BASELINE")
new_total=$(sum_of "${PROJECT_ROOT}/${BASELINE_REL}")

if [ "$rc" -eq 0 ]; then
    echo "check-baseline-no-growth: no key added and no count increased against ${base}"
    echo "  suppressed findings: ${old_total} -> ${new_total}"
    exit 0
fi

# ── the reviewed-addition route (#14919) ─────────────────────────────────────
#
# Until now the guard had exactly two outcomes, "no growth, exit 0" and
# "growth, exit 1", while its own failure text told the reader that growth was
# "a decision for a reviewer to take deliberately". No such decision existed.
# A guard whose message promises a route it does not implement is a guard that
# acquires an illegitimate one the first time the route is genuinely needed.
#
# So there is now one route, and it is deliberately narrow enough that it
# cannot be the bypass this file exists to close. An addition is permitted only
# when BOTH hold, and neither can be satisfied by accident:
#
#   1. THE CHANGE DID NOT AUTHOR THE CONTENT. The entry's file must exist at
#      the base ref and be byte-identical to the file in this tree. That is the
#      mechanical difference between the two kinds of addition:
#
#        * a new DETECTION RULE that suddenly matches code which was already
#          there — the file is untouched, the finding is genuinely pre-existing,
#          and refusing it would mean "fixing" code this change never wrote;
#        * a new HARDCODED VALUE — the file necessarily changed, which is the
#          one-line bypass (hardcode it, append its key in the same commit).
#
#      The second can never reach the route at all. No marker, env var or label
#      opens it, because the test is on the diff rather than on permission.
#
#   2. A WRITTEN JUSTIFICATION, NEW IN THIS CHANGE. The nearest non-blank line
#      above the entry must read `# reviewed: #<issue> <why>`, and that exact
#      line must be among the lines this change ADDS to the baseline. A comment
#      that was already in the file cannot be re-used to cover a later append,
#      and the justification lands as a diff line adjacent to the entry it
#      justifies, so a reviewer sees both together or neither.
#
#      The marker is a preceding COMMENT and not a suffix on the entry itself
#      because the key is `<count>|<class>|<file>|<value>` and everything after
#      the first `|` is the key: a trailing `# reviewed: …` would silently
#      change the key so it matched no finding at all.
#
# What this route deliberately does NOT cover: a rename. Moving a file that
# carries a baselined value changes the entry's path, so the new path is absent
# at base and the addition is refused. That is the same answer as before this
# route existed — it is not a regression, and loosening test 1 to "the content
# existed at base under some name" would also admit a verbatim COPY of a file,
# which duplicates a hardcoded value rather than inheriting one.
#
# FAIL-CLOSED, as everywhere else here: every growth entry must be adjudicated
# to exactly one of allowed/refused, and the totals are asserted against the
# number of growth lines before anything exits 0. A growth line this parser
# failed to understand is a FAILURE, never an unexamined pass.

echo "check-baseline-no-growth: the baseline GREW against ${base}"
echo "  suppressed findings: ${old_total} -> ${new_total}"
echo
printf '%s\n' "$growth" | sed 's/^/  /'
echo

growth_entries=$(printf '%s\n' "$growth" | grep -c . || true)
if [ "${growth_entries:-0}" -eq 0 ]; then
    echo "FATAL: hv_baseline_growth reported growth but emitted no entries —" >&2
    echo "  refusing to report clean on a verdict this guard cannot read" >&2
    exit 1
fi
# Counted with `wc -l`, NOT with the non-blank count above, and the difference
# is the point. The loop below skips a blank growth line; counting only
# non-blank lines here would make that skip agree with itself and the
# reconciliation at the end would be unfalsifiable. Every line the library
# emitted has to come back with a verdict.
growth_lines=$(printf '%s\n' "$growth" | wc -l)

mapfile -t NEW_LINES < "${PROJECT_ROOT}/${BASELINE_REL}"
if [ "${#NEW_LINES[@]}" -eq 0 ]; then
    echo "FATAL: ${BASELINE_REL} read as zero lines — refusing to report clean" >&2
    exit 1
fi

# Lines this change ADDS to the baseline. Diffed against the working tree, the
# same side hv_baseline_growth just compared, so the two can never disagree
# about what "this change" is.
# Written to a file first, NOT consumed straight from `<(git diff ...)`. A
# process substitution's exit status is invisible to `set -e` and `pipefail`, so
# a failed `git diff` there would leave ADDED_LINES empty and every entry would
# be refused with the wrong reason ("already in the baseline") instead of the
# right one. Fail-closed either way, but a guard whose message misdescribes its
# own failure is one nobody can act on.
ADDED_DIFF=$(mktemp)
trap 'rm -f "$OLD_BASELINE" "$ADDED_DIFF"' EXIT
if ! git diff "$base" -- "$BASELINE_REL" > "$ADDED_DIFF"; then
    echo "FATAL: cannot diff ${BASELINE_REL} against ${base} — refusing to report clean" >&2
    exit 1
fi

declare -A ADDED_LINES=()
while IFS= read -r _added; do
    # A bare `+` is an added BLANK line. Its key would be the empty string,
    # which is a bad array subscript under `set -u` and, worse, would make an
    # entry with no marker at all look like it had one.
    [ -n "${_added:1}" ] || continue
    ADDED_LINES["${_added:1}"]=1
done < <(grep '^+' "$ADDED_DIFF" | grep -v '^+++')

# The nearest non-blank line above the entry whose key is $1, or nothing.
marker_for_key() {
    local key="$1" i j
    for (( i = 0; i < ${#NEW_LINES[@]}; i++ )); do
        [[ ${NEW_LINES[$i]} =~ ^[0-9] ]] || continue
        [ "${NEW_LINES[$i]#*|}" = "$key" ] || continue
        for (( j = i - 1; j >= 0; j-- )); do
            [[ ${NEW_LINES[$j]} =~ ^[[:space:]]*$ ]] && continue
            printf '%s\n' "${NEW_LINES[$j]}"
            return 0
        done
        return 1
    done
    return 1
}

allowed=0
refused=0
while IFS= read -r gline; do
    [ -n "$gline" ] || continue
    # `NEW-KEY  (+2)  ssot|path|value` / `COUNT-UP (1->2)  ssot|path|value`.
    # The parenthetical never contains `)`, so the first one ends it.
    key="${gline#*)}"
    key="${key#"${key%%[![:space:]]*}"}"

    if [ -z "$key" ] || [ "$key" = "$gline" ]; then
        echo "  REFUSED  ${gline}"
        echo "           this guard could not parse the entry out of that growth line."
        refused=$((refused + 1))
        continue
    fi

    # THE KEY MUST BE UNAMBIGUOUS BEFORE ITS FILE FIELD MEANS ANYTHING.
    #
    # A key is `<class>|<file>|<value>` and both `file` and `value` are raw --
    # a literal `|` is a legal byte in a Linux filename and nothing in this
    # toolchain rejects one. With three separators the split below is guesswork,
    # and the guess is exploitable: for
    #
    #     ssot|autobot-backend/decoy.py|evil_new.py|<secret>
    #
    # the naive split yields `autobot-backend/decoy.py` -- an untouched,
    # pre-existing DECOY -- while the finding really belongs to the brand-new
    # file `autobot-backend/decoy.py|evil_new.py` that this change just wrote.
    # Every test below then validated the decoy and the guard reported ALLOWED,
    # exit 0, over exactly the bypass this file exists to close. Reproduced
    # end-to-end during review before this check existed.
    #
    # So an ambiguous key is REFUSED rather than guessed at. All 1408 entries in
    # the live baseline carry exactly two separators, so this costs nothing
    # today; a value that genuinely contains `|` needs escaping in the record
    # format itself, which is a change to the detector, not a guess here.
    _hv_seps="${key//[^|]/}"
    if [ "${#_hv_seps}" -ne 2 ]; then
        echo "  REFUSED  ${key}"
        echo "           this key has ${#_hv_seps} '|' separator(s), not 2, so which part"
        echo "           of it is the FILE cannot be determined. Guessing here means"
        echo "           validating a different file than the finding belongs to."
        refused=$((refused + 1))
        continue
    fi

    entry_file="${key#*|}"
    entry_file="${entry_file%%|*}"
    if [ -z "$entry_file" ]; then
        echo "  REFUSED  ${key}"
        echo "           its file field is empty."
        refused=$((refused + 1))
        continue
    fi

    if [ ! -f "$entry_file" ]; then
        echo "  REFUSED  ${key}"
        echo "           ${entry_file} does not exist in this tree, so the entry suppresses"
        echo "           nothing and is stranded the moment it lands."
        refused=$((refused + 1))
        continue
    fi

    # A SYMLINK IS NOT THE CONTENT THE FINDING IS ABOUT.
    #
    # A symlink's blob is the target PATH STRING, so `git diff --quiet` below
    # reports it unchanged however much the file it points at was rewritten.
    # Found in review: base has `alias.py -> real.py`, the change rewrites
    # `real.py` to add a secret and baselines `alias.py`, and the byte-identical
    # test passes on the link object while the value is brand new.
    #
    # Refusing costs nothing, because a finding can never legitimately be
    # attributed to a symlink path in the first place: hv_scan_tree walks the
    # tree with `grep -r`, which does not follow symlinks during traversal, so
    # the detector reports the finding under the real path. An entry naming a
    # symlink is therefore always either a mistake or a decoy.
    if [ -L "$entry_file" ]; then
        echo "  REFUSED  ${key}"
        echo "           ${entry_file} is a symlink. Its content is the target PATH, so"
        echo "           'byte-identical to the base ref' says nothing about the file the"
        echo "           value actually lives in. The detector never attributes a finding"
        echo "           to a symlink path either — baseline the real path."
        refused=$((refused + 1))
        continue
    fi

    if ! git rev-parse --verify --quiet "${base}:${entry_file}" >/dev/null; then
        echo "  REFUSED  ${key}"
        echo "           ${entry_file} does not exist at ${base}: this change created it,"
        echo "           so the value in it is new, not pre-existing."
        refused=$((refused + 1))
        continue
    fi

    if ! git diff --quiet "$base" -- "$entry_file"; then
        echo "  REFUSED  ${key}"
        echo "           ${entry_file} is modified by this change. An addition whose file"
        echo "           this change touches is the bypass the guard exists to close:"
        echo "           hardcode a value, append its key in the same commit. There is"
        echo "           no route for it. Fix the value."
        refused=$((refused + 1))
        continue
    fi

    marker=$(marker_for_key "$key") || marker=""
    if [ -z "$marker" ] || ! [[ $marker =~ ^#[[:space:]]*reviewed:[[:space:]]*#[0-9]+[[:space:]]+[^[:space:]] ]]; then
        echo "  REFUSED  ${key}"
        echo "           ${entry_file} is unchanged by this change, so a detection-rule"
        echo "           change could legitimately have surfaced this. That still needs a"
        echo "           written justification on the line above the entry:"
        echo
        echo "               # reviewed: #<issue> why this cannot be fixed at the source"
        echo "               <count>|${key}"
        echo
        refused=$((refused + 1))
        continue
    fi

    if [ -z "${ADDED_LINES[$marker]+set}" ]; then
        echo "  REFUSED  ${key}"
        echo "           its justification was already in the baseline before this change:"
        echo "             ${marker}"
        echo "           A justification already in the file covers the entry it was"
        echo "           written for, not a later append that happens to sit under it."
        refused=$((refused + 1))
        continue
    fi

    echo "  ALLOWED  ${key}"
    echo "           ${entry_file} is byte-identical to ${base}, and this change adds:"
    echo "             ${marker}"
    echo "::warning file=${BASELINE_REL}::reviewed baseline addition: ${key} — ${marker}"
    allowed=$((allowed + 1))
done < <(printf '%s\n' "$growth")

# Every growth line must have reached exactly one verdict. Without this, a
# growth line the parser silently dropped would leave both counters at zero and
# the run would exit 0 over real growth — an absent result reading as a clean
# result, which is the class this whole family of guards exists to stop.
#
# Reachable, and covered by a test that stubs the library into emitting a line
# the loop skips. An assertion no input can trigger is one nobody can prove
# still works.
if [ $((allowed + refused)) -ne "$growth_lines" ]; then
    echo >&2
    echo "FATAL: ${growth_lines} growth entr(ies) but $((allowed + refused)) adjudicated —" >&2
    echo "  refusing to report clean on a comparison this guard did not finish" >&2
    exit 1
fi

echo
if [ "$refused" -gt 0 ]; then
    echo "The baseline only shrinks by default. ${refused} of ${growth_entries} addition(s)"
    echo "above have no route and were refused; fix the violation at the source."
    echo
    echo "The one route that exists, and what it costs: an entry may be ADDED only"
    echo "when its file is byte-identical to the base ref — so this change did not"
    echo "write the value, a detection-rule change surfaced code that was already"
    echo "there — AND this change adds a justification line directly above it:"
    echo
    echo "    # reviewed: #<issue> why this cannot be fixed at the source"
    echo "    <count>|<class>|<file>|<value>"
    echo
    echo "Nothing opens the route for a file this change touches. That case is the"
    echo "bypass itself and has no override, by design."
    exit 1
fi

echo "check-baseline-no-growth: ${allowed} reviewed addition(s), every one of them in a"
echo "  file this change leaves byte-identical to ${base} and justified by a line this"
echo "  change adds. The unreviewed direction stays closed."
exit 0
