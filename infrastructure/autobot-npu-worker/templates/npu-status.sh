#!/bin/bash
# AutoBot NPU Worker - Status Script
# Manual intervention script for checking the NPU worker status

SERVICE_NAME="autobot-npu-worker"
CONTAINER_NAME="autobot-npu-worker"
HEALTH_PORT=8081

echo "=== AutoBot NPU Worker Status ==="
echo ""

# Check systemd status
echo "Systemd Status:"
systemctl status "${SERVICE_NAME}" --no-pager 2>/dev/null | head -10 || echo "Service not found or not installed"
echo ""

# Check container status
echo "Container Status:"
if docker ps --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
    echo "Container is RUNNING"
    docker ps --filter "name=${CONTAINER_NAME}" --format "table {{.Status}}\t{{.Ports}}"
else
    echo "Container is NOT running"
    # Check if stopped
    if docker ps -a --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
        echo "Container exists but stopped:"
        docker ps -a --filter "name=${CONTAINER_NAME}" --format "table {{.Status}}"
    fi
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

# Recent logs
echo "Recent Container Logs (last 10 lines):"
docker logs --tail 10 "${CONTAINER_NAME}" 2>&1 || echo "No container logs available"
