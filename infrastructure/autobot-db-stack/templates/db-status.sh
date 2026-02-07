#!/bin/bash
# AutoBot DB Stack - Status Script
# Manual intervention script for checking database services status

STACK_DIR="/opt/autobot/autobot-db-stack"

echo "=== AutoBot DB Stack Status ==="
echo ""

# Check Docker
if ! systemctl is-active --quiet docker; then
    echo "Docker is NOT running"
    exit 1
fi

# Container status
echo "Container Status:"
docker compose -f "${STACK_DIR}/docker-compose.yml" ps 2>/dev/null || echo "Stack not deployed"
echo ""

# Redis health
echo "Redis (6379):"
if docker exec autobot-redis redis-cli ping 2>/dev/null | grep -q "PONG"; then
    echo "  Status: HEALTHY"
    echo "  Info:"
    docker exec autobot-redis redis-cli info server 2>/dev/null | grep -E "redis_version|uptime|connected_clients" | head -5 || true
else
    echo "  Status: NOT RESPONDING"
fi
echo ""

# PostgreSQL health
echo "PostgreSQL (5432):"
if docker exec autobot-postgres pg_isready -U autobot 2>/dev/null | grep -q "accepting"; then
    echo "  Status: HEALTHY"
    docker exec autobot-postgres psql -U autobot -c "SELECT version();" 2>/dev/null | head -3 || true
else
    echo "  Status: NOT RESPONDING"
fi
echo ""

# ChromaDB health
echo "ChromaDB (8000):"
if curl -s "http://127.0.0.1:8000/api/v1/heartbeat" 2>/dev/null | grep -q "nanosecond"; then
    echo "  Status: HEALTHY"
    curl -s "http://127.0.0.1:8000/api/v1/collections" 2>/dev/null | head -1 || true
else
    echo "  Status: NOT RESPONDING"
fi
echo ""

# Disk usage
echo "Volume Disk Usage:"
docker system df -v 2>/dev/null | grep -E "autobot-(redis|postgres|chroma)" || echo "No volumes found"
echo ""

# Recent logs
echo "Recent Errors (last 5 per service):"
echo "--- Redis ---"
docker logs --tail 5 autobot-redis 2>&1 | grep -i error || echo "No recent errors"
echo "--- PostgreSQL ---"
docker logs --tail 5 autobot-postgres 2>&1 | grep -i error || echo "No recent errors"
echo "--- ChromaDB ---"
docker logs --tail 5 autobot-chromadb 2>&1 | grep -i error || echo "No recent errors"
