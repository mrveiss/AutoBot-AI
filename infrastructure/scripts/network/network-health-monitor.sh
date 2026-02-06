#!/bin/bash
# AutoBot Network Health Monitoring Script
# Monitors all critical network services and provides health status

set -e

# Source network configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/network-config.sh"

echo ""
echo "🔍 AutoBot Network Health Monitor"
echo "=================================="
echo "Timestamp: $(date)"
echo ""

# Function to test service availability
test_service() {
    local name="$1"
    local url="$2"
    local expected_status="$3"
    local timeout="${4:-5}"

    echo -n "📡 $name: "

    if response=$(curl -s -w "%{http_code}" --connect-timeout "$timeout" --max-time "$timeout" "$url" 2>/dev/null); then
        status_code="${response: -3}"
        if [ "$status_code" = "$expected_status" ]; then
            echo "✅ HEALTHY ($status_code)"
            return 0
        else
            echo "⚠️  DEGRADED ($status_code, expected $expected_status)"
            return 1
        fi
    else
        echo "❌ FAILED (connection timeout or error)"
        return 2
    fi
}

# Function to test port connectivity
test_port() {
    local name="$1"
    local host="$2"
    local port="$3"
    local timeout="${4:-3}"

    echo -n "🔌 $name (${host}:${port}): "

    if timeout "$timeout" bash -c "echo >/dev/tcp/$host/$port" 2>/dev/null; then
        echo "✅ LISTENING"
        return 0
    else
        echo "❌ NOT ACCESSIBLE"
        return 1
    fi
}

# Core Services Health Check
echo "🌐 Core Services Status:"
echo "------------------------"

# Test HTTP endpoints using environment variables
test_service "Backend API" "${BACKEND_URL}/api/health" "200"
test_service "Frontend" "${FRONTEND_URL}" "200"
test_service "VNC Web Interface" "${VNC_WEB_URL}/vnc.html" "200"
test_service "AI Stack" "${AI_STACK_URL}/health" "200"
test_service "NPU Worker" "${NPU_WORKER_URL}/health" "200"
test_service "Browser Service" "${BROWSER_URL}/health" "200"

echo ""
echo "🔗 Port Connectivity Status:"
echo "-----------------------------"

# Test port connectivity using environment variables
test_port "Redis" "${REDIS_HOST}" "${REDIS_PORT}"
test_port "VNC Server" "${VNC_SERVER_HOST}" "${VNC_SERVER_PORT}"
test_port "Backend API" "${BACKEND_HOST}" "${BACKEND_PORT}"

echo ""
echo "📊 Network Performance Metrics:"
echo "--------------------------------"

# Network latency tests using environment variables
echo -n "⏱️  Backend API Latency: "
if latency=$(curl -w "%{time_total}" -s -o /dev/null "${BACKEND_URL}/api/health" 2>/dev/null); then
    echo "${latency}s"
else
    echo "Failed to measure"
fi

echo -n "⏱️  Frontend Latency: "
if latency=$(curl -w "%{time_total}" -s -o /dev/null "${FRONTEND_URL}" 2>/dev/null); then
    echo "${latency}s"
else
    echo "Failed to measure"
fi

echo ""
echo "🐳 Container Health Status:"
echo "---------------------------"

# Docker container health
if command -v docker >/dev/null 2>&1; then
    docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}" | grep autobot | while read -r line; do
        name=$(echo "$line" | awk '{print $1}')
        status=$(echo "$line" | awk '{print $2,$3}')
        if [[ "$status" == *"healthy"* ]]; then
            echo "✅ $name: $status"
        elif [[ "$status" == *"Up"* ]]; then
            echo "⚠️  $name: $status (no health check)"
        else
            echo "❌ $name: $status"
        fi
    done
else
    echo "⚠️  Docker not available"
fi

echo ""
echo "🛡️ Security Status:"
echo "-------------------"

# VNC Security Check
echo -n "🔒 VNC Server Binding: "
if netstat -tuln | grep ":5902" | grep -q "127.0.0.1\|::1"; then
    echo "✅ SECURE (localhost only)"
else
    if netstat -tuln | grep -q ":5902"; then
        echo "⚠️  EXPOSED (not localhost-bound)"
    else
        echo "❌ NOT RUNNING"
    fi
fi

echo -n "🔒 noVNC Proxy: "
if netstat -tuln | grep -q ":6080"; then
    echo "✅ RUNNING (check access controls)"
else
    echo "❌ NOT RUNNING"
fi

# Process count check
echo ""
echo "⚙️ Process Status:"
echo "------------------"

vnc_count=$(ps aux | grep -E "(Xvnc|vnc)" | grep -v grep | wc -l)
websockify_count=$(ps aux | grep websockify | grep -v grep | wc -l)

echo "🖥️  VNC Processes: $vnc_count"
echo "🌐 WebSocket Proxies: $websockify_count"

if [ "$websockify_count" -gt 1 ]; then
    echo "⚠️  Multiple websockify processes detected"
fi

echo ""
echo "📈 System Resources:"
echo "--------------------"

# System resource usage
echo -n "💾 Memory Usage: "
free -h | awk 'NR==2{printf "%.1f%% (%s used of %s)\n", $3*100/$2, $3, $2}'

echo -n "💽 Disk Usage: "
df -h / | awk 'NR==2{print $5 " (" $3 " used of " $2 ")"}'

echo -n "🔥 Load Average: "
uptime | awk -F'load average:' '{print $2}' | sed 's/^[ \t]*//'

echo ""
echo "=================================="
echo "🏁 Network Health Check Complete"
echo "Timestamp: $(date)"
echo ""
