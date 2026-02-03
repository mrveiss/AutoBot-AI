#!/bin/bash
# AutoBot Chat System Debug Script
# Demonstrates comprehensive MCP debugging workflow

echo "🔍 AutoBot Chat System Debugging Session"
echo "========================================"
echo "Scenario: Users report chat messages not sending properly"
echo ""

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Helper function to parse MCP responses
parse_mcp_response() {
    grep '^{' | jq -r '.result.content[0].text' 2>/dev/null || echo "{}"
}

# Step 1: Initial System Check
echo -e "${BLUE}📊 Step 1: Initial System Analysis${NC}"
echo "Checking overall project health..."

PROJECT_HEALTH=$(echo '{"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "autobot_analyze_project", "arguments": {"includeStats": true}}}' | \
    node .mcp/autobot-mcp-server.js 2>&1 | parse_mcp_response)

if [ ! -z "$PROJECT_HEALTH" ]; then
    FRONTEND_VERSION=$(echo "$PROJECT_HEALTH" | jq -r '.structure.frontend.version // "unknown"')
    BACKEND_FILES=$(echo "$PROJECT_HEALTH" | jq -r '.structure.backend.totalFiles // 0')
    echo -e "  Frontend Version: ${GREEN}$FRONTEND_VERSION${NC}"
    echo -e "  Backend Files: ${GREEN}$BACKEND_FILES${NC}"
fi

# Step 2: Frontend Console Errors
echo -e "\n${BLUE}🎨 Step 2: Frontend Error Analysis${NC}"
echo "Checking for console errors..."

FRONTEND_ERRORS=$(echo '{"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "autobot_debug_frontend", "arguments": {"action": "console-errors", "timeframe": "30m"}}}' | \
    node .mcp/autobot-mcp-server.js 2>&1 | parse_mcp_response)

ERROR_COUNT=$(echo "$FRONTEND_ERRORS" | jq -r '.errorCount // 0')
if [ "$ERROR_COUNT" -gt 0 ]; then
    echo -e "  ${RED}⚠️  Found $ERROR_COUNT console errors${NC}"
    echo "$FRONTEND_ERRORS" | jq -r '.errors[]? | "    - \(.message // .)"' 2>/dev/null | head -5
else
    echo -e "  ${GREEN}✓ No console errors detected${NC}"
fi

# Step 3: API Endpoint Analysis
echo -e "\n${BLUE}🔧 Step 3: API Endpoint Analysis${NC}"
echo "Analyzing chat API performance..."

API_ANALYSIS=$(echo '{"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "autobot_debug_api_calls", "arguments": {"endpoint": "/api/chat", "timeframe": "1h", "includeErrors": true}}}' | \
    node .mcp/autobot-mcp-server.js 2>&1 | parse_mcp_response)

API_CALLS=$(echo "$API_ANALYSIS" | jq -r '.totalCalls // 0')
API_ERRORS=$(echo "$API_ANALYSIS" | jq -r '.errorCount // 0')
AVG_RESPONSE=$(echo "$API_ANALYSIS" | jq -r '.avgResponseTime // "N/A"')

echo -e "  Total API Calls: $API_CALLS"
echo -e "  Failed Calls: ${RED}$API_ERRORS${NC}"
echo -e "  Avg Response Time: $AVG_RESPONSE ms"

# Step 4: WebSocket Connection Check
echo -e "\n${BLUE}🔌 Step 4: WebSocket Connection Analysis${NC}"
echo "Checking real-time connections..."

WS_STATUS=$(echo '{"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "autobot_debug_websockets", "arguments": {"action": "connections"}}}' | \
    node .mcp/autobot-mcp-server.js 2>&1 | parse_mcp_response)

ACTIVE_CONNECTIONS=$(echo "$WS_STATUS" | jq -r '.activeConnections // 0')
CONNECTION_ERRORS=$(echo "$WS_STATUS" | jq -r '.recentErrors // 0')

if [ "$ACTIVE_CONNECTIONS" -eq 0 ]; then
    echo -e "  ${RED}❌ No active WebSocket connections${NC}"
    echo "  This explains why messages aren't sending!"
else
    echo -e "  ${GREEN}✓ Active connections: $ACTIVE_CONNECTIONS${NC}"
fi

# Step 5: Backend Health Check
echo -e "\n${BLUE}🏥 Step 5: Backend Service Health${NC}"
echo "Checking backend API status..."

BACKEND_HEALTH=$(echo '{"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "autobot_debug_backend", "arguments": {"action": "api-health"}}}' | \
    node .mcp/autobot-mcp-server.js 2>&1 | parse_mcp_response)

API_STATUS=$(echo "$BACKEND_HEALTH" | jq -r '.healthy // false')
if [ "$API_STATUS" = "true" ]; then
    echo -e "  ${GREEN}✓ Backend API is healthy${NC}"
