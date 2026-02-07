#!/bin/bash
# AutoBot NPU Worker - Stop Script
# Manual intervention script for stopping the NPU worker service

set -e

SERVICE_NAME="autobot-npu-worker"

echo "Stopping AutoBot NPU Worker..."

if ! systemctl is-active --quiet "${SERVICE_NAME}"; then
    echo "NPU Worker is not running"
    exit 0
fi

# Stop the service
sudo systemctl stop "${SERVICE_NAME}"

# Wait for clean stop
MAX_WAIT=30
WAITED=0
while systemctl is-active --quiet "${SERVICE_NAME}"; do
    if [[ ${WAITED} -ge ${MAX_WAIT} ]]; then
        echo "Warning: Service did not stop within ${MAX_WAIT} seconds"
        echo "Force killing..."
        sudo systemctl kill "${SERVICE_NAME}"
        break
    fi
    sleep 1
    ((WAITED++))
done

echo "AutoBot NPU Worker stopped"
