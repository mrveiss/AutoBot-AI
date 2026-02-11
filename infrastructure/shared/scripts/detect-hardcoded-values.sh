#!/bin/bash
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
#
# Automated Hardcoded Value Detection with SSOT Validation
# =========================================================
#
# Prevents hardcoding violations by detecting common patterns and
# validating against SSOT (Single Source of Truth) configuration.
#
# Issue: #642 - Centralize Environment Variables with SSOT Config Validation
# Related: #599 - SSOT Configuration System Epic
#
# Usage:
#   ./scripts/detect-hardcoded-values.sh [--fix] [--report] [--json]
#
# Options:
#   --fix     Attempt to auto-fix violations (not yet implemented)
#   --report  Generate detailed coverage report
#   --json    Output in JSON format for CI/CD integration

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/lib/ssot-config.sh" 2>/dev/null || true
PROJECT_ROOT="${PROJECT_ROOT:-$(cd "$SCRIPT_DIR/../../.." && pwd)}"

# Colors for output
RED='\033[0;31m'
YELLOW='\033[1;33m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Track violations
VIOLATIONS_FOUND=0
SSOT_VIOLATIONS=0
FIX_MODE=false
REPORT_MODE=false
JSON_MODE=false

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --fix)
            FIX_MODE=true
            shift
            ;;
        --report)
            REPORT_MODE=true
            shift
            ;;
        --json)
            JSON_MODE=true
            shift
            ;;
        *)
            shift
            ;;
    esac
done

# =============================================================================
# SSOT Configuration Mappings
# =============================================================================
# These values have SSOT config equivalents and should NEVER be hardcoded

declare -A SSOT_VM_IPS=(
    ["172.16.168.20"]="config.vm.main (AUTOBOT_BACKEND_HOST)"
    ["172.16.168.21"]="config.vm.frontend (AUTOBOT_FRONTEND_HOST)"
    ["172.16.168.22"]="config.vm.npu (AUTOBOT_NPU_WORKER_HOST)"
    ["172.16.168.23"]="config.vm.redis (AUTOBOT_REDIS_HOST)"
    ["172.16.168.24"]="config.vm.aistack (AUTOBOT_AI_STACK_HOST)"
    ["172.16.168.25"]="config.vm.browser (AUTOBOT_BROWSER_SERVICE_HOST)"
)

declare -A SSOT_PORTS=(
    ["8001"]="config.port.backend (AUTOBOT_BACKEND_PORT)"
    ["5173"]="config.port.frontend (AUTOBOT_FRONTEND_PORT)"
    ["6379"]="config.port.redis (AUTOBOT_REDIS_PORT)"
    ["11434"]="config.port.ollama (AUTOBOT_OLLAMA_PORT)"
    ["6080"]="config.port.vnc (AUTOBOT_VNC_PORT)"
    ["8080"]="config.port.aistack (AUTOBOT_AI_STACK_PORT)"
    ["8081"]="config.port.npu (AUTOBOT_NPU_WORKER_PORT)"
    ["8082"]="config.port.npu (AUTOBOT_NPU_WORKER_PORT)"
)

declare -A SSOT_MODELS=(
    ["mistral:7b-instruct"]="config.llm.default_model (AUTOBOT_DEFAULT_LLM_MODEL)"
    ["nomic-embed-text:latest"]="config.llm.embedding_model (AUTOBOT_EMBEDDING_MODEL)"
)

# Files/patterns to exclude from scanning
EXCLUDE_PATTERNS=(
    "*.env*"
    "*network_constants.py"
    "*security_constants.py"
    "*/constants/network.ts"
    "*config.yaml"
    "*.example"
    "*__tests__*"
    "*test_*"
    "*_test.py"
    "*.test.ts"
    "*ssot_config.py"
    "*ssot-config.ts"
    "*ssot_mappings.py"
    "*detect-hardcoded-values.sh"
    "*CLAUDE.md"
    "*HARDCODING_PREVENTION.md"
    "*SSOT_CONFIG_GUIDE.md"
    "*.md"
    "*archive/*"
    "*__pycache__*"
)

# =============================================================================
# Helper Functions
# =============================================================================

# Check if file should be excluded
should_exclude_file() {
    local file="$1"
    for pattern in "${EXCLUDE_PATTERNS[@]}"; do
        if [[ "$file" == $pattern ]]; then
            return 0
        fi
    done
    return 1
}

