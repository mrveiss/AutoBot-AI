#!/bin/bash
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# Test Bidirectional DNS Resolution

echo "🧪 Testing AutoBot DNS Resolution"
echo "=================================="

# Test 1: Host to Container Resolution
echo ""
echo "📡 HOST → CONTAINER Resolution:"
echo "------------------------------"

test_host_to_container() {
    local name=$1
    local port=$2
    local description=$3

    printf "%-30s " "$description:"
    if timeout 3 bash -c "echo >/dev/tcp/$name/$port" 2>/dev/null; then
        echo "✅ $name:$port reachable"
    else
        echo "❌ $name:$port failed"
    fi
}

test_host_to_container "autobot-redis" "6379" "Redis (full name)"
test_host_to_container "redis.autobot" "6379" "Redis (domain alias)"
test_host_to_container "redis" "6379" "Redis (short alias)"
test_host_to_container "autobot-frontend" "5173" "Frontend (full name)"
test_host_to_container "frontend.autobot" "5173" "Frontend (domain alias)"
test_host_to_container "frontend" "5173" "Frontend (short alias)"

# Test 2: Container to Host Resolution
echo ""
echo "📡 CONTAINER → HOST Resolution:"
echo "------------------------------"

test_container_to_host() {
    local container=$1
    local target=$2
    local port=$3
    local description=$4

    printf "%-30s " "$description:"
    if docker exec "$container" timeout 3 nc -z "$target" "$port" 2>/dev/null; then
        echo "✅ $target:$port reachable from $container"
    else
        echo "❌ $target:$port failed from $container"
    fi
}

# Test from frontend container
if docker ps --format '{{.Names}}' | grep -q "autobot-frontend"; then
    test_container_to_host "autobot-frontend" "host.docker.internal" "8001" "Backend (standard)"
    test_container_to_host "autobot-frontend" "backend.autobot" "8001" "Backend (alias)"
    test_container_to_host "autobot-frontend" "api.autobot" "8001" "API (alias)"
else
    echo "❌ Frontend container not running - cannot test container→host"
fi

# Test 3: Container to Container Resolution
echo ""
echo "📡 CONTAINER → CONTAINER Resolution:"
echo "-----------------------------------"

if docker ps --format '{{.Names}}' | grep -q "autobot-frontend"; then
    test_container_to_host "autobot-frontend" "redis" "6379" "Frontend→Redis (short)"
    test_container_to_host "autobot-frontend" "redis.autobot" "6379" "Frontend→Redis (domain)"
    test_container_to_host "autobot-frontend" "autobot-redis" "6379" "Frontend→Redis (full)"
else
    echo "❌ Frontend container not running - cannot test container→container"
fi

# Test 4: DNS Resolution (name to IP)
echo ""
echo "🔍 DNS Name Resolution:"
echo "----------------------"

resolve_name() {
    local name=$1
    printf "%-30s " "$name:"

    if ip=$(python3 -c "import socket; print(socket.gethostbyname('$name'))" 2>/dev/null); then
        echo "✅ $ip"
    else
        echo "❌ Failed to resolve"
    fi
}

resolve_name "host.docker.internal"
resolve_name "autobot-redis"
resolve_name "redis.autobot"
resolve_name "redis"
resolve_name "autobot-frontend"
resolve_name "frontend.autobot"
resolve_name "frontend"

# Test 5: Show current mappings
echo ""
echo "📋 Current DNS Mappings:"
echo "------------------------"

echo "Host /etc/hosts AutoBot entries:"
if grep -q "AutoBot DNS" /etc/hosts 2>/dev/null; then
    grep -A 20 "AutoBot DNS" /etc/hosts | grep -v "^#" | grep -v "^$" | head -10
else
    echo "  No AutoBot entries in /etc/hosts"
fi

echo ""
echo "Docker network aliases:"
if docker network inspect autobot-network >/dev/null 2>&1; then
    docker network inspect autobot-network | jq -r '.[] | .Containers | to_entries[] | "\(.value.Name) → \(.value.IPv4Address | split("/")[0])"' | head -10
else
    echo "  AutoBot network not found"
fi

echo ""
echo "🎯 Quick connectivity tests:"
echo "curl http://redis.autobot:6379 (if Redis web interface enabled)"
echo "curl http://frontend.autobot:5173/"
echo "docker exec autobot-frontend curl backend.autobot:8001/api/health"
