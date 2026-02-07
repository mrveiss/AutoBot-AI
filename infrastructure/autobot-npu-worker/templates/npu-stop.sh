#!/bin/bash
# AutoBot NPU Worker - Stop Script
# Manual intervention script for stopping the NPU worker container

set -e

SERVICE_NAME="autobot-npu-worker"
CONTAINER_NAME="autobot-npu-worker"

echo "Stopping AutoBot NPU Worker..."

# Try systemd first
if systemctl list-unit-files "${SERVICE_NAME}.service" &>/dev/null; then
    if systemctl is-active --quiet "${SERVICE_NAME}"; then
        echo "Stopping via systemd..."
        sudo systemctl stop "${SERVICE_NAME}"
    fi
fi

# Also stop container directly if running
if docker ps --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
    echo "Stopping container..."
    docker stop "${CONTAINER_NAME}" 2>/dev/null || true
fi

# Clean up any lingering container
docker rm -f "${CONTAINER_NAME}" 2>/dev/null || true

# Wait for clean stop
MAX_WAIT=30
WAITED=0
while docker ps --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; do
    if [[ ${WAITED} -ge ${MAX_WAIT} ]]; then
        echo "Warning: Container did not stop within ${MAX_WAIT} seconds"
        echo "Force killing..."
        docker kill "${CONTAINER_NAME}" 2>/dev/null || true
        break
    fi
    sleep 1
    ((WAITED++))
done

echo "AutoBot NPU Worker stopped"
