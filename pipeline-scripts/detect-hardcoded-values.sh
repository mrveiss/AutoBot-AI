#!/usr/bin/env bash
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
#
# Detect hardcoded values that should use SSOT config — TREE SCAN entry point.
# Used by: .github/workflows/ssot-coverage.yml
# Reference: docs/developer/HARDCODING_PREVENTION.md
#
# #14371: this is now a thin entry point. Every rule lives in
# scripts/lib/hardcoded-value-rules.sh, which carries the UNION of what the
# three former detectors implemented — this one, the dormant
# autobot-infrastructure/shared/scripts/detect-hardcoded-values.sh, and the
# pre-commit hook. The hook is the other entry point onto the same rules.
#
# This one differs from the hook in exactly two ways, and both are entry-point
# policy rather than rule content:
#   * it scans a tree rather than the staged file list;
#   * it always exits 0. ssot-coverage.yml decides pass/fail from the reported
#     counts, and has done since #2874.
#
# Usage: detect-hardcoded-values.sh [--json|--report|--audit-baseline|--prune-baseline|--help]

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=scripts/lib/hardcoded-value-rules.sh
source "${REPO_ROOT}/scripts/lib/hardcoded-value-rules.sh" || {
    echo "FATAL: cannot load scripts/lib/hardcoded-value-rules.sh — refusing to report clean" >&2
    exit 1
}

BASELINE="${REPO_ROOT}/pipeline-scripts/hardcoded_values_baseline.txt"

OUTPUT_FORMAT="text"
REPORT_MODE=false
AUDIT_BASELINE=false
PRUNE_BASELINE=false

for arg in "$@"; do
    case "$arg" in
        --json)            OUTPUT_FORMAT="json" ;;
        --report)          REPORT_MODE=true ;;
        --audit-baseline)  AUDIT_BASELINE=true ;;
        --prune-baseline)  PRUNE_BASELINE=true ;;
        --help)
            echo "Usage: $0 [--json|--report|--audit-baseline|--prune-baseline|--help]"
            echo "  --json            Output results as JSON"
            echo "  --report          Show the detailed violation report"
            echo "  --audit-baseline  Fail on baseline entries that match nothing"
            echo "  --prune-baseline  Rewrite the baseline to what is actually found (REMOVES only)"
            exit 0
            ;;
    esac
done

# Directories to scan. autobot-infrastructure (#14316) is in the list because
# the deployment/ops scripts that actually touch hosts, paths and accounts have
# no type system or linter enforcing indirection on them.
SCAN_DIRS=(
    "autobot-backend"
    "autobot-frontend/src"
    "autobot_shared"
    "autobot-slm-backend"
    "autobot-slm-frontend/src"
    "autobot-infrastructure"
)

hv_load_baseline "$BASELINE" || exit 1

RAW=$(mktemp); NEWFILE=$(mktemp)
trap 'rm -f "$RAW" "$NEWFILE"' EXIT
(
    cd "$REPO_ROOT" || exit 1
    for dir in "${SCAN_DIRS[@]}"; do hv_scan_tree "$dir"; done
) > "$RAW"

# Redirection, not a pipe: through a pipe hv_partition runs in a subshell and
# its counters die with it — see the note on the function.
hv_partition < "$RAW" > "$NEWFILE"
SUPPRESSED="$HV_SUPPRESSED"
NEW=$(cat "$NEWFILE")

count_of() { grep -c "$1" "$NEWFILE" || true; }
TOTAL_VIOLATIONS=$(count_of '^VIOLATION|')
SSOT_VIOLATIONS=$(count_of '^VIOLATION|ssot|')
OTHER_VIOLATIONS=$(count_of '^VIOLATION|other|')
WARNINGS=$(count_of '^WARNING|')

STATUS="pass"
[ "$SSOT_VIOLATIONS" -gt 0 ] && STATUS="fail"

if [ "$AUDIT_BASELINE" = true ]; then
    STALE=$(hv_stale_baseline_entries)
    if [ -n "$STALE" ]; then
        STALE_COUNT=$(printf '%s\n' "$STALE" | grep -c . || true)
        echo "${STALE_COUNT} baseline entr(ies) in ${BASELINE#"$REPO_ROOT"/} no longer match anything:"
        echo
        printf '%s\n' "$STALE" | sed 's/^/  STALE  /'
        echo
        # #14912: this used to stop at "here is what is wrong". Most of the cost
        # of this check was never the rule, it was that the person who hit it --
        # usually the person who just FIXED a hardcoded value -- was not told how
        # to recover, and the file to edit has nothing to do with their change.
        echo "You almost certainly just fixed or moved these. Recover with one command:"
        echo
        echo "    ./pipeline-scripts/detect-hardcoded-values.sh --prune-baseline"
        echo
        echo "then commit the changed baseline. Prune only ever REMOVES entries — it"
        echo "cannot add a key or raise a count — so it cannot be used to silence a new"
        echo "finding. That direction is blocked independently by"
        echo "pipeline-scripts/check_baseline_no_growth.sh."
        echo
        echo "Why this blocks rather than warns: an entry naming a path that has moved"
        echo "exempts nothing today, but silently re-permits the value the moment that"
        echo "path comes back."
        exit 1
    fi
    echo "hardcoded-values: every baseline entry still matches something"
    exit 0
