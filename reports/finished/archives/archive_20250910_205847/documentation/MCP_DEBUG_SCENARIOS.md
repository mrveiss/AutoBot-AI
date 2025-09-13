# 🔍 Real-World MCP Debugging Scenarios

This document provides practical examples of using MCP servers to debug common AutoBot issues.

## Scenario 1: Frontend Not Rendering Properly

### Symptoms
- Blank page or components not showing
- Console errors in browser
- API calls failing

### MCP Debug Workflow

```bash
# Step 1: Check frontend console errors
echo '{"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "autobot_debug_frontend", "arguments": {"action": "console-errors", "timeframe": "10m"}}}' | node .mcp/autobot-mcp-server.js

# Step 2: Analyze network requests
echo '{"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "autobot_debug_frontend", "arguments": {"action": "network-analysis", "timeframe": "10m"}}}' | node .mcp/autobot-mcp-server.js

# Step 3: Check component tree
echo '{"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "autobot_debug_frontend", "arguments": {"action": "component-tree"}}}' | node .mcp/autobot-mcp-server.js

# Step 4: Visual inspection with Puppeteer
echo '{"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "puppeteer_navigate", "arguments": {"url": "http://127.0.0.1:5173"}}}' | mcp-server-puppeteer
echo '{"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "puppeteer_screenshot", "arguments": {"name": "frontend-issue", "fullPage": true}}}' | mcp-server-puppeteer
```

## Scenario 2: API Endpoint Timing Out

### Symptoms
- Slow response times
- 504 Gateway Timeout errors
- Frontend freezing

### MCP Debug Workflow

```bash
# Step 1: Check API health
echo '{"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "autobot_debug_backend", "arguments": {"action": "api-health"}}}' | node .mcp/autobot-mcp-server.js

# Step 2: Analyze specific endpoint
echo '{"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "autobot_debug_api_calls", "arguments": {"endpoint": "/api/workflow/execute", "timeframe": "1h", "includeErrors": true}}}' | node .mcp/autobot-mcp-server.js

# Step 3: Check backend logs
echo '{"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "autobot_debug_backend", "arguments": {"action": "logs", "timeframe": "30m", "pattern": "timeout|error"}}}' | node .mcp/autobot-mcp-server.js

# Step 4: Memory analysis
echo '{"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "autobot_debug_backend", "arguments": {"action": "memory-usage", "includeProcesses": true}}}' | node .mcp/autobot-mcp-server.js
```

## Scenario 3: WebSocket Disconnections

### Symptoms
- Real-time updates not working
- Chat messages not sending
- Terminal commands hanging

### MCP Debug Workflow

```bash
# Step 1: Check active connections
echo '{"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "autobot_debug_websockets", "arguments": {"action": "connections"}}}' | node .mcp/autobot-mcp-server.js

# Step 2: Monitor messages
echo '{"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "autobot_debug_websockets", "arguments": {"action": "messages", "timeframe": "5m"}}}' | node .mcp/autobot-mcp-server.js

# Step 3: Check for errors
echo '{"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "autobot_debug_websockets", "arguments": {"action": "errors", "timeframe": "30m"}}}' | node .mcp/autobot-mcp-server.js

# Step 4: Performance metrics
echo '{"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "autobot_debug_websockets", "arguments": {"action": "performance"}}}' | node .mcp/autobot-mcp-server.js
```

## Scenario 4: Build or Test Failures

### Symptoms
- npm build failing
- Test suite errors
- TypeScript compilation errors

### MCP Debug Workflow

```bash
# Step 1: Check build status
echo '{"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "autobot_build_status", "arguments": {}}}' | node .mcp/autobot-mcp-server.js

# Step 2: Run specific tests
echo '{"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "autobot_run_tests", "arguments": {"pattern": "**/*.spec.js", "verbose": true}}}' | node .mcp/autobot-mcp-server.js

# Step 3: Read error files
echo '{"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "read_multiple_files", "arguments": {"paths": ["tsconfig.json", "vite.config.ts", "package.json"]}}}' | mcp-server-filesystem /home/kali/Desktop/AutoBot

# Step 4: Search for problematic imports
echo '{"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "search_files", "arguments": {"path": "autobot-vue/src", "pattern": "*.vue", "searchTerm": "import.*from.*undefined"}}}' | mcp-server-filesystem /home/kali/Desktop/AutoBot
```

## Scenario 5: Database or State Issues

### Symptoms
- Data not persisting
- Incorrect state in UI
- Chat history missing

### MCP Debug Workflow

