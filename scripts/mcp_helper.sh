#!/bin/bash
# MCP Helper Script for AutoBot Development

# Function to call MCP server and parse JSON response
mcp_call() {
    local server=$1
    local tool=$2
    local args=$3
    
    local request='{"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "'$tool'", "arguments": '$args'}}'
    
    # Execute and filter out server startup message
    echo "$request" | $server 2>&1 | grep '^{' | jq -r '.result.content[0].text' 2>/dev/null || echo "Error calling MCP"
}

# Shortcuts for common operations
case "$1" in
    "project-health")
        mcp_call "node .mcp/autobot-mcp-server.js" "autobot_analyze_project" '{"includeStats": true}' | jq '.'
        ;;
    
    "frontend-errors")
        mcp_call "node .mcp/autobot-mcp-server.js" "autobot_debug_frontend" '{"action": "console-errors", "timeframe": "10m"}' | jq '.'
        ;;
    
    "backend-health")
        mcp_call "node .mcp/autobot-mcp-server.js" "autobot_debug_backend" '{"action": "api-health"}' | jq '.'
        ;;
    
    "api-performance")
        mcp_call "node .mcp/autobot-mcp-server.js" "autobot_debug_api_calls" '{"timeframe": "1h", "includePerformance": true}' | jq '.'
        ;;
    
    "websocket-status")
        mcp_call "node .mcp/autobot-mcp-server.js" "autobot_debug_websockets" '{"action": "connections"}' | jq '.'
        ;;
    
    "recent-errors")
        mcp_call "npx -y mcp-sqlite data/autobot.db" "query" '{"sql": "SELECT * FROM development_log WHERE log_level IN (\"ERROR\", \"CRITICAL\") ORDER BY timestamp DESC LIMIT 10"}' | jq '.'
        ;;
    
    "dev-progress")
        mcp_call "npx -y mcp-sqlite data/autobot.db" "query" '{"sql": "SELECT project_id, COUNT(*) as entries, MAX(timestamp) as last_update FROM development_log GROUP BY project_id"}' | jq '.'
        ;;
    
    "full-check")
        echo "🔍 AutoBot Full System Check"
        echo "=========================="
        
        echo -e "\n📊 Project Structure:"
        mcp_call "node .mcp/autobot-mcp-server.js" "autobot_analyze_project" '{}' | jq -r '.structure'
        
        echo -e "\n🏥 Backend Health:"
        mcp_call "node .mcp/autobot-mcp-server.js" "autobot_debug_backend" '{"action": "api-health"}' | jq -r '.status'
        
        echo -e "\n🎨 Frontend Status:"
        mcp_call "node .mcp/autobot-mcp-server.js" "autobot_debug_frontend" '{"action": "console-errors", "timeframe": "5m"}' | jq -r '.errorCount'
        
        echo -e "\n🔌 WebSocket Connections:"
        mcp_call "node .mcp/autobot-mcp-server.js" "autobot_debug_websockets" '{"action": "connections"}' | jq -r '.activeConnections'
        
        echo -e "\n📈 Recent Activity:"
        mcp_call "npx -y mcp-sqlite data/autobot.db" "query" '{"sql": "SELECT COUNT(*) as total_logs FROM development_log"}' | jq '.'
        ;;
    
    *)
        echo "AutoBot MCP Helper"
        echo "=================="
        echo ""
        echo "Usage: $0 <command>"
        echo ""
        echo "Commands:"
        echo "  project-health    - Analyze project structure and health"
        echo "  frontend-errors   - Check frontend console errors"
        echo "  backend-health    - Check backend API health"
        echo "  api-performance   - Analyze API call performance"
        echo "  websocket-status  - Check WebSocket connections"
        echo "  recent-errors     - Show recent error logs"
        echo "  dev-progress      - Show development progress"
        echo "  full-check        - Run complete system check"
        echo ""
        echo "Example: $0 frontend-errors"
        ;;
esac

# Make executable
chmod +x "$0"