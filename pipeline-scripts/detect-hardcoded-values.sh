#!/usr/bin/env bash
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
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

# Account-name violations (#14316). ACCOUNT_PATH_PATTERN is the original
# rule: a hardcoded /home/<user> path. ACCOUNT_POSITION_PATTERN is the
# broadened half -- the SAME two account names (kali: a leftover dev-image
# user; autobot: the correct production account, still a violation when
# hardcoded rather than read from AUTOBOT_BASE_DIR/a variable) appearing bare,
# in the positions that actually carry an account identity in shell/systemd/
# sudoers text: a systemd User=/Group= directive, a chown owner:group, or a
# sudoers rule. A path match alone misses exactly this shape -- it is how
# `User=kali`, `chown kali:kali` and bare `kali ALL=(ALL) NOPASSWD:` sudoers
# lines survived in autobot-infrastructure/shared/scripts/utilities/
# fix-vnc-desktop.sh, fix-vnc-wsl.sh and setup_passwordless_sudo.sh.
ACCOUNT_PATH_PATTERN='/home/kali|/home/autobot'
ACCOUNT_POSITION_PATTERN='(User=|Group=)(kali|autobot)\b|chown[^=]*\b(kali|autobot):(kali|autobot)\b|^[[:space:]]*(kali|autobot)[[:space:]]+ALL='
ACCOUNT_PATTERN="(${ACCOUNT_PATH_PATTERN}|${ACCOUNT_POSITION_PATTERN})"

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
# autobot-infrastructure (#14316): the deployment/ops scripts that actually
# touch hosts, paths and accounts directly -- and had no type system or
# linter enforcing indirection on them -- were never in this list, so a
# shell-script fix below would still have found nothing there.
SCAN_DIRS=(
    "autobot-backend"
    "autobot-frontend/src"
    "autobot_shared"
    "autobot-slm-backend"
    "autobot-slm-frontend/src"
    "autobot-infrastructure"
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
    # SSOT definition files (they ARE the config source)
    "registry_defaults.py"
    "ssot_mappings.py"
    # autobot-infrastructure/shared/scripts/detect-hardcoded-values.sh (#14316):
    # a second, dormant hardcoded-value scanner whose own body is a literal
    # table of every SSOT IP/port -- an SSOT definition file, exactly like
    # ssot_mappings.py above, not a violation of the rule it implements.
    "detect-hardcoded-values.sh"
    # Test files (assertions verify known config values) — cover both pytest
    # conventions (test_*.py prefix AND *_test.py suffix) and both TS conventions
    # (*.spec.ts AND *.test.ts). NOTE: this deliberately stops the design-value
    # scanner from flagging test files; hardcoded prod values in tests (e.g. an
    # IP address, GH#11589) are a separate concern for a dedicated check, not a
    # side-effect of this design-token scanner.
    "*_test.py"
    "test_*.py"
    "*.spec.ts"
    "*_test.ts"
    "*.test.ts"
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
    # #14316: *.sh/*.yml/*.yaml added -- Ansible playbooks/roles and shell
    # utilities are exactly where a raw fleet IP is most likely to be typed
    # directly rather than read from config, and neither extension was
    # scanned before.
    while IFS= read -r line; do
        if [ -n "$line" ]; then
            SSOT_VIOLATIONS=$((SSOT_VIOLATIONS + 1))
            TOTAL_VIOLATIONS=$((TOTAL_VIOLATIONS + 1))
            VIOLATION_DETAILS="${VIOLATION_DETAILS}SSOT|${line}\n"
        fi
    done < <(grep -rn --include="*.py" --include="*.ts" --include="*.vue" \
        --include="*.sh" --include="*.yml" --include="*.yaml" \
        $EXCLUDE_ARGS -E "$IP_PATTERN" "$full_path" 2>/dev/null \
        | grep -v '#.*noqa' | grep -v '//.*noqa' || true)

    # Scan for hardcoded account paths/identities (other violations) — see
    # ACCOUNT_PATTERN above for the path vs. bare-position halves (#14316).
    while IFS= read -r line; do
        if [ -n "$line" ]; then
            OTHER_VIOLATIONS=$((OTHER_VIOLATIONS + 1))
            TOTAL_VIOLATIONS=$((TOTAL_VIOLATIONS + 1))
            VIOLATION_DETAILS="${VIOLATION_DETAILS}OTHER|${line}\n"
        fi
    done < <(grep -rn --include="*.py" --include="*.ts" --include="*.vue" \
        --include="*.sh" --include="*.yml" --include="*.yaml" \
        $EXCLUDE_ARGS -E "$ACCOUNT_PATTERN" "$full_path" 2>/dev/null \
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
