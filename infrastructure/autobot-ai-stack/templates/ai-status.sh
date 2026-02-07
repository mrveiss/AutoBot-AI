#!/bin/bash
# AutoBot AI Stack - Status Script
# Manual intervention script for checking the AI stack status

SERVICE_NAME="autobot-ai-stack"
HEALTH_PORT=8080

echo "=== AutoBot AI Stack Status ==="
echo ""

# Check systemd status
echo "Systemd Status:"
systemctl status "${SERVICE_NAME}" --no-pager 2>/dev/null | head -15 || echo "Service not found or not running"
echo ""

# Check if process is running
echo "Process Check:"
if pgrep -f "uvicorn.*main:app.*${HEALTH_PORT}" > /dev/null; then
    echo "AI Stack process is running"
    pgrep -af "uvicorn.*main:app" | head -3
else
    echo "AI Stack process is NOT running"
fi
echo ""

# Health check
echo "Health Check:"
if curl -s "http://127.0.0.1:${HEALTH_PORT}/health" 2>/dev/null; then
    echo ""
    echo "Health endpoint responding"
else
    echo "Health endpoint NOT responding"
fi
echo ""

# Check connections to dependencies
echo "Dependency Connections:"
echo -n "  Redis (172.16.168.23:6379): "
if timeout 2 bash -c "echo > /dev/tcp/172.16.168.23/6379" 2>/dev/null; then
    echo "OK"
else
    echo "UNREACHABLE"
fi
echo -n "  ChromaDB (172.16.168.23:8000): "
if timeout 2 bash -c "echo > /dev/tcp/172.16.168.23/8000" 2>/dev/null; then
    echo "OK"
else
    echo "UNREACHABLE"
fi
echo ""

# Memory usage
echo "Resource Usage:"
if pgrep -f "uvicorn.*main:app" > /dev/null; then
    ps aux | grep "[u]vicorn.*main:app" | awk '{print "  Memory: " $4 "%, CPU: " $3 "%"}'
fi
echo ""

# Recent logs
echo "Recent Logs (last 10 lines):"
sudo journalctl -u "${SERVICE_NAME}" -n 10 --no-pager 2>/dev/null || echo "No logs available"
