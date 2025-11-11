#!/bin/bash

# Real-time monitoring script for PTY collaboration testing
# This script monitors backend logs for PTY execution, approvals, and errors

echo "╔════════════════════════════════════════════════════════════════╗"
echo "║     PTY Collaboration Mode - Real-Time Monitoring             ║"
echo "╚════════════════════════════════════════════════════════════════╝"
echo ""
echo "Monitoring backend logs for:"
echo "  • PTY command execution"
echo "  • Approval requests and responses"
echo "  • Session creation/restoration"
echo "  • Errors and warnings"
echo ""
echo "Press Ctrl+C to stop monitoring"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# Follow logs with color-coded output
tail -f /home/kali/Desktop/AutoBot/logs/backend.log | grep --line-buffered -E "(PTY_EXEC|agent_terminal|approval|Session|ERROR|WARNING)" | while read line; do
    if echo "$line" | grep -q "ERROR"; then
        echo -e "\033[0;31m[ERROR]\033[0m $line"
    elif echo "$line" | grep -q "WARNING"; then
        echo -e "\033[0;33m[WARN]\033[0m $line"
    elif echo "$line" | grep -q "PTY_EXEC"; then
        echo -e "\033[0;32m[PTY]\033[0m $line"
    elif echo "$line" | grep -q "approval"; then
        echo -e "\033[0;36m[APPROVAL]\033[0m $line"
    elif echo "$line" | grep -q "Session"; then
        echo -e "\033[0;35m[SESSION]\033[0m $line"
    else
        echo "$line"
    fi
done
