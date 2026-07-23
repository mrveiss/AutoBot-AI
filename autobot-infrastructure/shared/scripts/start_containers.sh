#!/bin/bash
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# =============================================================================
# DEV/SANDBOX ONLY - This script assumes Docker containers.
# Production uses native deployments. See Ansible roles for equivalent.
# =============================================================================
# Smart container startup script that checks and starts existing containers

set -e

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Container names
REDIS_CONTAINER="autobot-redis"
NPU_CONTAINER="autobot-npu-worker"
PLAYWRIGHT_CONTAINER="autobot-playwright-vnc"

# Function to check if container exists
container_exists() {
    docker ps -a --format "table {{.Names}}" | grep -q "^$1$"
}

# Function to check if container is running
container_running() {
    docker ps --format "table {{.Names}}" | grep -q "^$1$"
}

# Function to start or create container
start_container() {
    local container_name=$1
    local compose_service=$2

    if container_exists "$container_name"; then
        if container_running "$container_name"; then
            echo -e "${GREEN}✅ '$container_name' container is already running.${NC}"
        else
            echo -e "${YELLOW}🔄 Starting existing '$container_name' container...${NC}"
            docker start "$container_name"
            if [ $? -eq 0 ]; then
                echo -e "${GREEN}✅ '$container_name' container started successfully.${NC}"
            else
                echo -e "${RED}❌ Failed to start '$container_name' container.${NC}"
                echo -e "${YELLOW}🔄 Removing and recreating container...${NC}"
                docker rm "$container_name"
                docker-compose -f docker/compose/docker-compose.base.yml up -d "$compose_service"
            fi
        fi
    else
        echo -e "${YELLOW}🔄 Creating new '$container_name' container...${NC}"
        docker-compose -f docker/compose/docker-compose.base.yml up -d "$compose_service"
    fi
}

# Main execution
echo -e "${YELLOW}📦 Starting Docker containers...${NC}"

# Check if docker is running
if ! docker info > /dev/null 2>&1; then
    echo -e "${RED}❌ Docker is not running. Please start Docker first.${NC}"
    exit 1
fi

# Start Redis
start_container "$REDIS_CONTAINER" "redis"

# Start NPU Worker
start_container "$NPU_CONTAINER" "npu-worker"

# Start Playwright (if needed)
if [ "$1" != "--no-playwright" ]; then
    start_container "$PLAYWRIGHT_CONTAINER" "playwright"
fi

# Wait for containers to be ready
echo -e "${YELLOW}⏳ Waiting for containers to be ready...${NC}"
sleep 3

# Health checks
echo -e "${YELLOW}🔍 Checking container health...${NC}"

# Check Redis
if docker exec "$REDIS_CONTAINER" redis-cli ping > /dev/null 2>&1; then
    echo -e "${GREEN}✅ Redis is ready.${NC}"
else
    echo -e "${RED}❌ Redis health check failed.${NC}"
    exit 1
fi

# Check NPU Worker
if curl -s http://localhost:8002/health > /dev/null 2>&1; then
    echo -e "${GREEN}✅ NPU Worker is ready.${NC}"
else
    echo -e "${YELLOW}⚠️  NPU Worker health check failed (may still be starting).${NC}"
fi

echo -e "${GREEN}✅ All containers are ready!${NC}"
