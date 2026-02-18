#!/bin/bash
# AutoBot User Backend - Start Script
# Manual intervention script for starting the backend service

set -e

SERVICE_NAME="autobot-user-backend"
HEALTH_PORT=8001

echo "Starting ${SERVICE_NAME}..."

if systemctl is-active --quiet "${SERVICE_NAME}"; then
    echo "${SERVICE_NAME} is already running"
    exit 0
fi

sudo systemctl start "${SERVICE_NAME}"

# Wait for service to be ready
for i in {1..15}; do
    if curl -s "http://127.0.0.1:${HEALTH_PORT}/api/health" > /dev/null 2>&1; then
        echo "${SERVICE_NAME} started successfully"
        exit 0
    fi
    sleep 1
done

echo "Warning: ${SERVICE_NAME} started but health check not responding"
exit 1
