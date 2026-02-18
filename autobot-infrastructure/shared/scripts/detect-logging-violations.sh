#!/bin/bash
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
#
# Detect console.*/print() statements that should use structured logging
# Usage: ./scripts/detect-logging-violations.sh [--staged-only]
#
# Part of Issue #309 - Pre-commit hook for logging enforcement

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"

# Colors for output
RED='\033[0;31m'
YELLOW='\033[1;33m'
GREEN='\033[0;32m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Track violations
VIOLATIONS_FOUND=0
STAGED_ONLY=false

# Parse arguments
if [[ "${1:-}" == "--staged-only" ]]; then
    STAGED_ONLY=true
fi

echo -e "${CYAN}🔍 Scanning for logging violations...${NC}"
echo ""

# Function to report violation
report_violation() {
    local file="$1"
    local line_num="$2"
    local pattern="$3"
    local suggestion="$4"

    echo -e "${RED}❌ LOGGING VIOLATION${NC}"
    echo "   File: $file:$line_num"
    echo "   Pattern: ${pattern:0:100}..."  # Truncate long lines
    echo "   ${YELLOW}Suggestion: $suggestion${NC}"
    echo ""
    VIOLATIONS_FOUND=$((VIOLATIONS_FOUND + 1))
}

# Get files to check
get_files_to_check() {
    local pattern="$1"
    local dirs="$2"

    if [[ "$STAGED_ONLY" == "true" ]]; then
        git diff --cached --name-only --diff-filter=ACM 2>/dev/null | grep -E "$pattern" || true
    else
        find $dirs -type f \( -name "*.py" -o -name "*.ts" -o -name "*.vue" \) 2>/dev/null || true
    fi
}

# ═══════════════════════════════════════════════════════════════════════════
# PYTHON CHECKS - print() statements
# ═══════════════════════════════════════════════════════════════════════════

echo -e "${CYAN}📝 Checking Python files for print() statements...${NC}"

# Get Python files to check
if [[ "$STAGED_ONLY" == "true" ]]; then
    PY_FILES=$(git diff --cached --name-only --diff-filter=ACM 2>/dev/null | grep '\.py$' || true)
else
    PY_FILES=$(find "$PROJECT_ROOT/src" "$PROJECT_ROOT/backend" -type f -name "*.py" 2>/dev/null || true)
fi

for file in $PY_FILES; do
    [[ -z "$file" ]] && continue
    [[ ! -f "$file" ]] && continue

    # Skip excluded files/directories
    case "$file" in
        *"__pycache__"*|*"archive/"*|*"tests/"*|*"test_"*|*"_test.py")
            continue ;;
        *"service_registry_cli.py")  # CLI tools are allowed print()
            continue ;;
        *"script_utils.py")  # Script formatting utilities with intentional print()
            continue ;;
        *"monitoring/"*)  # Monitoring CLI tools use print() for terminal reports
            continue ;;
        *"cleanup_redis_metrics.py")  # Phase 5 CLI tool for Redis cleanup
            continue ;;
        *"test_phase5_cleanup.py")  # Phase 5 test script
            continue ;;
        *"test_grafana_integration.py")  # Phase 4 test script
            continue ;;
        *"test_alertmanager.py")  # Phase 3 test script
            continue ;;
        *"scripts/hooks/"*)  # Pre-commit hook scripts need terminal output
            continue ;;
        *"code_analysis/"*)  # Code analysis tools use print() for CLI output
            continue ;;
    esac

    # Check if file has if __name__ == "__main__"
    has_main_block=$(grep -n 'if __name__ == "__main__"' "$file" 2>/dev/null | head -1 | cut -d: -f1 || true)

    # Check if file has a main() function (commonly used with __main__)
    main_func_line=$(grep -n '^async def main\|^def main' "$file" 2>/dev/null | head -1 | cut -d: -f1 || true)

    # If has __main__ that calls main(), prints in main() are acceptable
    if [[ -n "$has_main_block" ]] && [[ -n "$main_func_line" ]]; then
        # Check if __main__ block calls main()
        calls_main=$(sed -n "${has_main_block},\$p" "$file" | grep -q 'main()' && echo "yes" || true)
    else
        calls_main=""
    fi

    # Find print statements
    while IFS=: read -r line_num line_content; do
        [[ -z "$line_num" ]] && continue

        # Skip if in docstring or doctest (line starts with """, #, *, >>>, ...)
        if echo "$line_content" | grep -qE '^[[:space:]]*("""|\x27\x27\x27|#|\*|>>>|\.\.\.)'; then
            continue
        fi

        # Skip if print is after __main__ block
        if [[ -n "$has_main_block" ]] && [[ "$line_num" -ge "$has_main_block" ]]; then
            continue
        fi

        # Skip if print is inside main() function and __main__ calls main()
        if [[ -n "$main_func_line" ]] && [[ -n "$calls_main" ]] && [[ "$line_num" -ge "$main_func_line" ]]; then
            continue
        fi

        # Skip if line is a comment
        if echo "$line_content" | grep -qE '^[[:space:]]*#'; then
            continue
        fi

        # Skip if print is in a string (e.g., template code, examples)
        if echo "$line_content" | grep -qE '(["'"'"'].*print\(|snippet.*=|template.*=|example.*=|code.*=)'; then
            continue
        fi

        report_violation "$file" "$line_num" "$line_content" \
            "Use logger.info/debug/warning/error() instead of print()"

    # Match actual print() function calls - not 'fingerprint(', 'blueprint(', etc.
    # Pattern: word boundary before print, or start of line/whitespace
    done < <(grep -n -E '(^|[^a-zA-Z_])print\(' "$file" 2>/dev/null || true)
