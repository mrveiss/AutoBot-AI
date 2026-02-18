#!/bin/bash
# AutoBot SLM Backend - Start Script
# Manual intervention script for starting the backend service

set -e

SERVICE_NAME="autobot-slm-backend"

echo "Starting ${SERVICE_NAME}..."

if systemctl is-active --quiet "${SERVICE_NAME}"; then
    echo "${SERVICE_NAME} is already running"
    exit 0
fi

sudo systemctl start "${SERVICE_NAME}"

# Wait for service to be ready
for i in {1..10}; do
    if curl -s http://127.0.0.1:8000/api/health > /dev/null 2>&1; then
        echo "${SERVICE_NAME} started successfully"
        exit 0
    fi
    sleep 1
done

echo "Warning: ${SERVICE_NAME} started but health check not responding"
exit 1
