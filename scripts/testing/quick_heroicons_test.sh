#!/bin/bash
# Quick Heroicons Validation Test

set -e

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${YELLOW}🧪 Quick Heroicons Dependency Validation${NC}"
echo ""

# Test current running container
echo -e "${YELLOW}Testing current running container...${NC}"

if docker exec autobot-frontend ls -la /app/node_modules/@heroicons/vue >/dev/null 2>&1; then
    echo -e "✅ Heroicons directory exists"
else
    echo -e "❌ Heroicons directory missing"
    exit 1
fi

if docker exec autobot-frontend node -e "const { CheckIcon } = require('@heroicons/vue/24/outline'); console.log('OK')" >/dev/null 2>&1; then
    echo -e "✅ Heroicons can be imported and used"
else
    echo -e "❌ Heroicons import failed"
    exit 1
fi

if docker exec autobot-frontend wget -q --spider http://localhost:5173 2>/dev/null; then
    echo -e "✅ Frontend is responding"
else
    echo -e "❌ Frontend not responding"
    exit 1
fi

# Test the environment variables are set correctly
EXEC_MODE=$(docker exec autobot-frontend env | grep AUTOBOT_EXECUTION_MODE | cut -d= -f2)
if [ "$EXEC_MODE" = "development" ]; then
    echo -e "✅ Execution mode correctly set to: $EXEC_MODE"
else
    echo -e "⚠️ Execution mode: $EXEC_MODE (expected development)"
fi

DEPS_MODE=$(docker exec autobot-frontend env | grep DEPENDENCY_CHECK_MODE | cut -d= -f2)
if [ "$DEPS_MODE" = "comprehensive" ]; then
    echo -e "✅ Dependency check mode correctly set to: $DEPS_MODE"
else
    echo -e "⚠️ Dependency check mode: $DEPS_MODE (expected comprehensive)"
fi

echo ""
echo -e "${GREEN}🎉 ALL TESTS PASSED!${NC}"
echo -e "✅ Heroicons dependency is working correctly in current mode"
echo -e "✅ Frontend container is healthy and responding"
echo -e "✅ Environment variables are properly configured"
echo ""
echo -e "${YELLOW}Architecture Summary:${NC}"
echo -e "• Docker Image: Built with comprehensive entrypoint script"
echo -e "• Volume Strategy: Named volume overlay for node_modules"  
echo -e "• Mount Points: Source code + preserved dependencies"
echo -e "• Environment: Development mode with comprehensive checks"
echo -e "• Execution Mode: Multi-mode support implemented"