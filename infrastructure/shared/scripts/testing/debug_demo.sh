#\!/bin/bash
echo "🚀 AutoBot MCP Debugging Demo"
echo "============================="

# 1. Check project health
echo -e "\n📊 Project Health Check:"
echo '{"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "autobot_analyze_project", "arguments": {}}}'  < /dev/null |  \
    node .mcp/autobot-mcp-server.js 2>&1 | grep '^{' | jq -r '.result.content[0].text' | \
    jq -r '.structure.frontend | "Frontend: \(.name) v\(.version) - \(.dependencies) deps"'

# 2. Query development progress
echo -e "\n📈 Development Progress:"
echo '{"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "query", "arguments": {"sql": "SELECT p.name, COUNT(d.id) as logs, MAX(d.timestamp) as last_update FROM projects p LEFT JOIN development_log d ON p.id = d.project_id GROUP BY p.id, p.name"}}}' | \
    npx -y mcp-sqlite data/autobot.db 2>/dev/null | jq -r '.result.content[0].text' | jq -r '.[] | "\(.name): \(.logs) entries (last: \(.last_update))"'

# 3. Check for errors
echo -e "\n🔍 Recent Success Logs:"
echo '{"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "query", "arguments": {"sql": "SELECT log_entry, details FROM development_log WHERE log_level = \"SUCCESS\" ORDER BY timestamp DESC LIMIT 3"}}}' | \
    npx -y mcp-sqlite data/autobot.db 2>/dev/null | jq -r '.result.content[0].text' | jq -r '.[] | "✓ \(.log_entry)"'

# 4. File system check
echo -e "\n📁 MCP Configuration Files:"
echo '{"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "list_directory", "arguments": {"path": "/home/kali/Desktop/AutoBot/.mcp"}}}' | \
    mcp-server-filesystem /home/kali/Desktop/AutoBot 2>/dev/null | jq -r '.result.content[0].text' | jq -r '.entries[] | select(.type == "file") | "- \(.name)"' | head -5

echo -e "\n✅ MCP Integration Demo Complete\!"
