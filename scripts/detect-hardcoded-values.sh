#!/bin/bash
# Automated Hardcoded Value Detection
# Prevents hardcoding violations by detecting common patterns
# Usage: ./scripts/detect-hardcoded-values.sh [--fix]

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# Colors for output
RED='\033[0;31m'
YELLOW='\033[1;33m'
GREEN='\033[0;32m'
NC='\033[0m' # No Color

# Track violations
VIOLATIONS_FOUND=0
FIX_MODE=false

if [[ "${1:-}" == "--fix" ]]; then
    FIX_MODE=true
    echo "🔧 Fix mode enabled - will attempt to auto-fix violations"
fi

echo "🔍 Scanning for hardcoded values..."
echo ""

# Function to report violation
report_violation() {
    local file="$1"
    local line_num="$2"
    local pattern="$3"
    local suggestion="$4"

    echo -e "${RED}❌ HARDCODING VIOLATION${NC}"
    echo "   File: $file:$line_num"
    echo "   Pattern: $pattern"
    echo "   ${YELLOW}Suggestion: $suggestion${NC}"
    echo ""
    ((VIOLATIONS_FOUND++))
}

# 1. Check for hardcoded IP addresses (excluding comments, .env files, constants files)
echo "📍 Checking for hardcoded IP addresses..."
while IFS=: read -r file line_num line_content; do
    # Skip .env files, network_constants.py, config files, and comments
    if [[ "$file" == *.env* ]] || \
       [[ "$file" == *"network_constants.py" ]] || \
       [[ "$file" == *"config.yaml" ]] || \
       [[ "$file" == *".example" ]] || \
       [[ "$line_content" =~ ^[[:space:]]*# ]]; then
        continue
    fi

    report_violation "$file" "$line_num" "Hardcoded IP: $line_content" \
        "Use NetworkConstants or environment variables"
done < <(grep -rn --include="*.py" --include="*.ts" --include="*.vue" \
    -E '\b([0-9]{1,3}\.){3}[0-9]{1,3}\b' "$PROJECT_ROOT/src" "$PROJECT_ROOT/backend" "$PROJECT_ROOT/autobot-vue/src" 2>/dev/null || true)

# 2. Check for hardcoded model names
echo "🤖 Checking for hardcoded LLM model names..."
while IFS=: read -r file line_num line_content; do
    # Skip .env files, comments, and config files
    if [[ "$file" == *.env* ]] || \
       [[ "$file" == *"config.yaml" ]] || \
       [[ "$file" == *".example" ]] || \
       [[ "$line_content" =~ ^[[:space:]]*# ]]; then
        continue
    fi

    # Skip if line contains os.getenv, config.get, or similar config access
    if echo "$line_content" | grep -qE '(os\.getenv|config\.get|getenv|CONFIG\[)'; then
        continue
    fi

    report_violation "$file" "$line_num" "Hardcoded model name: $line_content" \
        "Use config.get_default_llm_model() or os.getenv('AUTOBOT_DEFAULT_LLM_MODEL')"
done < <(grep -rn --include="*.py" \
    -E '(llama3|mistral|dolphin|openchat|gemma|phi|deepseek|qwen).*:[0-9]+(b|B)' \
    "$PROJECT_ROOT/src" "$PROJECT_ROOT/backend" 2>/dev/null | \
    grep -v "archive/" | grep -v "__pycache__" || true)

# 3. Check for hardcoded ports (excluding constants and config)
echo "🔌 Checking for hardcoded ports..."
while IFS=: read -r file line_num line_content; do
    # Skip constants files, .env, config, and comments
    if [[ "$file" == *"constants"* ]] || \
       [[ "$file" == *.env* ]] || \
       [[ "$file" == *"config"* ]] || \
       [[ "$line_content" =~ ^[[:space:]]*# ]]; then
        continue
    fi

    # Skip if line contains getenv or config access
    if echo "$line_content" | grep -qE '(getenv|config\.|CONFIG\[|NetworkConstants)'; then
        continue
    fi

    report_violation "$file" "$line_num" "Hardcoded port: $line_content" \
        "Use NetworkConstants.{SERVICE}_PORT or environment variables"
done < <(grep -rn --include="*.py" --include="*.ts" --include="*.vue" \
    -E ':[0-9]{4,5}[^0-9]' "$PROJECT_ROOT/src" "$PROJECT_ROOT/backend" "$PROJECT_ROOT/autobot-vue/src" 2>/dev/null | \
    grep -v "archive/" | grep -v "__pycache__" | head -20 || true)

# 4. Check for hardcoded URLs (excluding comments and config)
echo "🌐 Checking for hardcoded URLs..."
while IFS=: read -r file line_num line_content; do
    # Skip .env, config, and comments
    if [[ "$file" == *.env* ]] || \
       [[ "$file" == *"config"* ]] || \
       [[ "$line_content" =~ ^[[:space:]]*# ]]; then
        continue
    fi

    # Skip if line contains getenv or config access
    if echo "$line_content" | grep -qE '(getenv|config\.|CONFIG\[)'; then
        continue
    fi

    report_violation "$file" "$line_num" "Hardcoded URL: $line_content" \
        "Use environment variables or config"
done < <(grep -rn --include="*.py" --include="*.ts" --include="*.vue" \
    -E 'https?://[a-zA-Z0-9]' "$PROJECT_ROOT/src" "$PROJECT_ROOT/backend" "$PROJECT_ROOT/autobot-vue/src" 2>/dev/null | \
    grep -v "archive/" | grep -v "__pycache__" | head -20 || true)

# Summary
echo ""
echo "═══════════════════════════════════════════"
if [[ $VIOLATIONS_FOUND -eq 0 ]]; then
    echo -e "${GREEN}✅ No hardcoding violations found!${NC}"
    exit 0
else
    echo -e "${RED}❌ Found $VIOLATIONS_FOUND hardcoding violation(s)${NC}"
    echo ""
    echo "💡 Quick fixes:"
    echo "   1. Move values to .env file"
    echo "   2. Use NetworkConstants for IPs/ports"
    echo "   3. Use config.get_default_llm_model() for models"
    echo "   4. Document why if hardcoding is truly necessary"
    echo ""
    echo "📖 See CLAUDE.md for detailed guidelines"
    exit 1
fi
