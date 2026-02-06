#!/bin/bash
# Comprehensive Heroicons Dependency Test Suite
# Tests all AutoBot execution modes to ensure Heroicons works everywhere

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Test configuration
TEST_TIMEOUT=60
CONTAINER_NAME="autobot-frontend"

echo -e "${BLUE}=======================================================${NC}"
echo -e "${BLUE}🧪 AutoBot Heroicons Comprehensive Test Suite${NC}"
echo -e "${BLUE}=======================================================${NC}"
echo ""

# Function to cleanup before each test
cleanup_test() {
    echo -e "${YELLOW}🧹 Cleaning up for next test...${NC}"

    # Stop all AutoBot services
    docker compose -f docker-compose.yml down >/dev/null 2>&1 || true

    # Remove frontend containers specifically
    docker rm -f $CONTAINER_NAME >/dev/null 2>&1 || true

    # Kill any backend processes
    pkill -f "uvicorn.*backend" >/dev/null 2>&1 || true

    sleep 2
}

# Function to check if Heroicons is accessible in container
check_heroicons_in_container() {
    local container_name=$1
    local test_name=$2

    echo -e "${YELLOW}   🔍 Testing Heroicons accessibility in $test_name...${NC}"

    # Wait for container to be fully up
    local retries=0
    while [ $retries -lt 10 ]; do
        if docker exec $container_name ls /app/node_modules/@heroicons/vue >/dev/null 2>&1; then
            break
        fi
        sleep 2
        retries=$((retries + 1))
    done

    # Test 1: Directory exists
    if docker exec $container_name ls -la /app/node_modules/@heroicons/vue >/dev/null 2>&1; then
        echo -e "      ✅ @heroicons/vue directory exists"
    else
        echo -e "      ❌ @heroicons/vue directory missing"
        return 1
    fi

    # Test 2: Package.json exists and is readable
    if docker exec $container_name cat /app/node_modules/@heroicons/vue/package.json >/dev/null 2>&1; then
        echo -e "      ✅ package.json is readable"
    else
        echo -e "      ❌ package.json is not readable"
        return 1
    fi

    # Test 3: Main index files exist
    if docker exec $container_name ls /app/node_modules/@heroicons/vue/index.js >/dev/null 2>&1; then
        echo -e "      ✅ index.js exists"
    else
        echo -e "      ❌ index.js missing"
        return 1
    fi

    # Test 4: Icon directories exist
    if docker exec $container_name ls /app/node_modules/@heroicons/vue/outline >/dev/null 2>&1; then
        echo -e "      ✅ outline icons directory exists"
    else
        echo -e "      ❌ outline icons directory missing"
        return 1
    fi

    if docker exec $container_name ls /app/node_modules/@heroicons/vue/solid >/dev/null 2>&1; then
        echo -e "      ✅ solid icons directory exists"
    else
        echo -e "      ❌ solid icons directory missing"
        return 1
    fi

    # Test 5: Node.js can require the package
    if docker exec $container_name node -e "require('@heroicons/vue')" >/dev/null 2>&1; then
        echo -e "      ✅ Node.js can require @heroicons/vue"
    else
        echo -e "      ❌ Node.js cannot require @heroicons/vue"
        return 1
    fi

    return 0
}

# Function to check if frontend application is responding
check_frontend_health() {
    local retries=0
    local max_retries=30

    echo -e "${YELLOW}   🔍 Waiting for frontend to be healthy...${NC}"

    while [ $retries -lt $max_retries ]; do
        if docker exec $CONTAINER_NAME wget -q --spider http://localhost:5173 2>/dev/null; then
            echo -e "      ✅ Frontend is responding"
            return 0
        fi
        sleep 2
        retries=$((retries + 1))
        echo -e "      ⏳ Attempt $((retries + 1))/$max_retries..."
    done

    echo -e "      ❌ Frontend failed to respond after $max_retries attempts"
    return 1
}

