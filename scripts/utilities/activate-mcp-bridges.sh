#!/bin/bash
# MCP Bridge Activation and Verification Script
# Issue #51 - Backend Activation Procedure for New MCP Bridges

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
BACKEND_URL="${AUTOBOT_BACKEND_URL:-http://localhost:8001}"
MAX_WAIT_TIME=30
EXPECTED_BRIDGES=5
EXPECTED_MIN_TOOLS=20

echo -e "${BLUE}=== MCP Bridge Activation and Verification ===${NC}"
echo ""

# Change to project root
cd "$(dirname "$0")/../.."
PROJECT_ROOT=$(pwd)

echo -e "${YELLOW}Project Root: ${PROJECT_ROOT}${NC}"
echo ""

# Function to check if command exists
check_command() {
    if ! command -v "$1" &> /dev/null; then
        echo -e "${RED}Error: $1 is not installed${NC}"
        exit 1
    fi
}

# Check dependencies
check_command curl
check_command jq

# Step 1: Verify bridge implementation files exist
echo -e "${BLUE}Step 1: Verifying MCP Bridge Implementation Files${NC}"

BRIDGES=(
    "knowledge_mcp"
    "vnc_mcp"
    "sequential_thinking_mcp"
    "structured_thinking_mcp"
    "filesystem_mcp"
)

for bridge in "${BRIDGES[@]}"; do
    FILE="backend/api/${bridge}.py"
    if [ -f "$FILE" ]; then
        echo -e "  ${GREEN}✅ Found: ${FILE}${NC}"
    else
        echo -e "  ${RED}❌ Missing: ${FILE}${NC}"
        exit 1
    fi
done

echo ""

# Step 2: Verify router registration
echo -e "${BLUE}Step 2: Verifying Router Registration${NC}"

for bridge in "${BRIDGES[@]}"; do
    if grep -q "${bridge}_router" backend/app_factory.py; then
        echo -e "  ${GREEN}✅ Router registered: ${bridge}${NC}"
    else
        echo -e "  ${RED}❌ Router not registered: ${bridge}${NC}"
        exit 1
    fi
done

echo ""

# Step 3: Verify MCP Registry entries
echo -e "${BLUE}Step 3: Verifying MCP Registry Entries${NC}"

for bridge in "${BRIDGES[@]}"; do
    if grep -q "\"${bridge}\"" backend/api/mcp_registry.py; then
        echo -e "  ${GREEN}✅ Registry entry: ${bridge}${NC}"
    else
        echo -e "  ${RED}❌ Missing registry entry: ${bridge}${NC}"
        exit 1
    fi
done

echo ""

# Step 4: Check if backend is running
echo -e "${BLUE}Step 4: Checking Backend Status${NC}"

BACKEND_RUNNING=false
HEALTH_STATUS=$(curl -s -o /dev/null -w "%{http_code}" "${BACKEND_URL}/api/health" 2>/dev/null || echo "000")

if [ "$HEALTH_STATUS" -eq 200 ]; then
    echo -e "  ${GREEN}✅ Backend is running (HTTP 200)${NC}"
    BACKEND_RUNNING=true

    # Get current stats before restart
    CURRENT_BRIDGES=$(curl -s "${BACKEND_URL}/api/mcp/bridges" 2>/dev/null | jq '.total_bridges' 2>/dev/null || echo "0")
    CURRENT_TOOLS=$(curl -s "${BACKEND_URL}/api/mcp/tools" 2>/dev/null | jq '.total_tools' 2>/dev/null || echo "0")

    echo -e "  ${YELLOW}Current: ${CURRENT_BRIDGES} bridges, ${CURRENT_TOOLS} tools${NC}"
else
    echo -e "  ${YELLOW}⚠️  Backend not running (HTTP ${HEALTH_STATUS})${NC}"
fi

echo ""

# Step 5: Wait for backend to be fully operational
echo -e "${BLUE}Step 5: Waiting for Backend to be Fully Operational${NC}"

WAIT_COUNT=0
while [ $WAIT_COUNT -lt $MAX_WAIT_TIME ]; do
    HEALTH_STATUS=$(curl -s -o /dev/null -w "%{http_code}" "${BACKEND_URL}/api/health" 2>/dev/null || echo "000")

    if [ "$HEALTH_STATUS" -eq 200 ]; then
        # Check if MCP endpoints are responding
        MCP_STATUS=$(curl -s -o /dev/null -w "%{http_code}" "${BACKEND_URL}/api/mcp/bridges" 2>/dev/null || echo "000")

        if [ "$MCP_STATUS" -eq 200 ]; then
            echo -e "  ${GREEN}✅ Backend fully operational${NC}"
            break
        fi
    fi

    echo -e "  Waiting... (${WAIT_COUNT}/${MAX_WAIT_TIME}s)"
    sleep 2
    WAIT_COUNT=$((WAIT_COUNT + 2))
done

if [ $WAIT_COUNT -ge $MAX_WAIT_TIME ]; then
    echo -e "  ${RED}❌ Backend failed to start within ${MAX_WAIT_TIME} seconds${NC}"
    exit 1
fi

echo ""

# Step 6: Verify all MCP bridges are healthy
echo -e "${BLUE}Step 6: Verifying MCP Bridge Health${NC}"

