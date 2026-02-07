#!/bin/bash
# AutoBot User Backend - Stop Script
# Manual intervention script for stopping the backend service

set -e

SERVICE_NAME="autobot-user-backend"

echo "Stopping ${SERVICE_NAME}..."

if ! systemctl is-active --quiet "${SERVICE_NAME}"; then
    echo "${SERVICE_NAME} is not running"
    exit 0
fi

sudo systemctl stop "${SERVICE_NAME}"

# Wait for service to stop
for i in {1..10}; do
    if ! systemctl is-active --quiet "${SERVICE_NAME}"; then
        echo "${SERVICE_NAME} stopped successfully"
        exit 0
    fi
    sleep 1
done

echo "Warning: ${SERVICE_NAME} may still be stopping"
exit 1
