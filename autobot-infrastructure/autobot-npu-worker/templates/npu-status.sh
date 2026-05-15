#!/bin/bash
# AutoBot NPU Worker - Status Script
# Manual intervention script for checking the NPU worker status

SERVICE_NAME="autobot-npu-worker"
HEALTH_PORT=8081

echo "=== AutoBot NPU Worker Status ==="
echo ""

# Check systemd status
echo "Systemd Status:"
systemctl status "${SERVICE_NAME}" --no-pager 2>/dev/null | head -15 || echo "Service not found or not running"
echo ""

# Check if process is running
echo "Process Check:"
if pgrep -f "uvicorn.*npu_inference_server" > /dev/null; then
    echo "NPU Worker process is running"
    pgrep -af "uvicorn.*npu_inference_server" | head -3
else
    echo "NPU Worker process is NOT running"
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

# NPU device check
echo "NPU Device:"
if [[ -d /dev/dri ]]; then
    ls -la /dev/dri/
else
    echo "No /dev/dri found - NPU device may not be available"
fi
echo ""

# Resource usage
echo "Resource Usage:"
if pgrep -f "uvicorn.*npu_inference_server" > /dev/null; then
    ps aux | grep "[u]vicorn.*npu_inference_server" | awk '{print "  Memory: " $4 "%, CPU: " $3 "%"}'
fi
echo ""

# Recent logs
echo "Recent Logs (last 10 lines):"
sudo journalctl -u "${SERVICE_NAME}" -n 10 --no-pager 2>/dev/null || echo "No logs available"
