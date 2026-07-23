#!/bin/bash
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# Week 1 Tasks 1.5-1.6: Test Execution Script
# Run comprehensive tests for ConversationFileManager database initialization

set -e  # Exit on error

echo "═══════════════════════════════════════════════════════════════"
echo "Week 1 Tasks 1.5-1.6: Comprehensive Testing"
echo "═══════════════════════════════════════════════════════════════"
echo ""

# Color codes for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check if pytest is installed
if ! command -v pytest &> /dev/null; then
    echo -e "${YELLOW}⚠️  pytest not found. Installing...${NC}"
    pip install pytest pytest-asyncio
fi

# Create results directory
RESULTS_DIR="tests/results/week1_$(date +%Y%m%d_%H%M%S)"
mkdir -p "$RESULTS_DIR"

echo -e "${BLUE}📁 Results directory: $RESULTS_DIR${NC}"
echo ""

# Function to run test suite
run_test_suite() {
    local test_file=$1
    local test_name=$2
    local marker=$3

    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${BLUE}Running: $test_name${NC}"
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo ""

    if [ -n "$marker" ]; then
        pytest "$test_file" -v -m "$marker" \
            --tb=short \
            --asyncio-mode=auto \
            --log-cli-level=INFO \
            --junitxml="$RESULTS_DIR/${test_name}_results.xml"
    else
        pytest "$test_file" -v \
            --tb=short \
            --asyncio-mode=auto \
            --log-cli-level=INFO \
            --junitxml="$RESULTS_DIR/${test_name}_results.xml"
    fi

    if [ $? -eq 0 ]; then
        echo ""
        echo -e "${GREEN}✅ $test_name: PASSED${NC}"
    else
        echo ""
        echo -e "${YELLOW}❌ $test_name: FAILED${NC}"
        return 1
    fi
    echo ""
}

# Track overall success
overall_success=true

# Run Unit Tests (Task 1.5)
if ! run_test_suite \
    "tests/unit/test_conversation_file_manager_init.py" \
    "unit_tests" \
    ""; then
    overall_success=false
fi

# Run Integration Tests (Task 1.6)
if ! run_test_suite \
    "tests/distributed/test_db_initialization.py" \
    "integration_tests" \
    "integration"; then
    overall_success=false
fi

# Run with coverage
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${BLUE}Running: Coverage Analysis${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""

pytest tests/unit/test_conversation_file_manager_init.py \
    --cov=src.conversation_file_manager \
    --cov-report=html:"$RESULTS_DIR/coverage_report" \
    --cov-report=term \
    -v

if [ $? -eq 0 ]; then
    echo ""
    echo -e "${GREEN}✅ Coverage analysis: COMPLETE${NC}"
    echo -e "${BLUE}📊 Coverage report: $RESULTS_DIR/coverage_report/index.html${NC}"
else
    echo ""
    echo -e "${YELLOW}⚠️  Coverage analysis: INCOMPLETE${NC}"
fi

echo ""
echo "═══════════════════════════════════════════════════════════════"

# Final summary
if [ "$overall_success" = true ]; then
    echo -e "${GREEN}✅ ALL TESTS PASSED${NC}"
    echo ""
    echo "Test Results:"
    echo "  • Unit Tests (8 test cases): PASSED ✅"
    echo "  • Integration Tests (6 test cases): PASSED ✅"
    echo "  • Total Test Cases: 14"
    echo "  • Coverage Target: 100% for initialization code"
    echo ""
    echo -e "${BLUE}📁 Results saved to: $RESULTS_DIR${NC}"
    echo ""
    exit 0
else
    echo -e "${YELLOW}❌ SOME TESTS FAILED${NC}"
    echo ""
    echo "Check the output above for details."
    echo -e "${BLUE}📁 Results saved to: $RESULTS_DIR${NC}"
    echo ""
    exit 1
fi
