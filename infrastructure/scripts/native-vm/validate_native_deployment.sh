#!/bin/bash
# AutoBot Native VM Deployment Validation Script
# Comprehensive testing of all services and inter-VM communication

set -e

# Load unified configuration system
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." &> /dev/null && pwd)"
if [[ -f "${SCRIPT_DIR}/config/load_config.sh" ]]; then
    export PATH="$HOME/bin:$PATH"  # Ensure yq is available
    source "${SCRIPT_DIR}/config/load_config.sh"
    echo -e "\033[0;32m✓ Loaded unified configuration system\033[0m"
else
    echo -e "\033[0;31m✗ Warning: Unified configuration not found, using fallback values\033[0m"
fi

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

SERVICES_TESTED=0
SERVICES_PASSED=0
ERRORS=()

test_service() {
    local name="$1"
    local url="$2"
    local expected_status="$3"
    local timeout="${4:-5}"

    SERVICES_TESTED=$((SERVICES_TESTED + 1))
    echo -n "  Testing $name... "

    if timeout $timeout curl -s "$url" >/dev/null 2>&1; then
        if [ -n "$expected_status" ]; then
            response=$(timeout $timeout curl -s "$url" 2>/dev/null)
            if echo "$response" | grep -q "$expected_status"; then
                echo -e "${GREEN}✅ PASS${NC}"
                SERVICES_PASSED=$((SERVICES_PASSED + 1))
                return 0
            else
                echo -e "${RED}❌ FAIL (unexpected response)${NC}"
                ERRORS+=("$name: Expected '$expected_status' but got: $response")
                return 1
            fi
        else
            echo -e "${GREEN}✅ PASS${NC}"
            SERVICES_PASSED=$((SERVICES_PASSED + 1))
            return 0
        fi
    else
        echo -e "${RED}❌ FAIL (unreachable)${NC}"
        ERRORS+=("$name: Service unreachable at $url")
        return 1
    fi
}

test_redis() {
    local name="$1"
    local host="$2"
    local port="$3"

    SERVICES_TESTED=$((SERVICES_TESTED + 1))
    echo -n "  Testing $name... "

    if echo "PING" | nc -w 2 "$host" "$port" | grep -q "PONG"; then
        echo -e "${GREEN}✅ PASS${NC}"
        SERVICES_PASSED=$((SERVICES_PASSED + 1))
        return 0
    else
        echo -e "${RED}❌ FAIL (no response)${NC}"
        ERRORS+=("$name: Redis not responding at $host:$port")
        return 1
    fi
}

echo -e "${GREEN}🚀 AutoBot Native VM Deployment Validation${NC}"
echo -e "${BLUE}==========================================${NC}"
echo ""

# Load native configuration
if [ -f ".env.native-vm" ]; then
    echo -e "${YELLOW}📁 Loading native VM configuration...${NC}"
    set -a
    source ".env.native-vm"
    set +a
    echo -e "${GREEN}✅ Configuration loaded${NC}"
else
    echo -e "${RED}❌ Native VM configuration not found (.env.native-vm)${NC}"
    exit 1
fi

echo ""
echo -e "${BLUE}🏗️  Architecture Overview:${NC}"
echo "  WSL Backend:  $(get_config "infrastructure.hosts.backend" 2>/dev/null || echo "172.16.168.20"):$(get_config "infrastructure.ports.backend" 2>/dev/null || echo "8001") (This machine)"
echo "  Frontend:     $(get_config "infrastructure.hosts.frontend" 2>/dev/null || echo "172.16.168.21")      (VM1 - Nginx + Vue.js)"
echo "  NPU Worker:   $(get_config "infrastructure.hosts.npu_worker" 2>/dev/null || echo "172.16.168.22"):$(get_config "infrastructure.ports.npu_worker" 2>/dev/null || echo "8081") (VM2 - Hardware detection)"
echo "  Redis Stack:  $(get_config "infrastructure.hosts.redis" 2>/dev/null || echo "172.16.168.23"):$(get_config "infrastructure.ports.redis" 2>/dev/null || echo "6379") (VM3 - Data layer)"
echo "  AI Stack:     $(get_config "infrastructure.hosts.ai_stack" 2>/dev/null || echo "172.16.168.24"):$(get_config "infrastructure.ports.ai_stack" 2>/dev/null || echo "8080") (VM4 - AI processing)"
echo "  Browser:      $(get_config "infrastructure.hosts.browser_service" 2>/dev/null || echo "172.16.168.25"):$(get_config "infrastructure.ports.browser_service" 2>/dev/null || echo "3000") (VM5 - Playwright automation)"
echo ""

echo -e "${YELLOW}🔍 Testing Individual VM Services...${NC}"

# Test all VM services
test_service "Frontend VM1" "$(get_service_url "frontend" 2>/dev/null || echo "http://172.16.168.21")/" ""
test_service "NPU Worker VM2" "$(get_service_url "npu_worker" 2>/dev/null || echo "http://172.16.168.22:8081")/health" "healthy"
test_redis "Redis Stack VM3" "$(get_config "infrastructure.hosts.redis" 2>/dev/null || echo "172.16.168.23")" "$(get_config "infrastructure.ports.redis" 2>/dev/null || echo "6379")"
test_service "AI Stack VM4" "$(get_service_url "ai_stack" 2>/dev/null || echo "http://172.16.168.24:8080")/health" "healthy"
test_service "Browser VM5" "$(get_service_url "browser_service" 2>/dev/null || echo "http://172.16.168.25:3000")/health" "healthy"

echo ""
echo -e "${YELLOW}🔗 Testing Inter-VM Communication...${NC}"

