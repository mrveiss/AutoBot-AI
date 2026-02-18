#!/bin/bash
# AutoBot DB Stack - Status Script
# Manual intervention script for checking database services status

echo "=== AutoBot DB Stack Status ==="
echo ""

# Redis status
echo "Redis Stack (6379):"
if systemctl is-active --quiet autobot-redis 2>/dev/null || systemctl is-active --quiet redis-stack-server 2>/dev/null; then
    echo "  Service: RUNNING"
    if redis-cli ping 2>/dev/null | grep -q "PONG"; then
        echo "  Health: HEALTHY"
        redis-cli info server 2>/dev/null | grep -E "redis_version|uptime_in_seconds" | head -3 || true
    else
        echo "  Health: NOT RESPONDING"
    fi
else
    echo "  Service: STOPPED"
fi
echo ""

# PostgreSQL status
echo "PostgreSQL (5432):"
if systemctl is-active --quiet postgresql 2>/dev/null; then
    echo "  Service: RUNNING"
    if pg_isready -h 127.0.0.1 -U autobot 2>/dev/null | grep -q "accepting"; then
        echo "  Health: HEALTHY"
    else
        echo "  Health: NOT RESPONDING"
    fi
else
    echo "  Service: STOPPED"
fi
echo ""

# ChromaDB status
echo "ChromaDB (8000):"
if systemctl is-active --quiet autobot-chromadb 2>/dev/null; then
    echo "  Service: RUNNING"
    if curl -s "http://127.0.0.1:8000/api/v1/heartbeat" 2>/dev/null | grep -q "nanosecond"; then
        echo "  Health: HEALTHY"
    else
        echo "  Health: NOT RESPONDING"
    fi
else
    echo "  Service: STOPPED"
fi
echo ""

# Disk usage
echo "Data Directory Sizes:"
du -sh /var/lib/redis 2>/dev/null | awk '{print "  Redis: " $1}' || echo "  Redis: N/A"
du -sh /var/lib/postgresql 2>/dev/null | awk '{print "  PostgreSQL: " $1}' || echo "  PostgreSQL: N/A"
du -sh /opt/autobot/autobot-db-stack/chromadb/data 2>/dev/null | awk '{print "  ChromaDB: " $1}' || echo "  ChromaDB: N/A"
echo ""

# Recent errors
echo "Recent Service Errors:"
echo "--- Redis ---"
sudo journalctl -u autobot-redis -u redis-stack-server -n 3 --no-pager -p err 2>/dev/null || echo "No recent errors"
echo "--- PostgreSQL ---"
sudo journalctl -u postgresql -n 3 --no-pager -p err 2>/dev/null || echo "No recent errors"
echo "--- ChromaDB ---"
sudo journalctl -u autobot-chromadb -n 3 --no-pager -p err 2>/dev/null || echo "No recent errors"
