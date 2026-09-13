#!/bin/bash
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# Performance Benchmark Runner
# Issue #58 - Performance Benchmarking Suite
# Author: mrveiss

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BENCHMARK_DIR="$PROJECT_ROOT/tests/benchmarks"
RESULTS_DIR="$PROJECT_ROOT/reports/benchmarks"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
RESULTS_FILE="$RESULTS_DIR/benchmark_results_${TIMESTAMP}.json"

echo -e "${BLUE}=== AutoBot Performance Benchmarking Suite ===${NC}"
echo -e "Timestamp: $(date)"
echo -e "Project Root: ${PROJECT_ROOT}"
echo ""

# Parse arguments
CATEGORY="all"
VERBOSE=""
SAVE_RESULTS=true
COMPARE_BASELINE=false

while [[ $# -gt 0 ]]; do
    case $1 in
        --api)
            CATEGORY="api"
            shift
            ;;
        --rag)
            CATEGORY="rag"
            shift
            ;;
        --all)
            CATEGORY="all"
            shift
            ;;
        -v|--verbose)
            VERBOSE="-v"
            shift
            ;;
        --no-save)
            SAVE_RESULTS=false
            shift
            ;;
        --compare)
            COMPARE_BASELINE=true
            shift
            ;;
        -h|--help)
            echo "Usage: $0 [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  --api          Run only API benchmarks"
            echo "  --rag          Run only RAG benchmarks"
            echo "  --all          Run all benchmarks (default)"
            echo "  -v, --verbose  Verbose output"
            echo "  --no-save      Don't save results to file"
            echo "  --compare      Compare against baseline"
            echo "  -h, --help     Show this help"
            exit 0
            ;;
        *)
            echo -e "${RED}Unknown option: $1${NC}"
            exit 1
            ;;
    esac
done

# Create results directory
mkdir -p "$RESULTS_DIR"

# Change to project root
cd "$PROJECT_ROOT"

# Activate virtual environment if exists
if [ -f "venv/bin/activate" ]; then
    echo -e "${YELLOW}Activating virtual environment...${NC}"
    source venv/bin/activate
fi

# Verify dependencies
echo -e "${BLUE}Checking dependencies...${NC}"
python -c "import pytest; import numpy" 2>/dev/null || {
    echo -e "${RED}Missing dependencies. Install with: pip install pytest numpy${NC}"
    exit 1
}

echo -e "${GREEN}Dependencies OK${NC}"
echo ""

# Run benchmarks based on category
echo -e "${BLUE}Running benchmarks (Category: ${CATEGORY})...${NC}"
echo ""

PYTEST_ARGS="-x --tb=short $VERBOSE"

case $CATEGORY in
    api)
        echo -e "${YELLOW}=== API Endpoint Benchmarks ===${NC}"
        python -m pytest "$BENCHMARK_DIR/api_benchmarks.py" $PYTEST_ARGS
        ;;
    rag)
        echo -e "${YELLOW}=== RAG Query Benchmarks ===${NC}"
        python -m pytest "$BENCHMARK_DIR/rag_benchmarks.py" $PYTEST_ARGS
        ;;
    all)
        echo -e "${YELLOW}=== All Benchmarks ===${NC}"
        python -m pytest "$BENCHMARK_DIR/" $PYTEST_ARGS
        ;;
esac

BENCHMARK_EXIT_CODE=$?

echo ""

# Save results if enabled
if [ "$SAVE_RESULTS" = true ]; then
    echo -e "${BLUE}Saving benchmark results...${NC}"

    # (#14876) pytest-json-report is what produces the machine-readable
    # benchmark report; it is declared in
    # autobot-infrastructure/shared/scripts/requirements.txt. Two things were
    # wrong here. The plugin check discarded stderr, so a broken install read
    # as an absent one; and the fallback wrote a file with the same name and
    # extension as a real report while containing no measurements at all, so a
    # run that measured nothing was indistinguishable downstream from one that
    # measured everything.
    if python -c "import pytest_json_report"; then
        if ! python -m pytest "$BENCHMARK_DIR/" --json-report --json-report-file="$RESULTS_FILE" --quiet; then
            echo -e "${RED}Benchmark report generation FAILED - ${RESULTS_FILE} is incomplete or absent${NC}" >&2
            exit 1
        fi
        echo -e "${GREEN}Results saved to: ${RESULTS_FILE}${NC}"
    else
        echo -e "${RED}pytest-json-report is not installed, so NO benchmark report was produced.${NC}" >&2
        echo -e "${RED}Install it with: pip install -r autobot-infrastructure/shared/scripts/requirements.txt${NC}" >&2
        # Deliberately marked, and deliberately not named like a report: a
        # consumer that finds this file must not be able to read it as results.
        cat > "${RESULTS_FILE}.no-report" << EOF
{
  "measured": false,
  "reason": "pytest-json-report not installed; no benchmark results were recorded",
  "timestamp": "$(date -Iseconds)",
  "category": "$CATEGORY",
  "exit_code": $BENCHMARK_EXIT_CODE
}
EOF
        exit 1
    fi
fi

# Compare against baseline if requested
if [ "$COMPARE_BASELINE" = true ]; then
    BASELINE_FILE="$RESULTS_DIR/baseline.json"
    if [ -f "$BASELINE_FILE" ]; then
        echo -e "${BLUE}Comparing against baseline...${NC}"
        # Comparison would be done by Python script
        echo -e "${YELLOW}Baseline comparison not yet implemented${NC}"
    else
        echo -e "${YELLOW}No baseline file found at: ${BASELINE_FILE}${NC}"
        echo -e "To set baseline: cp ${RESULTS_FILE} ${BASELINE_FILE}"
    fi
fi

echo ""

# Summary
if [ $BENCHMARK_EXIT_CODE -eq 0 ]; then
    echo -e "${GREEN}=== Benchmarking Complete (PASSED) ===${NC}"
else
    echo -e "${RED}=== Benchmarking Complete (SOME FAILURES) ===${NC}"
fi

echo -e "Results: ${RESULTS_DIR}/"
echo -e "Run with -v for detailed output"
echo ""

# Quick performance summary
echo -e "${BLUE}Quick Performance Summary:${NC}"
echo "  - Run API benchmarks: $0 --api"
echo "  - Run RAG benchmarks: $0 --rag"
echo "  - Run all benchmarks: $0 --all"
echo "  - Verbose mode: $0 --all -v"
echo ""

exit $BENCHMARK_EXIT_CODE
