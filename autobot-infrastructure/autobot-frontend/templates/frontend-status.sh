#!/bin/bash
# AutoBot User Frontend - Status Script
# Manual intervention script for checking frontend status

SERVICE_NAME="nginx"

echo "=== AutoBot User Frontend Status ==="
echo ""

# Check nginx status
echo "Nginx Status:"
systemctl status "${SERVICE_NAME}" --no-pager 2>/dev/null | head -15 || echo "Nginx not running"
echo ""

# Check if site is enabled
echo "Site Configuration:"
if [[ -L "/etc/nginx/sites-enabled/autobot-user.conf" ]]; then
    echo "autobot-user.conf is ENABLED"
else
    echo "autobot-user.conf is NOT enabled"
fi
echo ""

# Health check
echo "Health Checks:"
echo -n "HTTPS (443): "
if curl -sk "https://127.0.0.1/health" 2>/dev/null; then
    echo " OK"
else
    echo "NOT responding"
fi

echo -n "HTTP (80): "
if curl -s "http://127.0.0.1/health" 2>/dev/null; then
    echo " OK (should redirect)"
else
    echo "NOT responding"
fi
echo ""

# Check backend connectivity
echo "Backend Connectivity:"
echo -n "API proxy: "
if curl -sk "https://127.0.0.1/api/health" 2>/dev/null; then
    echo " OK"
else
    echo "NOT responding (backend may be down)"
fi
echo ""

# SSL certificate info
echo "SSL Certificate:"
if [[ -f "/opt/autobot/nginx/certs/autobot-user.crt" ]]; then
    openssl x509 -in /opt/autobot/nginx/certs/autobot-user.crt -noout -dates 2>/dev/null || echo "Could not read certificate"
else
    echo "Certificate not found"
fi
