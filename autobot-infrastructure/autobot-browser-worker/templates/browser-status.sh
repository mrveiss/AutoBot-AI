#!/bin/bash
# AutoBot Browser Worker - Status Script
# Manual intervention script for checking the browser worker status

SERVICE_NAME="autobot-browser-worker"
HEALTH_PORT=3000

echo "=== AutoBot Browser Worker Status ==="
echo ""

# Check systemd status
echo "Systemd Status:"
systemctl status "${SERVICE_NAME}" --no-pager 2>/dev/null | head -15 || echo "Service not found or not running"
echo ""

# Check if process is running
echo "Process Check:"
if pgrep -f "uvicorn.*main:app.*${HEALTH_PORT}" > /dev/null; then
    echo "Browser Worker process is running"
    pgrep -af "uvicorn.*main:app" | head -3
else
    echo "Browser Worker process is NOT running"
fi
echo ""

# Browser process check
echo "Browser Processes:"
BROWSER_PROCS=$(pgrep -c -f "chromium" 2>/dev/null || echo "0")
echo "  Chromium processes: ${BROWSER_PROCS}"
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

# Playwright browsers
echo "Playwright Browsers:"
BROWSER_PATH="/opt/autobot/autobot-browser-worker/browsers"
if [[ -d "${BROWSER_PATH}" ]]; then
    ls -la "${BROWSER_PATH}" 2>/dev/null | head -5
else
    echo "Browsers not installed at ${BROWSER_PATH}"
fi
echo ""

# Recent logs
echo "Recent Logs (last 10 lines):"
sudo journalctl -u "${SERVICE_NAME}" -n 10 --no-pager 2>/dev/null || echo "No logs available"