fi

if [ "$PRUNE_BASELINE" = true ]; then
    # Refuse to write the result of a scan that found nothing. An empty result
    # and a broken detector are indistinguishable here, and this path REWRITES
    # the record: a rules file that failed to load, or a scan directory that has
    # moved, would take all ${#HV_BASELINE[@]} entries with it and the no-growth
    # guard would not object, because shrinking is allowed by design.
    TOTAL_FOUND=$(grep -c . "$RAW" || true)
    if [ "$TOTAL_FOUND" -eq 0 ]; then
        echo "FATAL: the scan found 0 findings, so pruning would empty the baseline." >&2
        echo "  A tree carrying ${#HV_BASELINE[@]} baselined findings does not legitimately" >&2
        echo "  drop to zero. This looks like a broken scan, not a fixed repository —" >&2
        echo "  refusing to rewrite the baseline from it." >&2
        exit 1
    fi
    PRUNED=$(mktemp)
    trap 'rm -f "$RAW" "$NEWFILE" "$PRUNED"' EXIT
    hv_pruned_baseline | sort -t'|' -k3,3 -k2,2 -k4,4 > "$PRUNED"
    KEPT=$(grep -c . "$PRUNED" || true)
    BEFORE=${#HV_BASELINE[@]}
    # Header first, then the pruned body. The leading comment block carries the
    # rules governing this file -- including "this file only ever shrinks" --
    # and a rewrite that dropped it would delete the reason the file exists.
    # Taken as the run of leading `#` lines, so it stays correct if the header
    # is edited later.
    { awk '/^#/ { print; next } { exit }' "$BASELINE"; cat "$PRUNED"; } > "${BASELINE}.tmp"
    HEADER_LINES=$(awk '/^#/ { c++; next } { exit } END { print c + 0 }' "${BASELINE}.tmp")
    if [ "$HEADER_LINES" -eq 0 ]; then
        rm -f "${BASELINE}.tmp"
        echo "FATAL: refusing to write a baseline with no header — the rules governing" >&2
        echo "  this file live in it." >&2
        exit 1
    fi
    mv "${BASELINE}.tmp" "$BASELINE"
    echo "hardcoded-values: baseline pruned — ${BEFORE} key(s) -> ${KEPT} key(s), $((BEFORE - KEPT)) removed"
    echo "  Removal-only: no key was added and no count raised (hv_pruned_baseline"
    echo "  iterates existing keys and emits min(baseline, found))."
    echo "  Review the diff and commit it with the change that fixed the violations."
    exit 0
fi

if [ "$OUTPUT_FORMAT" = "json" ]; then
    cat <<ENDJSON
{
  "status": "$STATUS",
  "total_violations": $TOTAL_VIOLATIONS,
  "ssot_violations": $SSOT_VIOLATIONS,
  "other_violations": $OTHER_VIOLATIONS,
  "warnings": $WARNINGS,
  "baselined": $SUPPRESSED
}
ENDJSON
elif [ "$REPORT_MODE" = true ]; then
    echo "========================================"
    echo " SSOT Hardcoded Value Detection Report"
    echo "========================================"
    echo
    echo "Rules applied:    ${#HV_RULES[@]} (${HV_RULES[*]})"
    echo "Status:           $STATUS"
    echo "New violations:   $TOTAL_VIOLATIONS (ssot=$SSOT_VIOLATIONS, other=$OTHER_VIOLATIONS)"
    echo "New warnings:     $WARNINGS"
    # Printed on every run, pass or fail: a backlog nobody is reminded of is
    # indistinguishable from no backlog.
    echo "Known backlog:    $SUPPRESSED finding(s) baselined, tracked in $HV_BASELINE_ISSUE"
    echo
    if [ -n "$NEW" ]; then
        echo "--- New findings ---"
        printf '%s\n' "$NEW" | while IFS='|' read -r sev class file lineno value; do
            [ -n "$sev" ] && echo "[$sev/$class] $file:$lineno  $value"
        done
    fi
else
    echo "SSOT Coverage: $STATUS (new=$TOTAL_VIOLATIONS, ssot=$SSOT_VIOLATIONS, other=$OTHER_VIOLATIONS, baselined=$SUPPRESSED, rules=${#HV_RULES[@]})"
fi

exit 0
