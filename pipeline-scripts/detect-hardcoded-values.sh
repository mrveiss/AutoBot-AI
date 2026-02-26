#!/usr/bin/env bash
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
#
# Detect hardcoded values that should use SSOT config.
# Used by: .github/workflows/ssot-coverage.yml
# Reference: docs/developer/HARDCODING_PREVENTION.md

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# Patterns that indicate hardcoded IPs/ports that belong in SSOT config
IP_PATTERN='172\.16\.168\.[0-9]+'
PORT_PATTERN='(8443|6379|3000|5432|8080|9090|11434)'

OUTPUT_FORMAT="text"
REPORT_MODE=false

for arg in "$@"; do
    case "$arg" in
        --json)   OUTPUT_FORMAT="json" ;;
        --report) REPORT_MODE=true ;;
        --help)
            echo "Usage: $0 [--json|--report|--help]"
            echo "  --json    Output results as JSON"
            echo "  --report  Show detailed violation report"
            exit 0
            ;;
    esac
done

TOTAL_VIOLATIONS=0
SSOT_VIOLATIONS=0
OTHER_VIOLATIONS=0
VIOLATION_DETAILS=""

# Directories to scan
SCAN_DIRS=(
    "autobot-backend"
    "autobot-frontend/src"
    "autobot-shared"
    "autobot-slm-backend"
    "autobot-slm-frontend/src"
)

# Files/patterns to exclude from scanning
EXCLUDE_PATTERNS=(
    "*.pyc"
    "node_modules"
    "dist"
    "__pycache__"
    ".git"
    "pipeline-scripts"
    "ssot_config.py"
    "ssot-config.ts"
    "config.yaml"
    "*.md"
    "*.lock"
    "*.json"
    "network_constants.py"
    "AUTOBOT_REFERENCE.md"
)

build_exclude_args() {
    local args=""
    for pat in "${EXCLUDE_PATTERNS[@]}"; do
        args="$args --exclude=$pat --exclude-dir=$pat"
    done
    echo "$args"
}

EXCLUDE_ARGS=$(build_exclude_args)

scan_directory() {
    local dir="$1"
    local full_path="$REPO_ROOT/$dir"

    if [ ! -d "$full_path" ]; then
        return
    fi

    # Scan for hardcoded IPs (SSOT violations)
    while IFS= read -r line; do
        if [ -n "$line" ]; then
            SSOT_VIOLATIONS=$((SSOT_VIOLATIONS + 1))
            TOTAL_VIOLATIONS=$((TOTAL_VIOLATIONS + 1))
            VIOLATION_DETAILS="${VIOLATION_DETAILS}SSOT|${line}\n"
        fi
    done < <(grep -rn --include="*.py" --include="*.ts" --include="*.vue" \
        $EXCLUDE_ARGS -E "$IP_PATTERN" "$full_path" 2>/dev/null \
        | grep -v '#.*noqa' | grep -v '//.*noqa' || true)

    # Scan for hardcoded /home/kali or /opt/autobot paths (other violations)
    while IFS= read -r line; do
        if [ -n "$line" ]; then
            OTHER_VIOLATIONS=$((OTHER_VIOLATIONS + 1))
            TOTAL_VIOLATIONS=$((TOTAL_VIOLATIONS + 1))
            VIOLATION_DETAILS="${VIOLATION_DETAILS}OTHER|${line}\n"
        fi
    done < <(grep -rn --include="*.py" --include="*.ts" --include="*.vue" \
        $EXCLUDE_ARGS -E '(/home/kali|/home/autobot)' "$full_path" 2>/dev/null \
        | grep -v '#.*noqa' | grep -v '//.*noqa' \
        | grep -v 'AUTOBOT_BASE_DIR' || true)
}

for dir in "${SCAN_DIRS[@]}"; do
    scan_directory "$dir"
done

STATUS="pass"
if [ "$SSOT_VIOLATIONS" -gt 0 ]; then
    STATUS="fail"
fi

if [ "$OUTPUT_FORMAT" = "json" ]; then
    cat <<ENDJSON
{
  "status": "$STATUS",
  "total_violations": $TOTAL_VIOLATIONS,
  "ssot_violations": $SSOT_VIOLATIONS,
  "other_violations": $OTHER_VIOLATIONS
}
ENDJSON
elif [ "$REPORT_MODE" = true ]; then
    echo "========================================"
    echo " SSOT Hardcoded Value Detection Report"
    echo "========================================"
    echo ""
    echo "Status:           $STATUS"
    echo "Total violations: $TOTAL_VIOLATIONS"
    echo "SSOT violations:  $SSOT_VIOLATIONS (have config equivalent)"
    echo "Other violations: $OTHER_VIOLATIONS"
    echo ""
    if [ "$TOTAL_VIOLATIONS" -gt 0 ]; then
        echo "--- Violations ---"
        echo -e "$VIOLATION_DETAILS" | while IFS='|' read -r type detail; do
            if [ -n "$type" ]; then
                echo "[$type] $detail"
            fi
        done
    fi
else
    echo "SSOT Coverage: $STATUS (total=$TOTAL_VIOLATIONS, ssot=$SSOT_VIOLATIONS, other=$OTHER_VIOLATIONS)"
fi

exit 0
