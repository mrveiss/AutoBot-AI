#!/bin/bash
# AutoBot DB Stack - Start Script
# Manual intervention script for starting all database services

set -e

echo "Starting AutoBot DB Stack..."

# Start Redis Stack
echo "Starting Redis Stack..."
if systemctl list-unit-files "autobot-redis.service" &>/dev/null; then
    sudo systemctl start autobot-redis
elif systemctl list-unit-files "redis-stack-server.service" &>/dev/null; then
    sudo systemctl start redis-stack-server
else
    echo "Warning: Redis Stack service not installed"
fi

# Start PostgreSQL
echo "Starting PostgreSQL..."
if systemctl list-unit-files "postgresql.service" &>/dev/null; then
    sudo systemctl start postgresql
else
    echo "Warning: PostgreSQL service not installed"
fi

# Start ChromaDB
echo "Starting ChromaDB..."
if systemctl list-unit-files "autobot-chromadb.service" &>/dev/null; then
    sudo systemctl start autobot-chromadb
else
    echo "Warning: ChromaDB service not installed"
fi

# Wait for services to be healthy
echo "Waiting for services to be healthy..."
sleep 5

# Check each service
SERVICES_OK=true

echo ""
echo "Checking service health..."

# Redis
echo -n "  Redis (6379): "
if redis-cli ping 2>/dev/null | grep -q "PONG"; then
    echo "OK"
else
    echo "FAILED"
    SERVICES_OK=false
fi

# PostgreSQL
echo -n "  PostgreSQL (5432): "
if pg_isready -h 127.0.0.1 -U autobot 2>/dev/null | grep -q "accepting"; then
    echo "OK"
else
    echo "FAILED"
    SERVICES_OK=false
fi

# ChromaDB
echo -n "  ChromaDB (8000): "
if curl -s "http://127.0.0.1:8000/api/v1/heartbeat" 2>/dev/null | grep -q "nanosecond"; then
    echo "OK"
else
    echo "FAILED"
    SERVICES_OK=false
fi

echo ""
if [[ "${SERVICES_OK}" == "true" ]]; then
    echo "AutoBot DB Stack started successfully"
    exit 0
else
    echo "Warning: Some services failed to start"
    exit 1
fi
