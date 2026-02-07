#!/bin/bash
# AutoBot AI Stack - Stop Script
# Manual intervention script for stopping the AI stack service

set -e

SERVICE_NAME="autobot-ai-stack"

echo "Stopping AutoBot AI Stack..."

if ! systemctl is-active --quiet "${SERVICE_NAME}"; then
    echo "AI Stack is not running"
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

echo "AutoBot AI Stack stopped"
