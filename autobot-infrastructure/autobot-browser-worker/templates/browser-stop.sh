#!/bin/bash
# AutoBot Browser Worker - Stop Script
# Manual intervention script for stopping the browser worker service

set -e

SERVICE_NAME="autobot-browser-worker"

echo "Stopping AutoBot Browser Worker..."

if ! systemctl is-active --quiet "${SERVICE_NAME}"; then
    echo "Browser Worker is not running"
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

# Clean up any orphaned browser processes
pkill -f "chromium" 2>/dev/null || true
pkill -f "playwright" 2>/dev/null || true

echo "AutoBot Browser Worker stopped"
