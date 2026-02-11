#!/bin/bash
# =============================================================================
# DEV/SANDBOX ONLY - This script assumes Docker containers.
# Production uses native deployments. See Ansible roles for equivalent.
# =============================================================================
# Start NPU Worker Separately
# Useful for testing NPU capabilities

set -e

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${GREEN}🚀 Starting AutoBot NPU Worker${NC}"

# Check for NPU hardware
if command -v lspci &>/dev/null && lspci | grep -i "neural\|npu\|ai" > /dev/null 2>&1; then
    echo -e "${GREEN}✅ NPU hardware detected${NC}"
    NPU_AVAILABLE=true
else
    echo -e "${YELLOW}⚠️  No NPU hardware detected - will use CPU fallback${NC}"
    NPU_AVAILABLE=false
fi

# Build NPU worker if needed
if ! docker images | grep -q "autobot-npu-worker"; then
    echo -e "${YELLOW}Building NPU worker container...${NC}"
    docker build -f docker/npu-worker/Dockerfile.npu-worker -t autobot-npu-worker:latest .
fi

# Start with Docker Compose
if command -v docker-compose &> /dev/null; then
    COMPOSE_CMD="docker-compose"
else
    COMPOSE_CMD="docker compose"
fi

echo -e "${GREEN}Starting NPU worker...${NC}"
$COMPOSE_CMD -f docker/compose/docker-compose.hybrid.yml --profile npu up -d autobot-npu-worker

# Wait for startup
echo -e "${YELLOW}Waiting for NPU worker to start...${NC}"
sleep 10

# Check health
if curl -s -f http://localhost:8081/health > /dev/null 2>&1; then
    echo -e "${GREEN}✅ NPU worker is running and healthy${NC}"
    echo -e "${GREEN}🌐 NPU worker available at: http://localhost:8081${NC}"
    echo -e "${GREEN}🧪 Test with: python test_npu_worker.py${NC}"
else
    echo -e "${RED}❌ NPU worker failed to start properly${NC}"
    echo -e "${YELLOW}Check logs with: docker logs autobot-npu-worker${NC}"
    exit 1
fi
