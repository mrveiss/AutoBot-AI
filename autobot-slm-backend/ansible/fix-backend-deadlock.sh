#!/bin/bash
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
#
# Fix Backend Worker Deadlock (Issue #876)
# Run this script on the backend server (172.16.168.20)

set -e

SERVICE_FILE="/etc/systemd/system/autobot-backend.service"
BACKUP_FILE="${SERVICE_FILE}.backup-$(date +%s)"
TEMP_FILE="/tmp/autobot-backend-single-worker.service"

echo "========================================="
echo "Backend Worker Deadlock Fix"
echo "========================================="

# Check if service exists
if [ ! -f "$SERVICE_FILE" ]; then
    echo "❌ Error: Service file not found at $SERVICE_FILE"
    exit 1
fi

echo "✓ Service file found"

# Backup current service file
echo "Creating backup..."
sudo cp "$SERVICE_FILE" "$BACKUP_FILE"
echo "✓ Backup created: $BACKUP_FILE"

# Create new service file with single worker
cat > "$TEMP_FILE" << 'EOF'
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
[Unit]
Description=AutoBot Backend API
After=network.target redis.service

[Service]
Type=simple
User=autobot
Group=autobot
WorkingDirectory=/opt/autobot/autobot-user-backend
Environment="PATH=/opt/autobot/autobot-user-backend/venv/bin:/usr/local/bin:/usr/bin:/bin"
Environment="PYTHONPATH=/opt/autobot:/opt/autobot/autobot-user-backend"
EnvironmentFile=/opt/autobot/autobot-user-backend/.env
EnvironmentFile=-/etc/autobot/service-keys/main-backend.env

# Issue #876: Single worker mode to prevent initialization deadlock
# FastAPI is async - single worker handles high concurrency efficiently
ExecStart=/opt/autobot/autobot-user-backend/venv/bin/uvicorn main:app --host 0.0.0.0 --port 8443 --workers 1

Restart=always
RestartSec=5
StandardOutput=append:/var/log/autobot/backend.log
StandardError=append:/var/log/autobot/backend-error.log

[Install]
WantedBy=multi-user.target
EOF

echo "✓ New service configuration created"

# Install new service file
echo "Installing new service configuration..."
sudo cp "$TEMP_FILE" "$SERVICE_FILE"
echo "✓ Service file updated"

# Reload systemd
echo "Reloading systemd daemon..."
sudo systemctl daemon-reload
echo "✓ Systemd reloaded"

# Restart service
echo "Stopping backend service..."
sudo systemctl stop autobot-backend

echo "Waiting for processes to stop..."
for i in {1..10}; do
    if ! pgrep -f "uvicorn main:app" > /dev/null; then
        echo "✓ All processes stopped"
        break
    fi
    sleep 1
done

echo "Starting backend with new configuration..."
sudo systemctl start autobot-backend
echo "✓ Service started"

# Wait for initialization
echo "Waiting for backend initialization (10s)..."
sleep 10

# Check health
echo "Checking backend health..."
if curl -k -s -f --max-time 10 https://172.16.168.20:8443/api/health > /dev/null 2>&1; then
    echo "✓ Backend health check passed"
else
    echo "⚠ Health check timeout (backend may still be initializing)"
fi

# Check for deadlock
echo "Checking for deadlock (SYN_SENT connections)..."
SYN_SENT=$(sudo lsof -i :8443 -n 2>/dev/null | grep SYN_SENT || true)
if [ -z "$SYN_SENT" ]; then
    echo "✓ No deadlock detected"
else
    echo "❌ Deadlock detected:"
    echo "$SYN_SENT"
    exit 1
fi

# Check worker count
echo "Verifying single worker mode..."
WORKER_COUNT=$(ps aux | grep -E 'uvicorn main:app' | grep -v grep | wc -l)
if [ "$WORKER_COUNT" -le 2 ]; then
    echo "✓ Single worker mode confirmed ($WORKER_COUNT processes)"
else
    echo "⚠ Warning: Multiple workers detected ($WORKER_COUNT processes)"
fi

# Service status
echo ""
echo "========================================="
echo "Service Status"
echo "========================================="
sudo systemctl status autobot-backend --no-pager -l

echo ""
echo "========================================="
echo "Fix Complete!"
echo "========================================="
echo "Backup: $BACKUP_FILE"
echo "Workers: Single worker mode (no deadlock)"
echo ""
echo "Login should now work at https://172.16.168.21/"
echo ""
echo "To rollback if needed:"
echo "  sudo cp $BACKUP_FILE $SERVICE_FILE"
echo "  sudo systemctl daemon-reload"
echo "  sudo systemctl restart autobot-backend"
