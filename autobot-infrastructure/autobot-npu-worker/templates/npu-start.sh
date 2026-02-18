#!/bin/bash
# AutoBot NPU Worker - Start Script
# Manual intervention script for starting the NPU worker service

set -e

SERVICE_NAME="autobot-npu-worker"
HEALTH_PORT=8081

echo "Starting AutoBot NPU Worker..."

# Check if service file exists
if ! systemctl list-unit-files "${SERVICE_NAME}.service" &>/dev/null; then
    echo "Error: Systemd service not installed"
    echo "Install with: sudo cp autobot-npu-worker.service /etc/systemd/system/"
    exit 1
fi

# Check if already running
if systemctl is-active --quiet "${SERVICE_NAME}"; then
    echo "NPU Worker is already running"
    exit 0
fi

# Ensure data directories exist
sudo -u autobot mkdir -p /opt/autobot/autobot-npu-worker/{models,cache,logs}

# Start the service
echo "Starting service..."
sudo systemctl start "${SERVICE_NAME}"

# Wait for service to be ready
echo "Waiting for NPU Worker to be ready..."
sleep 5

# Verify it's responding
MAX_WAIT=30
WAITED=0
while [[ ${WAITED} -lt ${MAX_WAIT} ]]; do
    if curl -s "http://127.0.0.1:${HEALTH_PORT}/health" > /dev/null 2>&1; then
        echo "AutoBot NPU Worker started successfully"
        exit 0
    fi
    sleep 1
    ((WAITED++))
done

echo "Warning: NPU Worker started but health check not responding"
echo "Check logs: sudo journalctl -u ${SERVICE_NAME} -n 50"
exit 1
