#!/bin/bash
# AutoBot SLM Frontend - Status Script
# Manual intervention script for checking nginx status

echo "=== SLM Frontend (nginx) Status ==="
echo

# Systemd status
if systemctl is-active --quiet nginx; then
    echo "Service: RUNNING"
else
    echo "Service: STOPPED"
fi

# HTTPS check
if curl -sk https://127.0.0.1/ > /dev/null 2>&1; then
    echo "HTTPS:   OK"
else
    echo "HTTPS:   NOT RESPONDING"
fi

# HTTP redirect check
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1/ 2>/dev/null || echo "000")
if [ "$HTTP_CODE" = "301" ] || [ "$HTTP_CODE" = "302" ]; then
    echo "HTTP:    Redirecting to HTTPS (${HTTP_CODE})"
else
    echo "HTTP:    Code ${HTTP_CODE}"
fi

echo
echo "=== Recent Logs ==="
sudo journalctl -u nginx -n 10 --no-pager 2>/dev/null || tail -20 /opt/autobot/logs/nginx-error.log 2>/dev/null || echo "No logs available"