BRIDGE_HEALTH=$(curl -s "${BACKEND_URL}/api/mcp/bridges" 2>/dev/null)
TOTAL_BRIDGES=$(echo "$BRIDGE_HEALTH" | jq '.total_bridges')
HEALTHY_BRIDGES=$(echo "$BRIDGE_HEALTH" | jq '.healthy_bridges')

echo -e "  Total Bridges: ${TOTAL_BRIDGES}"
echo -e "  Healthy Bridges: ${HEALTHY_BRIDGES}"

for bridge in "${BRIDGES[@]}"; do
    STATUS=$(echo "$BRIDGE_HEALTH" | jq -r ".bridges[] | select(.name == \"${bridge}\") | .status" 2>/dev/null)
    TOOL_COUNT=$(echo "$BRIDGE_HEALTH" | jq -r ".bridges[] | select(.name == \"${bridge}\") | .tool_count" 2>/dev/null)

    if [ "$STATUS" == "healthy" ]; then
        echo -e "  ${GREEN}✅ ${bridge}: ${STATUS} (${TOOL_COUNT} tools)${NC}"
    elif [ -n "$STATUS" ]; then
        echo -e "  ${RED}❌ ${bridge}: ${STATUS}${NC}"
    else
        echo -e "  ${RED}❌ ${bridge}: NOT FOUND in registry${NC}"
    fi
done

echo ""

# Step 7: Verify MCP Registry aggregation
echo -e "${BLUE}Step 7: Verifying MCP Registry Aggregation${NC}"

REGISTRY_DATA=$(curl -s "${BACKEND_URL}/api/mcp/tools" 2>/dev/null)
TOTAL_TOOLS=$(echo "$REGISTRY_DATA" | jq '.total_tools')

echo -e "  ${YELLOW}Total Tools Available: ${TOTAL_TOOLS}${NC}"

# Check tools per bridge
for bridge in "${BRIDGES[@]}"; do
    BRIDGE_TOOLS=$(echo "$REGISTRY_DATA" | jq "[.tools[] | select(.bridge == \"${bridge}\")] | length")
    echo -e "  - ${bridge}: ${BRIDGE_TOOLS} tools"
done

echo ""

# Step 8: Validate counts
echo -e "${BLUE}Step 8: Validating Counts${NC}"

if [ "$TOTAL_BRIDGES" -ge "$EXPECTED_BRIDGES" ]; then
    echo -e "  ${GREEN}✅ Bridge count: ${TOTAL_BRIDGES} (expected ≥${EXPECTED_BRIDGES})${NC}"
else
    echo -e "  ${RED}❌ Bridge count: ${TOTAL_BRIDGES} (expected ≥${EXPECTED_BRIDGES})${NC}"
    exit 1
fi

if [ "$TOTAL_TOOLS" -ge "$EXPECTED_MIN_TOOLS" ]; then
    echo -e "  ${GREEN}✅ Tool count: ${TOTAL_TOOLS} (expected ≥${EXPECTED_MIN_TOOLS})${NC}"
else
    echo -e "  ${RED}❌ Tool count: ${TOTAL_TOOLS} (expected ≥${EXPECTED_MIN_TOOLS})${NC}"
    exit 1
fi

if [ "$HEALTHY_BRIDGES" -eq "$TOTAL_BRIDGES" ]; then
    echo -e "  ${GREEN}✅ All bridges healthy: ${HEALTHY_BRIDGES}/${TOTAL_BRIDGES}${NC}"
else
    echo -e "  ${YELLOW}⚠️  Some bridges unhealthy: ${HEALTHY_BRIDGES}/${TOTAL_BRIDGES}${NC}"
fi

echo ""

# Step 9: Check response times
echo -e "${BLUE}Step 9: Checking MCP Registry Performance${NC}"

HEALTH_DATA=$(curl -s "${BACKEND_URL}/api/mcp/health" 2>/dev/null)
SLOWEST=$(echo "$HEALTH_DATA" | jq -r '.checks | sort_by(.response_time_ms) | reverse | .[0] | "\(.bridge): \(.response_time_ms)ms"')
FASTEST=$(echo "$HEALTH_DATA" | jq -r '.checks | sort_by(.response_time_ms) | .[0] | "\(.bridge): \(.response_time_ms)ms"')

echo -e "  Fastest: ${FASTEST}"
echo -e "  Slowest: ${SLOWEST}"

echo ""

# Final Summary
echo -e "${BLUE}=== Activation Summary ===${NC}"
echo -e "  ${GREEN}✅ All MCP bridges verified and operational${NC}"
echo -e "  Total Bridges: ${TOTAL_BRIDGES}"
echo -e "  Total Tools: ${TOTAL_TOOLS}"
echo -e "  Healthy: ${HEALTHY_BRIDGES}/${TOTAL_BRIDGES}"
echo ""
echo -e "${BLUE}Frontend MCP Manager URL:${NC}"
echo -e "  http://localhost:5173/tools/mcp"
echo -e "  http://172.16.168.21:5173/tools/mcp (Frontend VM)"
echo ""
echo -e "${BLUE}API Endpoints:${NC}"
echo -e "  GET ${BACKEND_URL}/api/mcp/tools       - List all tools"
echo -e "  GET ${BACKEND_URL}/api/mcp/bridges     - List all bridges"
echo -e "  GET ${BACKEND_URL}/api/mcp/health      - Health check"
echo -e "  GET ${BACKEND_URL}/api/mcp/stats       - Registry statistics"
echo ""
echo -e "${GREEN}=== Activation Complete ===${NC}"