else
    echo -e "  ${RED}❌ Backend API issues detected${NC}"
    echo "$BACKEND_HEALTH" | jq -r '.issues[]? // empty' | head -3
fi

# Step 6: Check Chat-Related Files
echo -e "\n${BLUE}📁 Step 6: File System Analysis${NC}"
echo "Examining chat implementation files..."

# Check if chat files exist
CHAT_FILES=$(echo '{"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "search_files", "arguments": {"path": "/home/kali/Desktop/AutoBot", "pattern": "**/[Cc]hat*.{js,vue,py}", "excludePatterns": ["node_modules/**", "venv/**"]}}}' | \
    mcp-server-filesystem /home/kali/Desktop/AutoBot 2>&1 | parse_mcp_response)

FILE_COUNT=$(echo "$CHAT_FILES" | jq -r '.files | length // 0' 2>/dev/null)
echo -e "  Found ${GREEN}$FILE_COUNT${NC} chat-related files"

# Step 7: Database Logging
echo -e "\n${BLUE}💾 Step 7: Logging Debug Session${NC}"
echo "Recording findings to database..."

DETAILS=$(cat <<EOF
{
  "scenario": "Chat messages not sending",
  "findings": {
    "console_errors": $ERROR_COUNT,
    "api_calls": $API_CALLS,
    "api_errors": $API_ERRORS,
    "websocket_connections": $ACTIVE_CONNECTIONS,
    "backend_healthy": $API_STATUS
  },
  "timestamp": "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
}
EOF
)

LOG_RESULT=$(echo "{\"jsonrpc\": \"2.0\", \"id\": 1, \"method\": \"tools/call\", \"params\": {\"name\": \"create_record\", \"arguments\": {\"table\": \"development_log\", \"data\": {\"project_id\": 1, \"log_entry\": \"Chat system debug session\", \"log_level\": \"DEBUG\", \"details\": $(echo "$DETAILS" | jq -c .)}}}}" | \
    npx -y mcp-sqlite data/autobot.db 2>&1 | parse_mcp_response)

if echo "$LOG_RESULT" | grep -q "success"; then
    echo -e "  ${GREEN}✓ Debug session logged to database${NC}"
fi

# Step 8: Recommendations
echo -e "\n${YELLOW}💡 Recommendations Based on Analysis:${NC}"

if [ "$ACTIVE_CONNECTIONS" -eq 0 ]; then
    echo "  1. WebSocket connection is down - restart backend services"
    echo "     Run: ./run_agent.sh"
fi

if [ "$ERROR_COUNT" -gt 0 ]; then
    echo "  2. Fix frontend console errors in:"
    echo "$FRONTEND_ERRORS" | jq -r '.topFiles[]? // empty' | head -3 | sed 's/^/     - /'
fi

if [ "$API_ERRORS" -gt 0 ]; then
    echo "  3. Investigate API failures:"
    echo "     - Check backend logs for detailed error messages"
    echo "     - Verify API endpoint configuration"
fi

if [ "$API_STATUS" != "true" ]; then
    echo "  4. Backend health issues detected:"
    echo "     - Check Docker container status"
    echo "     - Review backend configuration"
fi

# Step 9: Visual Testing (Optional)
echo -e "\n${BLUE}📸 Step 9: Visual Inspection${NC}"
read -p "Would you like to capture a screenshot of the current state? (y/n) " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    echo "Capturing frontend screenshot..."
    
    # Navigate to frontend
    NAV_RESULT=$(echo '{"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "puppeteer_navigate", "arguments": {"url": "http://127.0.0.1:5173"}}}' | \
        mcp-server-puppeteer 2>&1 | parse_mcp_response)
    
    # Take screenshot
    SCREENSHOT=$(echo '{"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "puppeteer_screenshot", "arguments": {"name": "chat-debug-'$(date +%s)'", "fullPage": true}}}' | \
        mcp-server-puppeteer 2>&1 | parse_mcp_response)
    
    if echo "$SCREENSHOT" | grep -q "saved"; then
        echo -e "  ${GREEN}✓ Screenshot captured successfully${NC}"
    fi
fi

# Summary
echo -e "\n${GREEN}📊 Debug Summary:${NC}"
echo "=================="
echo "- Frontend Errors: $ERROR_COUNT"
echo "- API Calls: $API_CALLS (Errors: $API_ERRORS)"
echo "- WebSocket Status: $ACTIVE_CONNECTIONS connections"
echo "- Backend Health: $([ "$API_STATUS" = "true" ] && echo "Healthy" || echo "Issues Detected")"
echo "- Debug session logged to database"

echo -e "\n${GREEN}✅ Debug session complete!${NC}"
echo "Use the recommendations above to fix the identified issues."

# Make executable
chmod +x "$0"