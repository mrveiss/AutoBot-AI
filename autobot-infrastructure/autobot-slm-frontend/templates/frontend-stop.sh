#!/bin/bash
# AutoBot SLM Frontend - Stop Script
# Manual intervention script for stopping nginx

set -e

echo "Stopping nginx (SLM frontend)..."

if ! systemctl is-active --quiet nginx; then
    echo "nginx is not running"
    exit 0
fi

sudo systemctl stop nginx

echo "nginx stopped"