```bash
# Step 1: Check database structure
echo '{"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "list_tables", "arguments": {}}}' | npx -y mcp-sqlite data/autobot.db

# Step 2: Query recent data
echo '{"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "query", "arguments": {"sql": "SELECT * FROM development_log ORDER BY timestamp DESC LIMIT 10"}}}' | npx -y mcp-sqlite data/autobot.db

# Step 3: Check file system data
echo '{"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "read_file", "arguments": {"path": "data/chat_history.json"}}}' | mcp-server-filesystem /home/kali/Desktop/AutoBot

# Step 4: Analyze state management
echo '{"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "autobot_debug_frontend", "arguments": {"action": "component-tree", "filter": "store"}}}' | node .mcp/autobot-mcp-server.js
```

## Scenario 6: Performance Degradation

### Symptoms
- Slow page loads
- High CPU/memory usage
- Laggy UI interactions

### MCP Debug Workflow

```bash
# Step 1: Frontend performance
echo '{"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "autobot_debug_frontend", "arguments": {"action": "performance"}}}' | node .mcp/autobot-mcp-server.js

# Step 2: Bundle analysis
echo '{"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "autobot_debug_frontend", "arguments": {"action": "bundle-analysis"}}}' | node .mcp/autobot-mcp-server.js

# Step 3: Backend memory
echo '{"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "autobot_debug_backend", "arguments": {"action": "memory-usage", "includeHeap": true}}}' | node .mcp/autobot-mcp-server.js

# Step 4: Log pattern analysis
echo '{"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "autobot_debug_logs_analysis", "arguments": {"pattern": "slow|timeout|memory", "timeframe": "1h"}}}' | node .mcp/autobot-mcp-server.js
```

## Combining MCP Tools for Complex Issues

### Example: Debugging a Complete Feature Failure

```bash
#!/bin/bash
# Comprehensive feature debug script

echo "🔍 Debugging Feature: Chat System"

# 1. Project overview
echo -e "\n📊 Project Status:"
echo '{"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "autobot_analyze_project", "arguments": {"includeStats": true}}}' | node .mcp/autobot-mcp-server.js 2>&1 | grep '^{' | jq -r '.result.content[0].text' | jq '.health.gitStatus' | head -5

# 2. Frontend analysis
echo -e "\n🎨 Frontend Health:"
echo '{"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "autobot_debug_frontend", "arguments": {"action": "console-errors"}}}' | node .mcp/autobot-mcp-server.js 2>&1 | grep '^{' | jq -r '.result.content[0].text'

# 3. Backend analysis
echo -e "\n🔧 Backend Health:"
echo '{"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "autobot_debug_backend", "arguments": {"action": "api-health"}}}' | node .mcp/autobot-mcp-server.js 2>&1 | grep '^{' | jq -r '.result.content[0].text'

# 4. WebSocket status
echo -e "\n🔌 WebSocket Status:"
echo '{"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "autobot_debug_websockets", "arguments": {"action": "connections"}}}' | node .mcp/autobot-mcp-server.js 2>&1 | grep '^{' | jq -r '.result.content[0].text'

# 5. Log to database
echo -e "\n💾 Logging Debug Session:"
echo '{"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "create_record", "arguments": {"table": "development_log", "data": {"project_id": 1, "log_entry": "Comprehensive chat system debug", "log_level": "DEBUG", "details": "{\"feature\": \"chat\", \"timestamp\": \"'$(date -u +%Y-%m-%dT%H:%M:%SZ)'\"}"}}}}' | npx -y mcp-sqlite data/autobot.db 2>/dev/null | jq -r '.result.content[0].text'
```

## Tips for Effective MCP Debugging

1. **Start Broad, Then Narrow**: Use `autobot_analyze_project` first, then focus on specific areas
2. **Combine Tools**: Use multiple MCP servers together for comprehensive analysis
3. **Track Progress**: Log debug sessions to SQLite for historical analysis
4. **Visual Validation**: Use Puppeteer for visual regression testing
5. **Pattern Recognition**: Use log analysis to identify recurring issues

## Quick Commands Cheatsheet

```bash
# Project health check
./scripts/mcp_helper.sh project-health

# Frontend debugging
./scripts/mcp_helper.sh frontend-errors

# Backend debugging
./scripts/mcp_helper.sh backend-health

# Full system check
./scripts/mcp_helper.sh full-check

# Test all MCP servers
./scripts/test_mcp_integration.sh
```

Remember: The power of MCP debugging comes from combining multiple tools to get a complete picture of the issue!