# Report a standard violation
report_violation() {
    local file="$1"
    local line_num="$2"
    local pattern="$3"
    local suggestion="$4"

    if [[ "$JSON_MODE" == "false" ]]; then
        echo -e "${RED}HARDCODING VIOLATION${NC}"
        echo "   File: $file:$line_num"
        echo "   Pattern: $pattern"
        echo -e "   ${YELLOW}Suggestion: $suggestion${NC}"
        echo ""
    fi
    VIOLATIONS_FOUND=$((VIOLATIONS_FOUND + 1))
}

# Report an SSOT-specific violation (has known SSOT equivalent)
report_ssot_violation() {
    local file="$1"
    local line_num="$2"
    local value="$3"
    local ssot_config="$4"
    local line_content="$5"

    if [[ "$JSON_MODE" == "false" ]]; then
        echo -e "${RED}SSOT VIOLATION${NC} - Value has SSOT config equivalent!"
        echo "   File: $file:$line_num"
        echo "   Hardcoded value: $value"
        echo -e "   ${CYAN}SSOT Config: $ssot_config${NC}"
        echo "   Context: ${line_content:0:80}..."
        echo ""
        echo -e "   ${GREEN}Python fix:${NC} from src.config.ssot_config import config"
        echo -e "   ${GREEN}TypeScript fix:${NC} import config from '@/config/ssot-config'"
        echo ""
    fi
    SSOT_VIOLATIONS=$((SSOT_VIOLATIONS + 1))
    VIOLATIONS_FOUND=$((VIOLATIONS_FOUND + 1))
}

# =============================================================================
# SSOT-Aware Scanning Functions
# =============================================================================

