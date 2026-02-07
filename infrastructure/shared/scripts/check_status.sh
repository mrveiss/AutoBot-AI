#!/bin/bash
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
#
# Quick status check script for PTY collaboration testing

# =============================================================================
# SSOT Configuration - Issue #694
# =============================================================================
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib/ssot-config.sh" 2>/dev/null || source "$SCRIPT_DIR/../lib/ssot-config.sh" 2>/dev/null || {
    # Fallback if lib not found
    PROJECT_ROOT="${PROJECT_ROOT:-/home/kali/Desktop/AutoBot}"
    [ -f "$PROJECT_ROOT/.env" ] && { set -a; source "$PROJECT_ROOT/.env"; set +a; }
}

# Assign SSOT variables with fallbacks
BACKEND_HOST="${AUTOBOT_BACKEND_HOST:-172.16.168.20}"
BACKEND_PORT="${AUTOBOT_BACKEND_PORT:-8001}"
FRONTEND_HOST="${AUTOBOT_FRONTEND_HOST:-172.16.168.21}"
FRONTEND_PORT="${AUTOBOT_FRONTEND_PORT:-5173}"
REDIS_HOST="${AUTOBOT_REDIS_HOST:-172.16.168.23}"

echo ""
echo "PTY Collaboration - System Status Check"
echo "========================================"
echo ""

# Check backend
echo -n "Backend ($BACKEND_HOST:$BACKEND_PORT): "
if curl -s "http://$BACKEND_HOST:$BACKEND_PORT/api/health" >/dev/null 2>&1; then
    echo -e "\033[0;32mRUNNING\033[0m"
else
    echo -e "\033[0;31mNOT RESPONDING\033[0m"
fi

# Check frontend
echo -n "Frontend ($FRONTEND_HOST:$FRONTEND_PORT): "
if curl -s -o /dev/null -w "%{http_code}" "http://$FRONTEND_HOST:$FRONTEND_PORT/" 2>/dev/null | grep -q "200"; then
    echo -e "\033[0;32mRUNNING\033[0m"
else
    echo -e "\033[0;31mNOT RESPONDING\033[0m"
fi

# Check Redis
echo -n "Redis ($REDIS_HOST:6379): "
if redis-cli -h "$REDIS_HOST" ping 2>/dev/null | grep -q "PONG"; then
    echo -e "\033[0;32mCONNECTED\033[0m"
else
    echo -e "\033[0;31mNOT CONNECTED\033[0m"
fi

echo ""
echo "----------------------------------------"
echo ""

# Check active sessions
echo "Active Agent Terminal Sessions:"
SESSION_COUNT=$(curl -s "http://$BACKEND_HOST:$BACKEND_PORT/api/agent-terminal/sessions" 2>/dev/null | jq '.sessions | length' 2>/dev/null)
if [ -n "$SESSION_COUNT" ]; then
    echo "  Count: $SESSION_COUNT"
    if [ "$SESSION_COUNT" -gt 0 ]; then
        echo ""
        curl -s "http://$BACKEND_HOST:$BACKEND_PORT/api/agent-terminal/sessions" 2>/dev/null | jq -r '.sessions[] | "  Session: \(.session_id)\n    Agent: \(.agent_id)\n    Conversation: \(.conversation_id // "N/A")\n    State: \(.state)\n    PTY: \(.pty_session_id // "N/A")\n"'
    fi
else
    echo "  Unable to retrieve session info"
fi

echo ""
echo "----------------------------------------"
echo ""

# Check recent errors
echo "Recent Errors (last 10):"
LOG_FILE="${PROJECT_ROOT:-/home/kali/Desktop/AutoBot}/logs/backend.log"
ERROR_COUNT=$(tail -100 "$LOG_FILE" 2>/dev/null | grep -c "ERROR")
if [ "$ERROR_COUNT" -eq 0 ]; then
    echo -e "  \033[0;32mNo recent errors\033[0m"
else
    echo -e "  \033[0;33m$ERROR_COUNT errors found\033[0m"
    tail -100 "$LOG_FILE" 2>/dev/null | grep "ERROR" | tail -5 | while read -r line; do
        echo "    $line"
    done
fi

echo ""
echo "----------------------------------------"
echo ""
echo "System Ready: Open http://$FRONTEND_HOST:$FRONTEND_PORT to begin testing"
echo ""
