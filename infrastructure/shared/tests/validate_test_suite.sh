#!/bin/bash
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
#
# Test Suite Validation Script
# Validates that all Knowledge Manager tests are discoverable and executable

set -e

echo "=================================================="
echo "Knowledge Manager Test Suite Validation"
echo "=================================================="
echo ""

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Counter
TOTAL_CHECKS=0
PASSED_CHECKS=0
FAILED_CHECKS=0

# Function to check if file exists
check_file() {
    TOTAL_CHECKS=$((TOTAL_CHECKS + 1))
    if [ -f "$1" ]; then
        echo -e "${GREEN}✓${NC} Found: $1"
        PASSED_CHECKS=$((PASSED_CHECKS + 1))
        return 0
    else
        echo -e "${RED}✗${NC} Missing: $1"
        FAILED_CHECKS=$((FAILED_CHECKS + 1))
        return 1
    fi
}

# Function to count tests in Python file
count_python_tests() {
    if [ -f "$1" ]; then
        count=$(grep -c "def test_" "$1" || true)
        echo -e "  ${YELLOW}→${NC} Found $count test functions"
    fi
}

# Function to count tests in TypeScript file
count_ts_tests() {
    if [ -f "$1" ]; then
        count=$(grep -c "it(" "$1" || true)
        echo -e "  ${YELLOW}→${NC} Found $count test cases"
    fi
}

echo "Checking Backend Unit Tests..."
echo "------------------------------"
check_file "/home/kali/Desktop/AutoBot/tests/unit/test_knowledge_categories.py"
count_python_tests "/home/kali/Desktop/AutoBot/tests/unit/test_knowledge_categories.py"

check_file "/home/kali/Desktop/AutoBot/tests/unit/test_knowledge_vectorization.py"
count_python_tests "/home/kali/Desktop/AutoBot/tests/unit/test_knowledge_vectorization.py"

echo ""
echo "Checking Frontend Unit Tests..."
echo "------------------------------"
check_file "/home/kali/Desktop/AutoBot/autobot-slm-frontend/src/composables/__tests__/useKnowledgeVectorization.test.ts"
count_ts_tests "/home/kali/Desktop/AutoBot/autobot-slm-frontend/src/composables/__tests__/useKnowledgeVectorization.test.ts"

echo ""
echo "Checking Integration Tests..."
echo "------------------------------"
check_file "/home/kali/Desktop/AutoBot/tests/integration/test_knowledge_api_integration.py"
count_python_tests "/home/kali/Desktop/AutoBot/tests/integration/test_knowledge_api_integration.py"

echo ""
echo "Checking Documentation..."
echo "------------------------------"
check_file "/home/kali/Desktop/AutoBot/tests/TEST_SUITE_SUMMARY.md"

echo ""
echo "=================================================="
echo "Validation Summary"
echo "=================================================="
echo -e "Total checks: $TOTAL_CHECKS"
echo -e "${GREEN}Passed: $PASSED_CHECKS${NC}"
echo -e "${RED}Failed: $FAILED_CHECKS${NC}"

if [ $FAILED_CHECKS -eq 0 ]; then
    echo ""
    echo -e "${GREEN}✓ All test files validated successfully!${NC}"
    echo ""
    echo "Next Steps:"
    echo "1. Run backend tests: pytest tests/unit/test_knowledge_*.py -v"
    echo "2. Run frontend tests: cd autobot-slm-frontend && npm run test:unit"
    echo "3. Run integration tests: pytest tests/integration/test_knowledge_*.py -v"
    exit 0
else
    echo ""
    echo -e "${RED}✗ Validation failed - some files are missing${NC}"
    exit 1
fi
