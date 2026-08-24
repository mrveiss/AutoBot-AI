#!/bin/bash
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# Comprehensive test suite for all fixes
# Usage: bash scripts/run-all-tests.sh

set -e  # Exit on first error

# #13149: this defaulted to the deployed install, so running it from a checkout
# read or wrote the LIVE install instead of this tree. The shared helper resolves
# the root from this file's own location; AUTOBOT_PROJECT_ROOT still overrides.
# shellcheck source=scripts/lib/project_root.sh
source "$(dirname "${BASH_SOURCE[0]}")/../../../scripts/lib/project_root.sh"

echo "🧪 AutoBot Comprehensive Test Suite"
echo "===================================="
echo ""

# Create timestamped results directory
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
RESULT_DIR="tests/results/comprehensive_test_${TIMESTAMP}"
mkdir -p "$RESULT_DIR"

echo "📁 Results directory: $RESULT_DIR"
echo ""

# Track overall status
FAILED=0
START_TIME=$(date +%s)

# Ensure we're in project root
cd ${PROJECT_ROOT}

# Phase 1: Unit Tests
echo "╔════════════════════════════════════════╗"
echo "║  Phase 1: Unit Tests (5 min target)   ║"
echo "╚════════════════════════════════════════╝"
echo ""

echo "📋 Running database initialization tests..."
python3 -m pytest tests/unit/test_database_init.py -v --tb=short \
    --junitxml="$RESULT_DIR/database_init_results.xml" || FAILED=$((FAILED + 1))
echo ""

echo "📋 Running context window manager tests..."
python3 -m pytest tests/unit/test_context_window_manager.py -v --tb=short \
    --junitxml="$RESULT_DIR/context_window_manager_results.xml" || FAILED=$((FAILED + 1))
echo ""

echo "📋 Running all unit tests..."
python3 -m pytest tests/unit/ -v --tb=short -x \
    --junitxml="$RESULT_DIR/all_unit_results.xml" \
    --cov=src --cov=backend --cov-report=html:"$RESULT_DIR/coverage" || FAILED=$((FAILED + 1))
echo ""

# Phase 2: Integration Tests
echo "╔════════════════════════════════════════╗"
echo "║ Phase 2: Integration (7 min target)   ║"
echo "╚════════════════════════════════════════╝"
echo ""

echo "🔗 Running context window integration tests..."
python3 -m pytest tests/integration/test_context_window_integration.py -v -s \
    --junitxml="$RESULT_DIR/context_window_integration_results.xml" || FAILED=$((FAILED + 1))
echo ""

echo "🔗 Running all integration tests..."
python3 -m pytest tests/integration/ -v -s -x \
    --junitxml="$RESULT_DIR/all_integration_results.xml" || FAILED=$((FAILED + 1))
echo ""

# Phase 3: Performance Tests
echo "╔════════════════════════════════════════╗"
echo "║ Phase 3: Performance (5 min target)   ║"
echo "╚════════════════════════════════════════╝"
echo ""

echo "⚡ Running async chat performance tests..."
python3 -m pytest tests/performance/test_async_chat_performance.py -v -s \
    --junitxml="$RESULT_DIR/async_chat_performance_results.xml" || FAILED=$((FAILED + 1))
echo ""

echo "⚡ Running context window performance tests..."
python3 -m pytest tests/performance/test_context_window_performance.py -v -s \
    --junitxml="$RESULT_DIR/context_window_performance_results.xml" || FAILED=$((FAILED + 1))
echo ""

echo "⚡ Running all performance tests..."
python3 -m pytest tests/performance/ -v -s \
    --junitxml="$RESULT_DIR/all_performance_results.xml" || FAILED=$((FAILED + 1))
echo ""

# Phase 4: Service Auth Verification
echo "╔════════════════════════════════════════╗"
echo "║ Phase 4: Service Auth (3 min target)  ║"
echo "╚════════════════════════════════════════╝"
echo ""

echo "🔐 Verifying service authentication..."
python3 scripts/verify-service-auth.py > "$RESULT_DIR/service_auth_verification.txt" 2>&1 || FAILED=$((FAILED + 1))
cat "$RESULT_DIR/service_auth_verification.txt"
echo ""

# Calculate duration
END_TIME=$(date +%s)
DURATION=$((END_TIME - START_TIME))

# Summary
echo "╔════════════════════════════════════════╗"
echo "║         Test Results Summary           ║"
echo "╚════════════════════════════════════════╝"
echo ""
echo "Total Duration: ${DURATION}s (target: 1200s / 20 min)"
echo "Results Directory: $RESULT_DIR"
echo ""

if [ $FAILED -eq 0 ]; then
    echo "✅ All tests PASSED"
    echo "Ready for deployment"
    echo ""
    echo "Next steps:"
    echo "  1. Review test results in: $RESULT_DIR"
    echo "  2. Check coverage report: $RESULT_DIR/coverage/index.html"
    echo "  3. Proceed with deployment"
    exit 0
else
    echo "❌ $FAILED test suite(s) FAILED"
    echo ""
    echo "Review failures:"
    echo "  - Check XML results in: $RESULT_DIR"
    echo "  - Review test output above"
    echo "  - Fix failing tests before deployment"
    exit 1
fi