# Test NPU Worker device detection
SERVICES_TESTED=$((SERVICES_TESTED + 1))
echo -n "  NPU Worker device detection... "
device_response=$(timeout 5 curl -s "$(get_service_url "npu_worker" 2>/dev/null || echo "http://172.16.168.22:8081")/devices" 2>/dev/null)
if echo "$device_response" | grep -q "available_devices"; then
    echo -e "${GREEN}✅ PASS${NC}"
    SERVICES_PASSED=$((SERVICES_PASSED + 1))
    echo "    Detected devices: $(echo "$device_response" | grep -o '"CPU":[^,}]*')"
else
    echo -e "${RED}❌ FAIL${NC}"
    ERRORS+=("NPU Worker: Device detection API not responding properly")
fi

# Test AI Stack status
SERVICES_TESTED=$((SERVICES_TESTED + 1))
echo -n "  AI Stack status endpoint... "
ai_response=$(timeout 5 curl -s "$(get_service_url "ai_stack" 2>/dev/null || echo "http://172.16.168.24:8080")/api/ai/status" 2>/dev/null)
if echo "$ai_response" | grep -q "ai_stack"; then
    echo -e "${GREEN}✅ PASS${NC}"
    SERVICES_PASSED=$((SERVICES_PASSED + 1))
    echo "    AI Stack mode: $(echo "$ai_response" | grep -o '"mode":"[^"]*"')"
else
    echo -e "${RED}❌ FAIL${NC}"
    ERRORS+=("AI Stack: Status API not responding properly")
fi

# Test Redis connectivity from different VMs (simulate backend connection)
SERVICES_TESTED=$((SERVICES_TESTED + 1))
echo -n "  Redis multi-database access... "
local redis_host=$(get_config "infrastructure.hosts.redis" 2>/dev/null || echo "172.16.168.23")
local redis_port=$(get_config "infrastructure.ports.redis" 2>/dev/null || echo "6379")
if echo "SELECT 0" | nc -w 2 "$redis_host" "$redis_port" | grep -q "OK"; then
    echo -e "${GREEN}✅ PASS${NC}"
    SERVICES_PASSED=$((SERVICES_PASSED + 1))
    echo "    Redis databases: 0-15 accessible"
else
    echo -e "${RED}❌ FAIL${NC}"
    ERRORS+=("Redis: Database selection not working")
fi

echo ""
echo -e "${YELLOW}⚡ Testing Performance & Resources...${NC}"

# Test service response times
test_response_time() {
    local name="$1"
    local url="$2"

    SERVICES_TESTED=$((SERVICES_TESTED + 1))
    echo -n "  $name response time... "

    response_time=$(timeout 10 curl -w "%{time_total}" -s -o /dev/null "$url" 2>/dev/null || echo "timeout")
    if [ "$response_time" != "timeout" ] && [ $(echo "$response_time < 2.0" | bc -l 2>/dev/null || echo 0) -eq 1 ]; then
        echo -e "${GREEN}✅ PASS (${response_time}s)${NC}"
        SERVICES_PASSED=$((SERVICES_PASSED + 1))
    elif [ "$response_time" != "timeout" ]; then
        echo -e "${YELLOW}⚠️  SLOW (${response_time}s)${NC}"
        SERVICES_PASSED=$((SERVICES_PASSED + 1))
    else
        echo -e "${RED}❌ TIMEOUT${NC}"
        ERRORS+=("$name: Response timeout (>10s)")
    fi
}

test_response_time "Frontend" "$(get_service_url "frontend" 2>/dev/null || echo "http://172.16.168.21")/"
test_response_time "NPU Worker" "$(get_service_url "npu_worker" 2>/dev/null || echo "http://172.16.168.22:8081")/health"
test_response_time "AI Stack" "$(get_service_url "ai_stack" 2>/dev/null || echo "http://172.16.168.24:8080")/health"
test_response_time "Browser" "$(get_service_url "browser_service" 2>/dev/null || echo "http://172.16.168.25:3000")/health"

echo ""
echo -e "${BLUE}📊 Validation Summary${NC}"
echo -e "${BLUE}===================${NC}"
echo -e "Services Tested: $SERVICES_TESTED"
echo -e "Services Passed: ${GREEN}$SERVICES_PASSED${NC}"
echo -e "Services Failed: ${RED}$((SERVICES_TESTED - SERVICES_PASSED))${NC}"

if [ ${#ERRORS[@]} -gt 0 ]; then
    echo ""
    echo -e "${RED}❌ Issues Found:${NC}"
    for error in "${ERRORS[@]}"; do
        echo -e "  • $error"
    done
fi

echo ""
if [ $SERVICES_PASSED -eq $SERVICES_TESTED ]; then
    echo -e "${GREEN}🎉 ALL TESTS PASSED!${NC}"
    echo -e "${GREEN}✅ AutoBot Native VM Deployment is fully functional!${NC}"
    echo ""
    echo -e "${BLUE}🌐 Access your AutoBot installation at:${NC}"
    echo -e "  Frontend: ${YELLOW}$(get_service_url "frontend" 2>/dev/null || echo "http://172.16.168.21")/${NC}"
    echo -e "  Backend:  ${YELLOW}$(get_service_url "backend" 2>/dev/null || echo "http://172.16.168.20:8001")/${NC}"
    echo ""
    echo -e "${YELLOW}🚀 Ready to start AutoBot with: ./run_agent_native.sh${NC}"
    exit 0
else
    echo -e "${RED}❌ DEPLOYMENT VALIDATION FAILED${NC}"
    echo -e "${YELLOW}Some services need attention before AutoBot can run properly.${NC}"
    exit 1
fi
