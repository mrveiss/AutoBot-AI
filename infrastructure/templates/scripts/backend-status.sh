#!/bin/bash
# AutoBot SLM Backend - Status Script
# Manual intervention script for checking backend service status

SERVICE_NAME="autobot-slm-backend"

echo "=== ${SERVICE_NAME} Status ==="
echo

# Systemd status
if systemctl is-active --quiet "${SERVICE_NAME}"; then
    echo "Service: RUNNING"
else
    echo "Service: STOPPED"
fi

# Health check
if curl -s http://127.0.0.1:8000/api/health > /dev/null 2>&1; then
    echo "Health:  OK"
    echo
    echo "Health Response:"
    curl -s http://127.0.0.1:8000/api/health | python3 -m json.tool 2>/dev/null || curl -s http://127.0.0.1:8000/api/health
else
    echo "Health:  NOT RESPONDING"
fi

echo
echo "=== Recent Logs ==="
sudo journalctl -u "${SERVICE_NAME}" -n 10 --no-pager 2>/dev/null || tail -20 /opt/autobot/logs/slm-backend.log 2>/dev/null || echo "No logs available"
