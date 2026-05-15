#!/bin/bash
# AutoBot User Frontend - Start Script
# Manual intervention script for starting the frontend (nginx)

set -e

SERVICE_NAME="nginx"
CONFIG_FILE="/etc/nginx/sites-enabled/autobot-user.conf"

echo "Starting AutoBot User Frontend..."

# Verify config exists
if [[ ! -f "${CONFIG_FILE}" ]]; then
    echo "Error: Nginx config not found at ${CONFIG_FILE}"
    echo "Run the deployment script first"
    exit 1
fi

# Test nginx configuration
echo "Testing nginx configuration..."
if ! sudo nginx -t; then
    echo "Error: Nginx configuration test failed"
    exit 1
fi

# Start or reload nginx
if systemctl is-active --quiet "${SERVICE_NAME}"; then
    echo "Nginx is running, reloading configuration..."
    sudo systemctl reload "${SERVICE_NAME}"
else
    echo "Starting nginx..."
    sudo systemctl start "${SERVICE_NAME}"
fi

# Verify it's responding
sleep 2
if curl -sk "https://127.0.0.1/health" > /dev/null 2>&1; then
    echo "AutoBot User Frontend started successfully"
    exit 0
elif curl -s "http://127.0.0.1/health" > /dev/null 2>&1; then
    echo "AutoBot User Frontend started (HTTP only)"
    exit 0
fi

echo "Warning: Frontend started but health check not responding"
exit 1