# Test 1: Production Mode (Built Image)
test_production_mode() {
    echo -e "${GREEN}📦 Test 1: Production Mode (Built Image)${NC}"
    echo -e "   Testing: Built-in dependencies in production image"

    cleanup_test

    # Build production image and start container
    echo -e "${YELLOW}   🔨 Building production image...${NC}"
    docker compose build --no-cache frontend

    echo -e "${YELLOW}   🚀 Starting production container...${NC}"
    NODE_ENV=production AUTOBOT_EXECUTION_MODE=production docker compose up -d frontend

    # Wait for container to be ready
    sleep 10

    # Test Heroicons
    if check_heroicons_in_container $CONTAINER_NAME "Production Mode"; then
        echo -e "   ${GREEN}✅ Production Mode: PASSED${NC}"
        return 0
    else
        echo -e "   ${RED}❌ Production Mode: FAILED${NC}"
        return 1
    fi
}

# Test 2: Development Mode (Source Mounted)
test_development_mode() {
    echo -e "${GREEN}📦 Test 2: Development Mode (Source Mounted)${NC}"
    echo -e "   Testing: Volume-mounted source with node_modules overlay"

    cleanup_test

    # Start development container
    echo -e "${YELLOW}   🚀 Starting development container...${NC}"
    NODE_ENV=development AUTOBOT_EXECUTION_MODE=development docker compose up -d frontend

    # Wait for container to be ready
    sleep 15

    # Test Heroicons
    if check_heroicons_in_container $CONTAINER_NAME "Development Mode"; then
        echo -e "   ${GREEN}✅ Development Mode: PASSED${NC}"
        return 0
    else
        echo -e "   ${RED}❌ Development Mode: FAILED${NC}"
        return 1
    fi
}

# Test 3: Container Rebuild (Fresh Build)
test_container_rebuild() {
    echo -e "${GREEN}📦 Test 3: Container Rebuild (Fresh Build)${NC}"
    echo -e "   Testing: Complete container rebuild from scratch"

    cleanup_test

    # Remove existing images
    echo -e "${YELLOW}   🗑️  Removing existing frontend image...${NC}"
    docker rmi autobot-frontend:latest >/dev/null 2>&1 || true

    # Remove named volume
    echo -e "${YELLOW}   🗑️  Removing node_modules volume...${NC}"
    docker volume rm autobot_frontend_node_modules >/dev/null 2>&1 || true

    # Force rebuild
    echo -e "${YELLOW}   🔨 Force rebuilding with --no-cache...${NC}"
    docker compose build --no-cache frontend

    echo -e "${YELLOW}   🚀 Starting rebuilt container...${NC}"
    docker compose up -d frontend

    # Wait for container to be ready
    sleep 15

    # Test Heroicons
    if check_heroicons_in_container $CONTAINER_NAME "Container Rebuild"; then
        echo -e "   ${GREEN}✅ Container Rebuild: PASSED${NC}"
        return 0
    else
        echo -e "   ${RED}❌ Container Rebuild: FAILED${NC}"
        return 1
    fi
}

# Test 4: Fresh Install (Clean Environment)
test_fresh_install() {
    echo -e "${GREEN}📦 Test 4: Fresh Install (Clean Environment)${NC}"
    echo -e "   Testing: Complete clean slate scenario"

    cleanup_test

    # Remove all AutoBot Docker resources
    echo -e "${YELLOW}   🗑️  Cleaning entire AutoBot Docker environment...${NC}"
    docker system prune -f >/dev/null 2>&1 || true

    # Remove all AutoBot images
    docker images | grep autobot | awk '{print $3}' | xargs docker rmi -f >/dev/null 2>&1 || true

    # Remove all AutoBot volumes
    docker volume ls | grep autobot | awk '{print $2}' | xargs docker volume rm >/dev/null 2>&1 || true

    # Fresh build and start
    echo -e "${YELLOW}   🔨 Fresh build from clean environment...${NC}"
    docker compose build frontend

    echo -e "${YELLOW}   🚀 Starting fresh container...${NC}"
    docker compose up -d frontend

    # Wait for container to be ready
    sleep 20

    # Test Heroicons
    if check_heroicons_in_container $CONTAINER_NAME "Fresh Install"; then
        echo -e "   ${GREEN}✅ Fresh Install: PASSED${NC}"
        return 0
    else
        echo -e "   ${RED}❌ Fresh Install: FAILED${NC}"
        return 1
    fi
}

