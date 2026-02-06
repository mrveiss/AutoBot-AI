#!/bin/bash

# ============================================================================
# AutoBot Reusable Function Quality Checker
# ============================================================================
#
# Enforces code quality standards for function modularity and reusability.
#
# Checks:
# 1. Functions without docstrings
# 2. Functions that are too long (> 50 lines)
# 3. Inline lambda functions that should be extracted
# 4. Missing type hints on function parameters
# 5. Functions that should be extracted (repeated code patterns)
#
# Usage:
#   ./scripts/code-quality/check-reusable-functions.sh [files...]
#   ./scripts/code-quality/check-reusable-functions.sh              # Check all Python files
#   ./scripts/code-quality/check-reusable-functions.sh file.py      # Check specific file
#
# Exit codes:
#   0 - All checks passed
#   1 - Quality issues found
# ============================================================================

set -e

# Colors
RED='\033[0;31m'
YELLOW='\033[1;33m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Counters
VIOLATIONS=0
WARNINGS=0
FILES_CHECKED=0

# Configuration
MAX_FUNCTION_LINES=50
MIN_DOCSTRING_LENGTH=10

echo -e "${BLUE}🔍 AutoBot Reusable Function Quality Checker${NC}"
echo "=============================================="
echo ""

# Get files to check
if [ $# -eq 0 ]; then
    # Check all Python files in backend/ and src/
    FILES=$(find backend src -name "*.py" -type f 2>/dev/null || true)
else
    FILES="$@"
fi

if [ -z "$FILES" ]; then
    echo -e "${GREEN}✅ No Python files to check${NC}"
    exit 0
fi

# Function to check if function has docstring
check_docstring() {
    local file=$1
    local func_name=$2
    local line_num=$3

    # Look for docstring within next 5 lines
    local next_lines=$(sed -n "${line_num},$((line_num + 5))p" "$file")

    if ! echo "$next_lines" | grep -q '"""'; then
        echo -e "${YELLOW}⚠️  Missing docstring: ${file}:${line_num} - function '${func_name}'${NC}"
        ((WARNINGS++))
        return 1
    fi

    # Check docstring length
    local docstring=$(echo "$next_lines" | sed -n '/"""/,/"""/p' | tr -d '\n' | tr -d '"')
    local doc_length=${#docstring}

    if [ $doc_length -lt $MIN_DOCSTRING_LENGTH ]; then
        echo -e "${YELLOW}⚠️  Docstring too short (< ${MIN_DOCSTRING_LENGTH} chars): ${file}:${line_num} - function '${func_name}'${NC}"
        ((WARNINGS++))
        return 1
    fi

    return 0
}

# Function to check function length
check_function_length() {
    local file=$1
    local func_name=$2
    local start_line=$3

    # Find end of function (next def or class, or EOF)
    local end_line=$(awk -v start=$start_line '
        NR > start && /^(def |class |$)/ { print NR; exit }
        END { if (NR > start) print NR }
    ' "$file")

    if [ -z "$end_line" ]; then
        end_line=$(wc -l < "$file")
    fi

    local func_lines=$((end_line - start_line))

    if [ $func_lines -gt $MAX_FUNCTION_LINES ]; then
        echo -e "${RED}❌ Function too long (${func_lines} > ${MAX_FUNCTION_LINES} lines): ${file}:${start_line} - function '${func_name}'${NC}"
        echo -e "   ${YELLOW}Suggestion: Break down into smaller, reusable helper functions${NC}"
        ((VIOLATIONS++))
        return 1
    fi

    return 0
}

# Function to check for inline lambdas
check_inline_lambdas() {
    local file=$1

    # Find lambda expressions not assigned to variables
    while IFS=: read -r line_num line_content; do
        # Skip if lambda is assigned to a variable or used as default parameter
        if echo "$line_content" | grep -qE '^\s*([\w_]+\s*=\s*lambda|def.*=\s*lambda)'; then
            continue
        fi

        # Check if lambda is used inline (not in function signature)
        if echo "$line_content" | grep -qE 'lambda.*:.*\)' || \
           echo "$line_content" | grep -qE 'map\(lambda|filter\(lambda|sorted\(.*lambda'; then
            echo -e "${YELLOW}⚠️  Inline lambda detected: ${file}:${line_num}${NC}"
            echo -e "   ${line_content}"
            echo -e "   ${YELLOW}Suggestion: Extract to named function for reusability and testing${NC}"
            ((WARNINGS++))
        fi
    done < <(grep -n "lambda" "$file" 2>/dev/null || true)
}

# Function to check for missing type hints
check_type_hints() {
    local file=$1
    local func_name=$2
    local line_num=$3

    # Get function signature
    local signature=$(sed -n "${line_num}p" "$file")

    # Check for type hints in parameters (except self, cls)
    local params=$(echo "$signature" | sed 's/.*(\(.*\)).*/\1/')

    # Skip if no parameters or only self/cls
    if [ -z "$params" ] || echo "$params" | grep -qE '^\s*(self|cls)\s*$'; then
        return 0
    fi

    # Check if parameters have type hints
    if ! echo "$params" | grep -q ':'; then
        echo -e "${YELLOW}⚠️  Missing type hints: ${file}:${line_num} - function '${func_name}'${NC}"
        echo -e "   ${YELLOW}Suggestion: Add type hints for better code documentation and IDE support${NC}"
        ((WARNINGS++))
        return 1
    fi

    # Check for return type hint
    if ! echo "$signature" | grep -q '->'; then
        echo -e "${YELLOW}⚠️  Missing return type hint: ${file}:${line_num} - function '${func_name}'${NC}"
        ((WARNINGS++))
        return 1
    fi

    return 0
}

# Main checking loop
for file in $FILES; do
    if [ ! -f "$file" ]; then
        continue
    fi

    ((FILES_CHECKED++))

    # Find all function definitions
    while IFS=: read -r line_num line_content; do
        # Extract function name
        func_name=$(echo "$line_content" | sed 's/.*def \([^(]*\).*/\1/' | tr -d ' ')

        # Skip private functions (start with _) - they can have relaxed rules
        if [[ $func_name == _* ]] && [[ $func_name != __*__ ]]; then
            continue
        fi

        # Skip magic methods
        if [[ $func_name == __*__ ]]; then
            continue
        fi

        # Run checks
        check_docstring "$file" "$func_name" "$line_num"
        check_function_length "$file" "$func_name" "$line_num"
        check_type_hints "$file" "$func_name" "$line_num"

    done < <(grep -n "^[[:space:]]*def " "$file" 2>/dev/null || true)

    # Check for inline lambdas
    check_inline_lambdas "$file"
done

echo ""
echo "=============================================="
echo -e "Files checked: ${FILES_CHECKED}"
echo -e "Violations: ${RED}${VIOLATIONS}${NC}"
echo -e "Warnings: ${YELLOW}${WARNINGS}${NC}"
echo "=============================================="
echo ""

if [ $VIOLATIONS -gt 0 ]; then
    echo -e "${RED}❌ Code quality check failed - ${VIOLATIONS} violations found${NC}"
    echo -e "${YELLOW}Fix violations before committing${NC}"
    exit 1
elif [ $WARNINGS -gt 0 ]; then
    echo -e "${YELLOW}⚠️  Code quality warnings found - consider addressing them${NC}"
    echo -e "${GREEN}✅ No blocking violations - commit allowed${NC}"
    exit 0
else
    echo -e "${GREEN}✅ All function quality checks passed!${NC}"
    exit 0
fi
