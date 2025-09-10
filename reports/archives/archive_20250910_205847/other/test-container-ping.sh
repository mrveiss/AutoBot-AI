#!/bin/bash
# Test container network connectivity

set -e

echo "🔍 Testing Docker container network connectivity"
echo "=============================================="

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

# Test basic Docker functionality
echo -e "\n${YELLOW}Testing Docker daemon...${NC}"
if docker version >/dev/null 2>&1; then
    echo -e "${GREEN}✅ Docker daemon is accessible${NC}"
else
    echo -e "${RED}❌ Cannot connect to Docker daemon${NC}"
    exit 1
fi

# Create test network if it doesn't exist
TEST_NETWORK="autobot-test-network"
echo -e "\n${YELLOW}Creating test network...${NC}"
docker network create $TEST_NETWORK 2>/dev/null || echo "Network already exists"

# Start test containers
echo -e "\n${YELLOW}Starting test containers...${NC}"

# Container 1: Simple web server
docker run -d --rm --name test-server --network $TEST_NETWORK \
    -e MESSAGE="Hello from test server" \
    busybox sh -c 'echo $MESSAGE > index.html && httpd -f -p 8080' >/dev/null 2>&1

# Container 2: Client to test connectivity
docker run -d --rm --name test-client --network $TEST_NETWORK \
    busybox sleep 300 >/dev/null 2>&1

# Wait for containers to start
sleep 2

# Test 1: Container-to-container connectivity
echo -e "\n${YELLOW}Test 1: Container-to-container connectivity${NC}"
if docker exec test-client wget -qO- http://test-server:8080 | grep -q "Hello from test server"; then
    echo -e "${GREEN}✅ Containers can communicate via Docker network${NC}"
    CONTAINER_NET="OK"
else
    echo -e "${RED}❌ Containers cannot communicate via Docker network${NC}"
    CONTAINER_NET="FAIL"
fi

# Test 2: Host-to-container connectivity (via published port)
echo -e "\n${YELLOW}Test 2: Host-to-container connectivity${NC}"

# Stop and recreate server with published port
docker stop test-server >/dev/null 2>&1
docker run -d --rm --name test-server --network $TEST_NETWORK \
    -p 18080:8080 \
    -e MESSAGE="Hello from test server" \
    busybox sh -c 'echo $MESSAGE > index.html && httpd -f -p 8080' >/dev/null 2>&1

sleep 2

if curl -s http://localhost:18080 | grep -q "Hello from test server"; then
    echo -e "${GREEN}✅ Host can reach container via published port${NC}"
    HOST_TO_CONTAINER="OK"
else
    echo -e "${RED}❌ Host cannot reach container via published port${NC}"
    HOST_TO_CONTAINER="FAIL"
fi

# Test 3: Container-to-host connectivity
echo -e "\n${YELLOW}Test 3: Container-to-host connectivity${NC}"

# Get host gateway IP
if [[ "$OSTYPE" == "darwin"* ]]; then
    HOST_IP="host.docker.internal"
elif grep -q microsoft /proc/version 2>/dev/null; then
    HOST_IP="host.docker.internal"
else
    HOST_IP=$(docker network inspect bridge -f '{{range .IPAM.Config}}{{.Gateway}}{{end}}')
fi

# Start a simple server on host
python3 -m http.server 18081 >/dev/null 2>&1 &
SERVER_PID=$!
sleep 2

if docker exec test-client wget -qO- http://${HOST_IP}:18081 >/dev/null 2>&1; then
    echo -e "${GREEN}✅ Container can reach host services${NC}"
    CONTAINER_TO_HOST="OK"
else
    echo -e "${RED}❌ Container cannot reach host services${NC}"
    CONTAINER_TO_HOST="FAIL"
fi

# Kill the test server
kill $SERVER_PID 2>/dev/null || true

# Test 4: DNS resolution
echo -e "\n${YELLOW}Test 4: DNS resolution in containers${NC}"
if docker exec test-client nslookup google.com >/dev/null 2>&1; then
    echo -e "${GREEN}✅ DNS resolution works in containers${NC}"
    DNS="OK"
else
    echo -e "${RED}❌ DNS resolution fails in containers${NC}"
    DNS="FAIL"
fi

# Cleanup
echo -e "\n${YELLOW}Cleaning up test resources...${NC}"
docker stop test-server test-client >/dev/null 2>&1 || true
docker network rm $TEST_NETWORK >/dev/null 2>&1 || true

# Summary
echo -e "\n${YELLOW}=== Test Summary ===${NC}"
echo "Container-to-container: $CONTAINER_NET"
echo "Host-to-container:      $HOST_TO_CONTAINER"
echo "Container-to-host:      $CONTAINER_TO_HOST"
echo "DNS resolution:         $DNS"

# Recommendations
echo -e "\n${YELLOW}=== Recommendations ===${NC}"

if [[ "$CONTAINER_NET" == "FAIL" ]]; then
    echo "- Check Docker daemon and network configuration"
    echo "- Try restarting Docker service"
fi

if [[ "$HOST_TO_CONTAINER" == "FAIL" ]]; then
    echo "- Check firewall rules"
    echo "- Verify Docker's iptables configuration"
fi

if [[ "$CONTAINER_TO_HOST" == "FAIL" ]]; then
    echo "- Consider using host networking mode"
    echo "- Check if host.docker.internal is available"
fi

if [[ "$DNS" == "FAIL" ]]; then
    echo "- Check Docker's DNS configuration"
    echo "- Verify /etc/resolv.conf in containers"
fi

# Exit code based on critical tests
if [[ "$CONTAINER_NET" == "OK" ]] && [[ "$HOST_TO_CONTAINER" == "OK" ]]; then
    echo -e "\n${GREEN}✅ Docker networking is functional${NC}"
    exit 0
else
    echo -e "\n${RED}❌ Docker networking has issues${NC}"
    exit 1
fi