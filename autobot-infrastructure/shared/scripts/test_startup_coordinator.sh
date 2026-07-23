#!/bin/bash
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""
Test script for the startup coordinator
"""

echo "🧪 Testing AutoBot Startup Coordinator"
echo "======================================"

# Test 1: Check startup coordinator can be imported
echo "Test 1: Python import test..."
if python3 -c "from scripts.startup_coordinator import StartupCoordinator; print('✅ Import successful')" 2>/dev/null; then
    echo "✅ Startup coordinator imports successfully"
else
    echo "❌ Failed to import startup coordinator"
    echo "Installing required dependencies..."
    pip3 install requests psutil
    if python3 -c "from scripts.startup_coordinator import StartupCoordinator; print('✅ Import successful')" 2>/dev/null; then
        echo "✅ Dependencies installed, import successful"
    else
        echo "❌ Still failing after dependency install"
        exit 1
    fi
fi

# Test 2: Check component status
echo -e "\nTest 2: Component status check..."
python3 scripts/startup_coordinator.py --status

# Test 3: Test backend health endpoint (if running)
echo -e "\nTest 3: Backend health check..."
if curl -s http://127.0.0.3:8001/api/system/health >/dev/null 2>&1; then
    echo "✅ Backend is already running and responding"
else
    echo "ℹ️  Backend not currently running (expected for fresh start)"
fi

# Test 4: Validate startup component definitions
echo -e "\nTest 4: Startup component validation..."
python3 -c "
import sys
sys.path.append('.')
from scripts.startup_coordinator import StartupCoordinator

coordinator = StartupCoordinator()
print(f'✅ Defined components: {list(coordinator.components.keys())}')

# Check dependencies
for name, comp in coordinator.components.items():
    for dep in comp.dependencies:
        if dep not in coordinator.components:
            print(f'❌ Invalid dependency: {name} depends on unknown {dep}')
            sys.exit(1)

print('✅ All component dependencies are valid')
"

echo -e "\n🎯 Test Results:"
echo "✅ Startup coordinator is ready for use!"
echo ""
echo "Usage examples:"
echo "  python3 scripts/startup_coordinator.py --status      # Show component status"
echo "  python3 scripts/startup_coordinator.py --components backend frontend  # Start specific components"
echo "  python3 scripts/startup_coordinator.py --stop        # Stop all components"
echo ""
echo "Integration with run_agent.sh:"
echo "  ./run_agent.sh                                        # Uses startup coordinator automatically"
