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

echo "check-baseline-no-growth: the baseline GREW against ${base}"
echo "  suppressed findings: ${old_total} -> ${new_total}"
echo
printf '%s\n' "$growth" | sed 's/^/  /'
echo
echo "The baseline only ever shrinks. Each line above is a finding the detector"
echo "made and this change would suppress, which is indistinguishable from never"
echo "having found it. Fix the violation instead; if it genuinely cannot be fixed"
echo "now, that is a decision for a reviewer to take deliberately, not something"
echo "an appended line should buy silently."
exit 1
