#!/bin/bash

# Terminal Input Consistency Test Script
# Tests the terminal input fixes for automated testing scenarios

echo "🧪 Terminal Input Consistency Test"
echo "=================================="

# Check if frontend and backend are running
echo "📡 Checking system status..."

# Check frontend (Vue app)
FRONTEND_STATUS=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:3000 2>/dev/null || echo "000")
if [ "$FRONTEND_STATUS" != "200" ]; then
    echo "❌ Frontend not accessible at http://localhost:3000 (status: $FRONTEND_STATUS)"
    echo "   Please start the frontend with 'npm run dev' in autobot-vue/"
    echo ""
fi

# Check backend API
BACKEND_STATUS=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:8001/api/system/health 2>/dev/null || echo "000")
if [ "$BACKEND_STATUS" != "200" ]; then
    echo "❌ Backend not accessible at http://localhost:8001 (status: $BACKEND_STATUS)"
    echo "   Please start the backend with './run_agent.sh' or 'python main.py'"
    echo ""
fi

# If both are running, run the specific terminal test
if [ "$FRONTEND_STATUS" = "200" ] && [ "$BACKEND_STATUS" = "200" ]; then
    echo "✅ Both frontend and backend are accessible"
    echo ""
    echo "🎯 Running terminal input consistency test..."
    echo ""

    cd autobot-vue

    # Run only our specific test
    npx playwright test tests/gui/test_terminal_input_consistency.js --headed --workers=1

    RESULT=$?

    if [ $RESULT -eq 0 ]; then
        echo ""
        echo "✅ Terminal input consistency test PASSED"
        echo "   Terminal input handling improvements are working correctly"
    else
        echo ""
        echo "❌ Terminal input consistency test FAILED"
        echo "   There may be issues with the terminal input improvements"
    fi

    cd ..
else
    echo "🚫 Cannot run test - system components not fully available"
    echo ""
    echo "To test the terminal input fixes:"
    echo "1. Start the backend: ./run_agent.sh"
    echo "2. Start the frontend: cd autobot-vue && npm run dev"
    echo "3. Re-run this test script"
fi

echo ""
echo "📋 Terminal Input Fixes Summary:"
echo "• Enhanced focusInput() with double-check mechanism"
echo "• Improved connection status handling for input readiness"
echo "• Added testing utilities (isTerminalReady, ensureInputFocus)"
echo "• Automatic focus recovery on clicks within terminal area"
echo "• Periodic focus validation for automation scenarios"
echo "• Proper cleanup of focus intervals on unmount"