# Scan for hardcoded VM IPs with SSOT suggestions
scan_ssot_ips() {
    if [[ "$JSON_MODE" == "false" ]]; then
        echo -e "${BLUE}Checking for hardcoded VM IPs (SSOT-aware)...${NC}"
    fi

    for ip in "${!SSOT_VM_IPS[@]}"; do
        ssot_config="${SSOT_VM_IPS[$ip]}"

        while IFS=: read -r file line_num line_content; do
            # Skip excluded files
            if should_exclude_file "$file"; then
                continue
            fi

            # Skip comments
            if [[ "$line_content" =~ ^[[:space:]]*# ]] || [[ "$line_content" =~ ^[[:space:]]*// ]]; then
                continue
            fi

            # Skip if using getenv/config access
            if echo "$line_content" | grep -qE '(os\.getenv|config\.|getenv|CONFIG\[|AUTOBOT_)'; then
                continue
            fi

            # Skip SVG/path data
            if echo "$line_content" | grep -qE '(<path|fill-rule|clip-rule|d="[Mm])'; then
                continue
            fi

            report_ssot_violation "$file" "$line_num" "$ip" "$ssot_config" "$line_content"

        done < <(grep -rn --include="*.py" --include="*.ts" --include="*.vue" \
            -F "$ip" "$PROJECT_ROOT/src" "$PROJECT_ROOT/backend" "$PROJECT_ROOT/autobot-slm-frontend/src" 2>/dev/null || true)
    done
}

# Scan for hardcoded ports with SSOT suggestions
scan_ssot_ports() {
    if [[ "$JSON_MODE" == "false" ]]; then
        echo -e "${BLUE}Checking for hardcoded ports (SSOT-aware)...${NC}"
    fi

    for port in "${!SSOT_PORTS[@]}"; do
        ssot_config="${SSOT_PORTS[$port]}"

        # Search for port in URL context (e.g., :8001/ or :8001")
        while IFS=: read -r file line_num line_content; do
            # Skip excluded files
            if should_exclude_file "$file"; then
                continue
            fi

            # Skip comments
            if [[ "$line_content" =~ ^[[:space:]]*# ]] || [[ "$line_content" =~ ^[[:space:]]*// ]]; then
                continue
            fi

            # Skip if using getenv/config access
            if echo "$line_content" | grep -qE '(getenv|config\.|CONFIG\[|NetworkConstants|AUTOBOT_)'; then
                continue
            fi

            # Skip array slicing, Docker user mapping, OWASP IDs
            if echo "$line_content" | grep -qE '(\[:[0-9]|"[0-9]+:[0-9]+"|A[0-9]{2}:[0-9]{4})'; then
                continue
            fi

            report_ssot_violation "$file" "$line_num" ":$port" "$ssot_config" "$line_content"

        done < <(grep -rn --include="*.py" --include="*.ts" --include="*.vue" \
            -E ":${port}[^0-9]" "$PROJECT_ROOT/src" "$PROJECT_ROOT/backend" "$PROJECT_ROOT/autobot-slm-frontend/src" 2>/dev/null | head -30 || true)
    done
}

# Scan for hardcoded LLM model names with SSOT suggestions
scan_ssot_models() {
    if [[ "$JSON_MODE" == "false" ]]; then
        echo -e "${BLUE}Checking for hardcoded LLM model names (SSOT-aware)...${NC}"
    fi

    for model in "${!SSOT_MODELS[@]}"; do
        ssot_config="${SSOT_MODELS[$model]}"

        while IFS=: read -r file line_num line_content; do
            # Skip excluded files and special files
            if should_exclude_file "$file"; then
                continue
            fi

            # Skip config files
            if [[ "$file" == *"config"* ]] || [[ "$file" == *"failsafe"* ]]; then
                continue
            fi

            # Skip comments
            if [[ "$line_content" =~ ^[[:space:]]*# ]]; then
                continue
            fi

            # Skip if using getenv/config access
            if echo "$line_content" | grep -qE '(os\.getenv|config\.get|getenv|CONFIG\[|AUTOBOT_)'; then
                continue
            fi

            report_ssot_violation "$file" "$line_num" "$model" "$ssot_config" "$line_content"

        done < <(grep -rn --include="*.py" -F "$model" \
            "$PROJECT_ROOT/src" "$PROJECT_ROOT/backend" 2>/dev/null | grep -v "archive/" | grep -v "__pycache__" || true)
    done

    # Also scan for generic model patterns
    while IFS=: read -r file line_num line_content; do
        if should_exclude_file "$file"; then
            continue
        fi

        if [[ "$file" == *"config"* ]] || [[ "$file" == *"failsafe"* ]] || [[ "$file" == *"llm_interface"* ]]; then
            continue
        fi

        if [[ "$line_content" =~ ^[[:space:]]*# ]]; then
            continue
        fi

        if echo "$line_content" | grep -qE '(os\.getenv|config\.get|getenv|CONFIG\[)'; then
            continue
        fi

        report_violation "$file" "$line_num" "Hardcoded model name: $line_content" \
            "Use config.llm.default_model or os.getenv('AUTOBOT_DEFAULT_LLM_MODEL')"

    done < <(grep -rn --include="*.py" \
        -E '(llama3|dolphin|openchat|gemma|phi|deepseek|qwen).*:[0-9]+(b|B)' \
        "$PROJECT_ROOT/src" "$PROJECT_ROOT/backend" 2>/dev/null | \
        grep -v "archive/" | grep -v "__pycache__" || true)
}

# Scan for hardcoded URLs (general - not SSOT specific)
scan_urls() {
    if [[ "$JSON_MODE" == "false" ]]; then
        echo -e "${BLUE}Checking for hardcoded URLs...${NC}"
    fi

    while IFS=: read -r file line_num line_content; do
        if should_exclude_file "$file"; then
            continue
        fi

        # Skip enterprise templates, security configs
        if [[ "$file" == *"enterprise"* ]] || [[ "$file" == *"sso_integration"* ]] || \
           [[ "$file" == *"injection_detector"* ]] || [[ "$file" == *"domain_security"* ]] || \
           [[ "$file" == *"secure_llm"* ]] || [[ "$file" == *"secure_web"* ]]; then
            continue
        fi

        if [[ "$line_content" =~ ^[[:space:]]*# ]] || [[ "$line_content" =~ ^[[:space:]]*// ]]; then
            continue
        fi

        # Skip if using config access or example domains
        if echo "$line_content" | grep -qE '(getenv|config\.|CONFIG\[|example\.com|example\.org|example\.net|autobot\.local)'; then
            continue
        fi

        # Check if URL contains known SSOT IPs - report as SSOT violation
        for ip in "${!SSOT_VM_IPS[@]}"; do
            if [[ "$line_content" == *"$ip"* ]]; then
                report_ssot_violation "$file" "$line_num" "$ip" "${SSOT_VM_IPS[$ip]}" "$line_content"
                continue 2
            fi
        done

        report_violation "$file" "$line_num" "Hardcoded URL: ${line_content:0:60}..." \
            "Use SSOT config URLs (config.backend_url, config.redis_url, etc.)"

    done < <(grep -rn --include="*.py" --include="*.ts" --include="*.vue" \
        -E 'https?://[a-zA-Z0-9]' "$PROJECT_ROOT/src" "$PROJECT_ROOT/backend" "$PROJECT_ROOT/autobot-slm-frontend/src" 2>/dev/null | \
        grep -v "archive/" | grep -v "__pycache__" | head -30 || true)
}

# =============================================================================
# Report Generation
# =============================================================================

generate_report() {
    echo ""
    echo "============================================="
    echo "        SSOT COMPLIANCE REPORT"
    echo "============================================="
    echo ""
    echo "Total violations found: $VIOLATIONS_FOUND"
    echo "  - SSOT violations (has config equivalent): $SSOT_VIOLATIONS"
    echo "  - Other violations: $((VIOLATIONS_FOUND - SSOT_VIOLATIONS))"
    echo ""
    echo "SSOT Config Categories Checked:"
    echo "  - VM IPs: ${#SSOT_VM_IPS[@]} mappings"
    echo "  - Ports: ${#SSOT_PORTS[@]} mappings"
    echo "  - LLM Models: ${#SSOT_MODELS[@]} mappings"
    echo ""
    echo "Files scanned in:"
    echo "  - $PROJECT_ROOT/src"
    echo "  - $PROJECT_ROOT/backend"
    echo "  - $PROJECT_ROOT/autobot-slm-frontend/src"
    echo ""

    if [[ $SSOT_VIOLATIONS -gt 0 ]]; then
        echo -e "${RED}HIGH PRIORITY: $SSOT_VIOLATIONS values have SSOT equivalents!${NC}"
        echo ""
        echo "Quick fix steps:"
        echo "  1. Import SSOT config in your file:"
        echo "     Python:     from src.config.ssot_config import config"
        echo "     TypeScript: import config from '@/config/ssot-config'"
        echo ""
        echo "  2. Replace hardcoded values with config properties:"
        echo "     config.vm.main      -> Backend host IP"
        echo "     config.port.backend -> Backend port"
        echo "     config.backend_url  -> Full backend URL"
        echo ""
        echo "Documentation: docs/developer/SSOT_CONFIG_GUIDE.md"
    fi
}

generate_json_output() {
    cat <<EOF
{
  "total_violations": $VIOLATIONS_FOUND,
  "ssot_violations": $SSOT_VIOLATIONS,
  "other_violations": $((VIOLATIONS_FOUND - SSOT_VIOLATIONS)),
  "status": "$(if [[ $VIOLATIONS_FOUND -eq 0 ]]; then echo "pass"; else echo "fail"; fi)",
  "ssot_mappings": {
    "vm_ips": ${#SSOT_VM_IPS[@]},
    "ports": ${#SSOT_PORTS[@]},
    "models": ${#SSOT_MODELS[@]}
  }
}
EOF
}

# =============================================================================
# Main Execution
# =============================================================================

if [[ "$JSON_MODE" == "false" ]]; then
    echo "============================================="
    echo " SSOT-Aware Hardcoded Value Detection"
    echo " Issue #642 - SSOT Config Validation"
    echo "============================================="
    echo ""
fi

# Run SSOT-aware scans
scan_ssot_ips
scan_ssot_ports
scan_ssot_models
scan_urls

# Output results
if [[ "$JSON_MODE" == "true" ]]; then
    generate_json_output
elif [[ "$REPORT_MODE" == "true" ]]; then
    generate_report
else
    # Standard summary
    echo ""
    echo "============================================="
    if [[ $VIOLATIONS_FOUND -eq 0 ]]; then
        echo -e "${GREEN}No hardcoding violations found!${NC}"
        exit 0
    else
        echo -e "${RED}Found $VIOLATIONS_FOUND hardcoding violation(s)${NC}"
        if [[ $SSOT_VIOLATIONS -gt 0 ]]; then
            echo -e "${YELLOW}  - $SSOT_VIOLATIONS have SSOT config equivalents (high priority)${NC}"
        fi
        echo ""
        echo "Quick fixes:"
        echo "  1. Use SSOT config: from src.config.ssot_config import config"
        echo "  2. Use environment variables: os.getenv('AUTOBOT_*')"
        echo "  3. See: docs/developer/SSOT_CONFIG_GUIDE.md"
        echo ""
        exit 1
    fi
fi

exit 0
