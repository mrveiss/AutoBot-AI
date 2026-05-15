#!/bin/bash
# AutoBot SLM Frontend - Start Script
# Manual intervention script for starting nginx (serves frontend)

set -e

echo "Starting nginx (SLM frontend)..."

if systemctl is-active --quiet nginx; then
    echo "nginx is already running"
    exit 0
fi

sudo systemctl start nginx

# Wait for nginx to be ready
for i in {1..5}; do
    if curl -sk https://127.0.0.1/ > /dev/null 2>&1; then
        echo "nginx started successfully"
        exit 0
    fi
    sleep 1
done

echo "Warning: nginx started but not responding on HTTPS"
exit 1
