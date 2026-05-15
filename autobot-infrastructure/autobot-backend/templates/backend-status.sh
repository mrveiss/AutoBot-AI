#!/bin/bash
# AutoBot User Backend - Status Script
# Manual intervention script for checking the backend service status

SERVICE_NAME="autobot-user-backend"
HEALTH_PORT=8001

echo "=== ${SERVICE_NAME} Status ==="
echo ""

# Check systemd status
echo "Systemd Status:"
systemctl status "${SERVICE_NAME}" --no-pager 2>/dev/null || echo "Service not found or not running"
echo ""

# Check if process is running
echo "Process Check:"
if pgrep -f "uvicorn.*main:app.*${HEALTH_PORT}" > /dev/null; then
    echo "Backend process is running"
    pgrep -af "uvicorn.*main:app" | head -3
else
    echo "Backend process is NOT running"
fi
echo ""

# Health check
echo "Health Check:"
if curl -s "http://127.0.0.1:${HEALTH_PORT}/api/health" 2>/dev/null; then
    echo ""
    echo "Health endpoint responding"
else
    echo "Health endpoint NOT responding"
fi
echo ""

# Recent logs
echo "Recent Logs (last 10 lines):"
sudo journalctl -u "${SERVICE_NAME}" -n 10 --no-pager 2>/dev/null || echo "No logs available"