# Test 5: Direct Docker Compose (No Script)
test_direct_compose() {
    echo -e "${GREEN}📦 Test 5: Direct Docker Compose (No Script)${NC}"
    echo -e "   Testing: Direct docker compose up without unified script"

    cleanup_test

    # Start with direct docker compose command
    echo -e "${YELLOW}   🚀 Starting with direct docker compose up...${NC}"
    docker compose up -d frontend >/dev/null 2>&1

    # Wait for container to be ready
    sleep 15

    # Test Heroicons
    if check_heroicons_in_container $CONTAINER_NAME "Direct Compose"; then
        echo -e "   ${GREEN}✅ Direct Compose: PASSED${NC}"
        return 0
    else
        echo -e "   ${RED}❌ Direct Compose: FAILED${NC}"
        return 1
    fi
}

# Test 6: Frontend Application Health
test_application_health() {
    echo -e "${GREEN}📦 Test 6: Frontend Application Health${NC}"
    echo -e "   Testing: Frontend application can start and respond"

    # Don't cleanup - use current running container

    # Test frontend health
    if check_frontend_health; then
        echo -e "   ${GREEN}✅ Application Health: PASSED${NC}"
        return 0
    else
        echo -e "   ${RED}❌ Application Health: FAILED${NC}"
        return 1
    fi
}

# Main test execution
main() {
    local failed_tests=0
    local total_tests=6

    echo -e "${BLUE}Starting comprehensive test suite...${NC}"
    echo ""

    # Test 1: Production Mode
    if ! test_production_mode; then
        failed_tests=$((failed_tests + 1))
    fi
    echo ""

    # Test 2: Development Mode
    if ! test_development_mode; then
        failed_tests=$((failed_tests + 1))
    fi
    echo ""

    # Test 3: Container Rebuild
    if ! test_container_rebuild; then
        failed_tests=$((failed_tests + 1))
    fi
    echo ""

    # Test 4: Fresh Install
    if ! test_fresh_install; then
        failed_tests=$((failed_tests + 1))
    fi
    echo ""

    # Test 5: Direct Compose
    if ! test_direct_compose; then
        failed_tests=$((failed_tests + 1))
    fi
    echo ""

    # Test 6: Application Health
    if ! test_application_health; then
        failed_tests=$((failed_tests + 1))
    fi
    echo ""

    # Final cleanup
    cleanup_test

    # Report results
    echo -e "${BLUE}=======================================================${NC}"
    echo -e "${BLUE}📊 Test Results Summary${NC}"
    echo -e "${BLUE}=======================================================${NC}"

    local passed_tests=$((total_tests - failed_tests))
    echo -e "Total Tests: $total_tests"
    echo -e "${GREEN}Passed: $passed_tests${NC}"
    if [ $failed_tests -gt 0 ]; then
        echo -e "${RED}Failed: $failed_tests${NC}"
    else
        echo -e "${GREEN}Failed: $failed_tests${NC}"
    fi
    echo ""

    if [ $failed_tests -eq 0 ]; then
        echo -e "${GREEN}🎉 ALL TESTS PASSED!${NC}"
        echo -e "${GREEN}Heroicons dependency works in ALL execution modes.${NC}"
        exit 0
    else
        echo -e "${RED}❌ SOME TESTS FAILED!${NC}"
        echo -e "${RED}Heroicons dependency needs further fixes.${NC}"
        exit 1
    fi
}

# Run main function
main "$@"
