#!/bin/bash
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# Test script for the startup coordinator
# (#14867) These lines were a Python '"""' docstring that bash executed as
# commands, emitting "command not found" noise that hid the real failures below.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# Import roots for the inline Python below, derived from this script's own
# location: startup_coordinator.py sits next to this script, and the repo root
# is three levels up (scripts/ -> shared/ -> autobot-infrastructure/ -> root).
# Without these the import test could never pass, and its stderr was discarded
# so the script reported success anyway (#14867).
REPO_ROOT="$(cd "${SCRIPT_DIR}/../../.." && pwd)"
export PYTHONPATH="${SCRIPT_DIR}:${REPO_ROOT}/autobot-backend:${REPO_ROOT}:${PYTHONPATH:-}"

# Every failed check increments this; the summary refuses to claim success
# while it is non-zero (#14867).
FAILURES=0

echo "🧪 Testing AutoBot Startup Coordinator"
echo "======================================"

# Test 1: Check startup coordinator can be imported
echo "Test 1: Python import test..."
if python3 -c "from startup_coordinator import StartupCoordinator; print('✅ Import successful')"; then
    echo "✅ Startup coordinator imports successfully"
else
    echo "❌ Failed to import startup coordinator"
    echo "Installing required dependencies..."
    pip3 install requests psutil
    if python3 -c "from startup_coordinator import StartupCoordinator; print('✅ Import successful')"; then
        echo "✅ Dependencies installed, import successful"
    else
        echo "❌ Still failing after dependency install"
        exit 1
    fi
fi

# Test 2: Check component status
echo -e "\nTest 2: Component status check..."
# (#14867) The coordinator lives next to this script, not under a "scripts/"
# directory relative to the caller's cwd, and a non-zero exit must be recorded.
if ! python3 "${SCRIPT_DIR}/startup_coordinator.py" --status; then
    echo "❌ Component status check failed - see the error above" >&2
    FAILURES=$((FAILURES + 1))
fi

# Test 3: Test backend health endpoint (if running)
echo -e "\nTest 3: Backend health check..."
if curl -s http://127.0.0.3:8001/api/system/health >/dev/null 2>&1; then
    echo "✅ Backend is already running and responding"
else
    echo "ℹ️  Backend not currently running (expected for fresh start)"
fi

# Test 4: Validate startup component definitions
echo -e "\nTest 4: Startup component validation..."
if ! python3 -c "
import sys
sys.path.append('.')
from startup_coordinator import StartupCoordinator

coordinator = StartupCoordinator()
print(f'✅ Defined components: {list(coordinator.components.keys())}')

# Check dependencies
for name, comp in coordinator.components.items():
    for dep in comp.dependencies:
        if dep not in coordinator.components:
            print(f'❌ Invalid dependency: {name} depends on unknown {dep}')
            sys.exit(1)

print('✅ All component dependencies are valid')
"; then
    echo "❌ Startup component validation failed - see the traceback above" >&2
    FAILURES=$((FAILURES + 1))
fi

echo -e "\n🎯 Test Results:"
# (#14867) A failed check used to print an X and still fall through to the
# "ready for use" banner with exit 0.
if [ "$FAILURES" -ne 0 ]; then
    echo "❌ $FAILURES startup coordinator check(s) failed - NOT ready for use" >&2
    exit 1
fi
echo "✅ Startup coordinator is ready for use!"
echo ""
echo "Usage examples:"
echo "  python3 scripts/startup_coordinator.py --status      # Show component status"
echo "  python3 scripts/startup_coordinator.py --components backend frontend  # Start specific components"
echo "  python3 scripts/startup_coordinator.py --stop        # Stop all components"
echo ""
echo "Integration with run_agent.sh:"
echo "  ./run_agent.sh                                        # Uses startup coordinator automatically"
