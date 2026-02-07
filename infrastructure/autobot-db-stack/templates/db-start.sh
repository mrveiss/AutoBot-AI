#!/bin/bash
# AutoBot DB Stack - Start Script
# Manual intervention script for starting all database services

set -e

STACK_DIR="/opt/autobot/autobot-db-stack"
cd "${STACK_DIR}"

echo "Starting AutoBot DB Stack..."

# Check if Docker is running
if ! systemctl is-active --quiet docker; then
    echo "Error: Docker is not running"
    echo "Start Docker first: sudo systemctl start docker"
    exit 1
fi

# Ensure secrets directory exists
if [[ ! -f "${STACK_DIR}/secrets/postgres_password.txt" ]]; then
    echo "Creating secrets directory..."
    mkdir -p "${STACK_DIR}/secrets"
    # Generate random password if not exists
    openssl rand -base64 32 > "${STACK_DIR}/secrets/postgres_password.txt"
    chmod 600 "${STACK_DIR}/secrets/postgres_password.txt"
    echo "Generated new PostgreSQL password"
fi

# Start the stack
echo "Starting database containers..."
docker compose up -d

# Wait for services to be healthy
echo "Waiting for services to be healthy..."
sleep 10

# Check each service
SERVICES_OK=true

echo ""
echo "Checking service health..."

# Redis
if docker exec autobot-redis redis-cli ping 2>/dev/null | grep -q "PONG"; then
    echo "  Redis: OK"
else
    echo "  Redis: FAILED"
    SERVICES_OK=false
fi

# PostgreSQL
if docker exec autobot-postgres pg_isready -U autobot 2>/dev/null | grep -q "accepting"; then
    echo "  PostgreSQL: OK"
else
    echo "  PostgreSQL: FAILED"
    SERVICES_OK=false
fi

# ChromaDB
if curl -s "http://127.0.0.1:8000/api/v1/heartbeat" 2>/dev/null | grep -q "nanosecond"; then
    echo "  ChromaDB: OK"
else
    echo "  ChromaDB: FAILED"
    SERVICES_OK=false
fi

echo ""
if [[ "${SERVICES_OK}" == "true" ]]; then
    echo "AutoBot DB Stack started successfully"
    exit 0
else
    echo "Warning: Some services failed to start"
    echo "Check logs: docker compose logs"
    exit 1
fi
