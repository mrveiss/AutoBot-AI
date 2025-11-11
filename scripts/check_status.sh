#!/bin/bash

# Quick status check script for PTY collaboration testing

echo "╔════════════════════════════════════════════════════════════════╗"
echo "║          PTY Collaboration - System Status Check              ║"
echo "╚════════════════════════════════════════════════════════════════╝"
echo ""

# Check backend
echo -n "Backend (172.16.168.20:8001): "
if curl -s http://172.16.168.20:8001/api/health >/dev/null 2>&1; then
    echo -e "\033[0;32m✅ RUNNING\033[0m"
else
    echo -e "\033[0;31m❌ NOT RESPONDING\033[0m"
fi

# Check frontend
echo -n "Frontend (172.16.168.21:5173): "
if curl -s -o /dev/null -w "%{http_code}" http://172.16.168.21:5173/ 2>/dev/null | grep -q "200"; then
    echo -e "\033[0;32m✅ RUNNING\033[0m"
else
    echo -e "\033[0;31m❌ NOT RESPONDING\033[0m"
fi

# Check Redis
echo -n "Redis (172.16.168.23:6379): "
if redis-cli -h 172.16.168.23 ping 2>/dev/null | grep -q "PONG"; then
    echo -e "\033[0;32m✅ CONNECTED\033[0m"
else
    echo -e "\033[0;31m❌ NOT CONNECTED\033[0m"
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# Check active sessions
echo "Active Agent Terminal Sessions:"
SESSION_COUNT=$(curl -s http://172.16.168.20:8001/api/agent-terminal/sessions 2>/dev/null | jq '.sessions | length' 2>/dev/null)
if [ -n "$SESSION_COUNT" ]; then
    echo "  Count: $SESSION_COUNT"
    if [ "$SESSION_COUNT" -gt 0 ]; then
        echo ""
        curl -s http://172.16.168.20:8001/api/agent-terminal/sessions 2>/dev/null | jq -r '.sessions[] | "  • Session: \(.session_id)\n    Agent: \(.agent_id)\n    Conversation: \(.conversation_id // "N/A")\n    State: \(.state)\n    PTY: \(.pty_session_id // "N/A")\n"'
    fi
else
    echo "  Unable to retrieve session info"
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# Check recent errors
echo "Recent Errors (last 10):"
ERROR_COUNT=$(tail -100 /home/kali/Desktop/AutoBot/logs/backend.log 2>/dev/null | grep -c "ERROR")
if [ "$ERROR_COUNT" -eq 0 ]; then
    echo -e "  \033[0;32m✅ No recent errors\033[0m"
else
    echo -e "  \033[0;33m⚠️  $ERROR_COUNT errors found\033[0m"
    tail -100 /home/kali/Desktop/AutoBot/logs/backend.log 2>/dev/null | grep "ERROR" | tail -5 | while read line; do
        echo "    $line"
    done
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "System Ready: Open http://172.16.168.21:5173 to begin testing"
echo ""
