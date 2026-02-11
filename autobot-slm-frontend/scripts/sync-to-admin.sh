#!/bin/bash
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss

# SLM Admin Sync Script
# Syncs slm-admin to the management node (172.16.168.19)

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
_PROJECT_ROOT="$SCRIPT_DIR"
while [ "$_PROJECT_ROOT" != "/" ] && [ ! -f "$_PROJECT_ROOT/.env" ]; do
    _PROJECT_ROOT="$(dirname "$_PROJECT_ROOT")"
done
source "$_PROJECT_ROOT/infrastructure/shared/scripts/lib/ssot-config.sh" 2>/dev/null || true
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
REMOTE_HOST="${AUTOBOT_SLM_HOST:-172.16.168.19}"
REMOTE_USER="${AUTOBOT_SSH_USER:-autobot}"
REMOTE_PATH="/home/autobot/slm-admin"

echo "==================================="
echo "SLM Admin Deployment Sync"
echo "==================================="
echo "Source: $PROJECT_DIR"
echo "Target: $REMOTE_USER@$REMOTE_HOST:$REMOTE_PATH"
echo ""

# Check if remote is reachable
if ! ping -c 1 -W 2 "$REMOTE_HOST" > /dev/null 2>&1; then
    echo "ERROR: Cannot reach $REMOTE_HOST"
    exit 1
fi

# Sync source files (exclude node_modules and dist)
echo "Syncing source files..."
rsync -avz --delete \
    --exclude 'node_modules/' \
    --exclude 'dist/' \
    --exclude '.git/' \
    --exclude '*.log' \
    "$PROJECT_DIR/" \
    "$REMOTE_USER@$REMOTE_HOST:$REMOTE_PATH/"

echo ""
echo "Installing dependencies on remote..."
ssh "$REMOTE_USER@$REMOTE_HOST" "cd $REMOTE_PATH && npm install"

# Option to build
if [ "$1" = "--build" ]; then
    echo ""
    echo "Building for production..."
    ssh "$REMOTE_USER@$REMOTE_HOST" "cd $REMOTE_PATH && npm run build"
fi

# Option to start dev server
if [ "$1" = "--dev" ]; then
    echo ""
    echo "Starting development server..."
    ssh "$REMOTE_USER@$REMOTE_HOST" "cd $REMOTE_PATH && npm run dev"
fi

echo ""
echo "==================================="
echo "Sync complete!"
echo "==================================="
echo ""
echo "To start development server:"
echo "  ssh $REMOTE_USER@$REMOTE_HOST 'cd $REMOTE_PATH && npm run dev'"
echo ""
echo "To build for production:"
echo "  ssh $REMOTE_USER@$REMOTE_HOST 'cd $REMOTE_PATH && npm run build'"
echo ""