done

# ═══════════════════════════════════════════════════════════════════════════
# FRONTEND CHECKS - console.* statements
# ═══════════════════════════════════════════════════════════════════════════

echo -e "${CYAN}📝 Checking Frontend files for console.* statements...${NC}"

# Get frontend files to check
if [[ "$STAGED_ONLY" == "true" ]]; then
    FE_FILES=$(git diff --cached --name-only --diff-filter=ACM 2>/dev/null | grep -E '\.(ts|vue)$' || true)
else
    FE_FILES=$(find "$PROJECT_ROOT/autobot-slm-frontend/src" -type f \( -name "*.ts" -o -name "*.vue" \) 2>/dev/null || true)
fi

for file in $FE_FILES; do
    [[ -z "$file" ]] && continue
    [[ ! -f "$file" ]] && continue

    # Skip excluded files/directories
    case "$file" in
        *"node_modules"*|*"dist/"*|*".d.ts")
            continue ;;
        *"debugUtils.ts")  # Logger implementation - allowed
            continue ;;
        *"RumAgent.ts"|*"RumConsoleHelper.ts")  # RUM tools - intentional console output
            continue ;;
        *"chunkTestUtility.ts")  # Test utility - intentional console output
            continue ;;
        *"/examples/"*)  # Example/demo components - allowed
            continue ;;
    esac

    # Find console.* statements (not in JSDoc comments)
    while IFS=: read -r line_num line_content; do
        [[ -z "$line_num" ]] && continue

        # Skip if in JSDoc comment (line starts with * or spaces + *)
        if echo "$line_content" | grep -qE '^[[:space:]]*\*'; then
            continue
        fi

        # Skip if in code block within documentation (after ```)
        if echo "$line_content" | grep -qE '^\s*\*.*console\.'; then
            continue
        fi

        # Skip if it's in a string (example data)
        if echo "$line_content" | grep -qE "(snippet.*=|template.*=|example.*=|'.*console\.)"; then
            continue
        fi

        report_violation "$file" "$line_num" "$line_content" \
            "Use createLogger() from '@/utils/debugUtils' instead of console.*"

    done < <(grep -n 'console\.' "$file" 2>/dev/null | grep -vE '^\s*\*|^\s*//' || true)
done

# ═══════════════════════════════════════════════════════════════════════════
# SUMMARY
# ═══════════════════════════════════════════════════════════════════════════

echo ""
echo "═══════════════════════════════════════════"
if [[ $VIOLATIONS_FOUND -eq 0 ]]; then
    echo -e "${GREEN}✅ No logging violations found!${NC}"
    exit 0
else
    echo -e "${RED}❌ Found $VIOLATIONS_FOUND logging violation(s)${NC}"
    echo ""
    echo "💡 Quick fixes:"
    echo ""
    echo "   Python:"
    echo "     import logging"
    echo "     logger = logging.getLogger(__name__)"
    echo "     logger.info('message')  # instead of print()"
    echo ""
    echo "   TypeScript/Vue:"
    echo "     import { createLogger } from '@/utils/debugUtils'"
    echo "     const logger = createLogger('ComponentName')"
    echo "     logger.info('message')  # instead of console.log()"
    echo ""
    echo "📖 See docs/developer/LOGGING_STANDARDS.md for guidelines"
    echo ""
    echo "To bypass (NOT RECOMMENDED): git commit --no-verify"
    exit 1
fi
