#!/usr/bin/env bash
#
# AutoBot Async Operations Baseline Performance Testing - Quick Execution Script
# Week 2-3 Task 2.5: Performance Load Testing
#
# Usage:
#   bash tests/performance/run_baseline.sh
#
# This script:
# 1. Checks if backend is running
# 2. Executes baseline performance tests
# 3. Displays results summary
# 4. Stores results for future comparison

set -e  # Exit on error

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
_PROJECT_ROOT="$SCRIPT_DIR"
while [ "$_PROJECT_ROOT" != "/" ] && [ ! -f "$_PROJECT_ROOT/.env" ]; do
    _PROJECT_ROOT="$(dirname "$_PROJECT_ROOT")"
done
source "$_PROJECT_ROOT/infrastructure/shared/scripts/lib/ssot-config.sh" 2>/dev/null || true
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

echo "================================================================================"
echo "AutoBot Async Operations Baseline Performance Testing"
echo "Week 2-3 Task 2.5: Baseline Measurement BEFORE Async Conversions"
echo "================================================================================"
echo ""

# Backend configuration from environment or defaults
BACKEND_HOST="${AUTOBOT_BACKEND_HOST:-172.16.168.20}"
BACKEND_PORT="${AUTOBOT_BACKEND_PORT:-8001}"
BACKEND_URL="http://${BACKEND_HOST}:${BACKEND_PORT}"

# Check if backend is running
echo "🔍 Checking if AutoBot backend is running..."
if ! curl -s -f "${BACKEND_URL}/api/health" > /dev/null 2>&1; then
    echo ""
    echo "❌ ERROR: AutoBot backend is not running!"
    echo ""
    echo "Please start AutoBot first:"
    echo "  cd ${PROJECT_ROOT}"
    echo "  bash run_autobot.sh --dev"
    echo ""
    exit 1
fi

echo "✅ Backend is running"
echo ""

# Check Python dependencies
echo "🔍 Checking Python dependencies..."
python3 -c "import aiohttp, redis, aiofiles" 2>/dev/null || {
    echo ""
    echo "⚠️  Missing dependencies. Installing..."
    pip install aiohttp redis aiofiles
    echo ""
}

echo "✅ Dependencies installed"
echo ""

# Create results directory
mkdir -p "${SCRIPT_DIR}/results"

# Execute baseline tests
echo "🚀 Running baseline performance tests..."
echo "   This will take approximately 5-10 minutes..."
echo ""

cd "${PROJECT_ROOT}"
python3 tests/performance/test_async_baseline.py

echo ""
echo "================================================================================"
echo "✅ Baseline Testing Complete!"
echo "================================================================================"
echo ""
echo "📊 Results saved to: tests/performance/results/"
echo ""
echo "📄 Next Steps:"
echo "   1. Review results summary above"
echo "   2. Store baseline results for comparison"
echo "   3. Wait for async conversions (Tasks 2.1-2.4)"
echo "   4. Re-run this script after async implementation"
echo "   5. Validate 10-50x performance improvements"
echo ""
echo "📖 Documentation: tests/performance/README_ASYNC_VALIDATION.md"
echo "================================================================================"
