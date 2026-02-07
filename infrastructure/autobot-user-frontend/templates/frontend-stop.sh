#!/bin/bash
# AutoBot User Frontend - Stop Script
# Manual intervention script for stopping the frontend
# Note: This stops nginx entirely, affecting all sites

set -e

SERVICE_NAME="nginx"

echo "Stopping AutoBot User Frontend (nginx)..."

if ! systemctl is-active --quiet "${SERVICE_NAME}"; then
    echo "Nginx is not running"
    exit 0
fi

# Just reload to remove the site, don't stop nginx entirely
# To fully stop: sudo systemctl stop nginx
echo "Note: To stop nginx entirely, use: sudo systemctl stop nginx"
echo "This script only disables the autobot-user site"

if [[ -L "/etc/nginx/sites-enabled/autobot-user.conf" ]]; then
    sudo rm -f "/etc/nginx/sites-enabled/autobot-user.conf"
    sudo systemctl reload "${SERVICE_NAME}"
    echo "AutoBot User Frontend disabled"
else
    echo "Site already disabled"
fi
