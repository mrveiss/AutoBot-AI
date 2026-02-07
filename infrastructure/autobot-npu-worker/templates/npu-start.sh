#!/bin/bash
# AutoBot NPU Worker - Start Script
# Manual intervention script for starting the NPU worker container

set -e

SERVICE_NAME="autobot-npu-worker"
CONTAINER_NAME="autobot-npu-worker"
HEALTH_PORT=8081

echo "Starting AutoBot NPU Worker..."

# Check if Docker is running
if ! systemctl is-active --quiet docker; then
    echo "Error: Docker is not running"
    echo "Start Docker first: sudo systemctl start docker"
    exit 1
fi

# Check if container is already running
if docker ps --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
    echo "NPU Worker container is already running"
    exit 0
fi

# Remove any stopped container with same name
docker rm -f "${CONTAINER_NAME}" 2>/dev/null || true

# Start via systemd if service is installed
if systemctl list-unit-files "${SERVICE_NAME}.service" &>/dev/null; then
    echo "Starting via systemd..."
    sudo systemctl start "${SERVICE_NAME}"
else
    echo "Warning: Systemd service not installed, starting container directly..."
    docker run -d --rm \
        --name "${CONTAINER_NAME}" \
        --device /dev/dri:/dev/dri \
        --group-add video \
        -p ${HEALTH_PORT}:8081 \
        -v /opt/autobot/autobot-npu-worker/models:/app/models \
        -v /opt/autobot/autobot-npu-worker/cache:/app/cache \
        -e NPU_DEVICE=AUTO \
        -e NPU_LOG_LEVEL=INFO \
        -e REDIS_HOST=172.16.168.23 \
        -e REDIS_PORT=6379 \
        autobot-npu-worker:latest
fi

# Wait for container to be healthy
echo "Waiting for NPU Worker to be ready..."
sleep 5

# Verify it's responding
if curl -s "http://127.0.0.1:${HEALTH_PORT}/health" > /dev/null 2>&1; then
    echo "AutoBot NPU Worker started successfully"
    exit 0
fi

echo "Warning: NPU Worker started but health check not responding"
echo "Container logs:"
docker logs --tail 20 "${CONTAINER_NAME}" 2>&1 || true
exit 1
