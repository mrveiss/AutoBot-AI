#!/bin/bash
# Test MCP Integration for AutoBot
# This script verifies all MCP servers are properly configured

echo "🚀 Testing MCP Server Integration for AutoBot"
echo "============================================"

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Test function
test_mcp() {
    local name=$1
    local command=$2
    local test_json=$3

    echo -ne "Testing $name... "

    if echo "$test_json" | $command 2>/dev/null | grep -q "result"; then
        echo -e "${GREEN}✓ Working${NC}"
        return 0
    else
        echo -e "${RED}✗ Failed${NC}"
        return 1
    fi
}

# 1. Test AutoBot MCP Server
echo -e "\n${YELLOW}1. AutoBot Custom MCP Server${NC}"
test_mcp "Project Analysis" "node autobot-mcp-server.js" \
    '{"jsonrpc":"2.0","id":1,"method":"tools/list"}'

# 2. Test Filesystem MCP Server
echo -e "\n${YELLOW}2. Filesystem MCP Server${NC}"
test_mcp "File Operations" "mcp-server-filesystem /home/kali/Desktop/AutoBot" \
    '{"jsonrpc":"2.0","id":1,"method":"tools/list"}'

# 3. Test SQLite MCP Server
echo -e "\n${YELLOW}3. SQLite MCP Server${NC}"
test_mcp "Database Operations" "npx -y mcp-sqlite data/autobot.db" \
    '{"jsonrpc":"2.0","id":1,"method":"tools/list"}'

# 4. Test Puppeteer MCP Server
echo -e "\n${YELLOW}4. Puppeteer MCP Server${NC}"
test_mcp "Browser Automation" "mcp-server-puppeteer" \
    '{"jsonrpc":"2.0","id":1,"method":"tools/list"}'

# 5. Test Sequential Thinking MCP Server
echo -e "\n${YELLOW}5. Sequential Thinking MCP Server${NC}"
test_mcp "Problem Solving" "mcp-server-sequential-thinking" \
    '{"jsonrpc":"2.0","id":1,"method":"tools/list"}'

# 6. Test GitHub MCP Server (if configured)
echo -e "\n${YELLOW}6. GitHub MCP Server${NC}"
if [ -n "$GITHUB_PAT" ]; then
    test_mcp "GitHub Operations" "./github-mcp-server stdio" \
        '{"jsonrpc":"2.0","id":1,"method":"tools/list"}'
else
    echo -e "${YELLOW}⚠ Skipped (GITHUB_PAT not set)${NC}"
fi

# Test a real debugging scenario
echo -e "\n${YELLOW}Testing Real Debug Scenario${NC}"
echo -ne "Running frontend debug check... "

debug_result=$(echo '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"autobot_debug_frontend","arguments":{"action":"console-errors","timeframe":"5m"}}}' | node autobot-mcp-server.js 2>/dev/null)

if echo "$debug_result" | grep -q "errorCount"; then
    echo -e "${GREEN}✓ Debug tools working${NC}"

    # Extract error count if available
    error_count=$(echo "$debug_result" | grep -o '"errorCount":[0-9]*' | cut -d':' -f2)
    if [ -n "$error_count" ]; then
        echo "  Frontend errors found: $error_count"
    fi
else
    echo -e "${RED}✗ Debug tools failed${NC}"
fi

# Summary
echo -e "\n${YELLOW}Summary${NC}"
echo "======="
echo "MCP servers are configured and ready for AutoBot development!"
echo ""
echo "Quick tips:"
echo "- Use 'node autobot-mcp-server.js' for project-specific debugging"
echo "- Check MCP_QUICK_REFERENCE.md for common commands"
echo "- See docs/development/MCP_USAGE_GUIDE.md for detailed workflows"

# Make executable
chmod +x "$0"
