#!/bin/bash
# AutoBot DB Stack - Stop Script
# Manual intervention script for stopping all database services

set -e

STACK_DIR="/opt/autobot/autobot-db-stack"
cd "${STACK_DIR}"

echo "Stopping AutoBot DB Stack..."

# Check if Docker is running
if ! systemctl is-active --quiet docker; then
    echo "Docker is not running, nothing to stop"
    exit 0
fi

# Stop the stack gracefully
echo "Stopping database containers..."
docker compose stop

# Optionally remove containers (keep volumes)
read -p "Remove containers? (volumes will be preserved) [y/N]: " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    docker compose down
    echo "Containers removed (volumes preserved)"
else
    echo "Containers stopped (can restart quickly)"
fi

echo "AutoBot DB Stack stopped"
