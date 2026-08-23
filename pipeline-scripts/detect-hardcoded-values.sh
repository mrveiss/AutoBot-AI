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
# Usage: detect-hardcoded-values.sh [--json|--report|--audit-baseline|--help]

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

for arg in "$@"; do
    case "$arg" in
        --json)            OUTPUT_FORMAT="json" ;;
        --report)          REPORT_MODE=true ;;
        --audit-baseline)  AUDIT_BASELINE=true ;;
        --help)
            echo "Usage: $0 [--json|--report|--audit-baseline|--help]"
            echo "  --json            Output results as JSON"
            echo "  --report          Show the detailed violation report"
            echo "  --audit-baseline  Fail on baseline entries that match nothing"
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
        echo "Baseline entries in ${BASELINE#"$REPO_ROOT"/} that match nothing any more:"
        printf '%s\n' "$STALE" | sed 's/^/  STALE  /'
        echo
        echo "A fixed violation must take its baseline line with it. An entry naming a"
        echo "path that has moved exempts nothing, silently, and re-permits the value"
        echo "the moment the path comes back."
        exit 1
    fi
    echo "hardcoded-values: every baseline entry still matches something"
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
