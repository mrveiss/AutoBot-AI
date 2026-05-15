#!/bin/bash
# =============================================================================
# DEV/SANDBOX ONLY - This script assumes Docker containers.
# Production uses native deployments. See Ansible roles for equivalent.
# =============================================================================

# Script to start ALL AutoBot containers for full functionality
# This ensures Redis, NPU Worker, AI Stack, and Playwright are all running

echo "🚀 Starting ALL AutoBot containers for full functionality..."

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Function to check if a container is healthy
check_container_health() {
    local container_name=$1
    local health_endpoint=$2
    local max_attempts=${3:-10}

    echo "🔍 Checking $container_name health..."
    for i in $(seq 1 $max_attempts); do
        if [ -n "$health_endpoint" ]; then
            # Check via HTTP endpoint
            if curl -sf "$health_endpoint" >/dev/null 2>&1; then
                echo -e "${GREEN}✅ $container_name is healthy.${NC}"
                return 0
            fi
        else
            # Check via docker health status
            if docker inspect --format='{{.State.Health.Status}}' "$container_name" 2>/dev/null | grep -q "healthy"; then
                echo -e "${GREEN}✅ $container_name is healthy.${NC}"
                return 0
            fi
        fi
        echo "⏳ Waiting for $container_name... (attempt $i/$max_attempts)"
        sleep 2
    done
    echo -e "${YELLOW}⚠️  $container_name health check timed out. Container may still be starting.${NC}"
    return 1
}

# Ensure docker and docker-compose are available
if ! command -v docker &> /dev/null; then
    echo -e "${RED}❌ Docker is not installed or not in PATH.${NC}"
    exit 1
fi

if ! command -v docker-compose &> /dev/null; then
    echo -e "${RED}❌ docker-compose is not installed or not in PATH.${NC}"
    exit 1
fi

# Check if docker daemon is running
if ! docker info >/dev/null 2>&1; then
    echo -e "${RED}❌ Docker daemon is not running. Please start Docker.${NC}"
    exit 1
fi

# Start all containers using docker-compose
echo "🔄 Starting all containers via docker-compose..."

# Use --no-deps to avoid circular dependencies, then start in order
docker-compose -f docker/compose/docker-compose.hybrid.yml up -d autobot-redis || {
    echo -e "${RED}❌ Failed to start Redis Stack.${NC}"
    exit 1
}

# Wait for Redis to be ready before starting dependent services
check_container_health "autobot-redis" "" 10

# Start NPU Worker
docker-compose -f docker/compose/docker-compose.hybrid.yml up -d autobot-npu-worker || {
    echo -e "${YELLOW}⚠️  Failed to start NPU Worker. Continuing without NPU acceleration.${NC}"
}

# Start AI Stack (if defined in docker-compose)
if docker-compose -f docker-compose.hybrid.yml config --services | grep -q "autobot-ai-stack"; then
    docker-compose -f docker/compose/docker-compose.hybrid.yml up -d autobot-ai-stack || {
        echo -e "${YELLOW}⚠️  Failed to start AI Stack container.${NC}"
    }
fi

# Start Playwright service
if docker ps -a --format '{{.Names}}' | grep -q '^autobot-playwright$'; then
    echo "🔄 Starting Playwright service..."
    docker start autobot-playwright || {
        echo -e "${YELLOW}⚠️  Failed to start Playwright container.${NC}"
    }
else
    echo -e "${YELLOW}⚠️  Playwright container not found. Run setup_agent.sh to create it.${NC}"
fi

# Wait for all services to be ready
echo ""
echo "⏳ Waiting for all services to be ready..."

# Check each service
check_container_health "autobot-redis" "" 10
check_container_health "autobot-npu-worker" "http://localhost:8081/health" 15
check_container_health "autobot-playwright" "http://localhost:3000/health" 15

# If AI stack is running, check it too
if docker ps --format '{{.Names}}' | grep -q '^autobot-ai-stack$'; then
    check_container_health "autobot-ai-stack" "http://localhost:8080/health" 20
fi

# Show status summary
echo ""
echo "📊 Container Status Summary:"
echo "================================"
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}" | grep -E "(autobot-|NAMES)"

echo ""
echo -e "${GREEN}✅ All containers have been started!${NC}"
echo ""
echo "🌐 Service Endpoints:"
echo "  • Redis:        localhost:6379"
echo "  • RedisInsight: http://localhost:8002"  # Now on port 8002 internally too
echo "  • NPU Worker:   http://localhost:8081"
echo "  • Playwright:   http://localhost:3000"
if docker ps --format '{{.Names}}' | grep -q '^autobot-ai-stack$'; then
    echo "  • AI Stack:     http://localhost:8080"
fi

echo ""
echo "💡 To start the AutoBot application, run: ./run_agent.sh"
echo "💡 To stop all containers, run: docker-compose -f docker/compose/docker-compose.hybrid.yml down"
