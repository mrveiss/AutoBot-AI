#!/bin/bash
# AutoBot Common Functions
# Shared utility functions across all agent containers
# Eliminates duplicate utility code patterns

# Utility functions for agent containers
get_container_ip() {
    hostname -i 2>/dev/null || echo "127.0.0.1"
}

get_memory_usage() {
    python -c "import psutil; print(f'{psutil.virtual_memory().percent:.1f}')" 2>/dev/null || echo "unknown"
}

get_cpu_usage() {
    python -c "import psutil; print(f'{psutil.cpu_percent(interval=1):.1f}')" 2>/dev/null || echo "unknown"
}

get_disk_usage() {
    python -c "import psutil; print(f'{psutil.disk_usage(\"/\").percent:.1f}')" 2>/dev/null || echo "unknown"
}

# Network utilities
test_connection() {
    local host=$1
    local port=$2
    local timeout=${3:-5}

    timeout "$timeout" bash -c "</dev/tcp/$host/$port" 2>/dev/null
}

wait_for_redis() {
    local host="${REDIS_HOST:-autobot-redis}"
    local port="${REDIS_PORT:-6379}"
    local timeout=${1:-60}

    echo "Waiting for Redis at $host:$port..."

    for ((i=0; i<timeout; i++)); do
        if test_connection "$host" "$port" 1; then
            echo "✅ Redis is available"
            return 0
        fi
        sleep 1
        echo -n "."
    done

    echo "❌ Redis not available after ${timeout}s"
    return 1
}

# Configuration utilities
load_agent_config() {
    local config_file="${1:-/app/config/agent.yaml}"

    if [[ -f "$config_file" ]]; then
        echo "Loading configuration from $config_file"
        # Export environment variables from YAML (basic parsing)
        while IFS='=' read -r key value; do
            if [[ -n "$key" && -n "$value" ]]; then
                export "$key=$value"
            fi
        done < <(python -c "
import yaml, os
try:
    with open('$config_file') as f:
        config = yaml.safe_load(f)
    for k, v in config.items():
        if isinstance(v, (str, int, bool)):
            print(f'{k}={v}')
except Exception as e:
    print(f'# Error loading config: {e}', file=sys.stderr)
" 2>/dev/null)
    fi
}

# Health check utilities
basic_health_check() {
    local checks_passed=0
    local total_checks=4

    # Check 1: Process is running
    if pgrep -f "python.*main.py" >/dev/null; then
        ((checks_passed++))
    fi

    # Check 2: Port is listening
    if netstat -ln 2>/dev/null | grep -q ":${HEALTH_CHECK_PORT:-8000}"; then
        ((checks_passed++))
    fi

    # Check 3: Memory usage reasonable
    local mem_usage
    mem_usage=$(get_memory_usage)
    if [[ "$mem_usage" != "unknown" ]] && (( $(echo "$mem_usage < 95" | bc -l 2>/dev/null || echo 1) )); then
        ((checks_passed++))
    fi

    # Check 4: Disk space available
    local disk_usage
    disk_usage=$(get_disk_usage)
    if [[ "$disk_usage" != "unknown" ]] && (( $(echo "$disk_usage < 95" | bc -l 2>/dev/null || echo 1) )); then
        ((checks_passed++))
    fi

    # Return health status
    if (( checks_passed >= 3 )); then
        return 0  # Healthy
    else
        return 1  # Unhealthy
    fi
}

# Logging utilities
setup_logging() {
    local log_level="${LOG_LEVEL:-INFO}"
    local log_file="${LOG_FILE:-/app/logs/agent.log}"

    # Create log directory if it doesn't exist
    mkdir -p "$(dirname "$log_file")"

    # Set up log rotation if logrotate is available
    if command -v logrotate >/dev/null; then
        cat > /tmp/logrotate.conf << EOF
$log_file {
    daily
    rotate 7
    compress
    delaycompress
    missingok
    notifempty
    copytruncate
}
EOF
    fi
}

# Prometheus metrics utilities (if prometheus-client is available)
expose_metrics() {
    local metrics_port="${METRICS_PORT:-9090}"

    python -c "
import time
import psutil
from prometheus_client import start_http_server, Gauge, Counter

# Create metrics
cpu_usage = Gauge('agent_cpu_usage_percent', 'CPU usage percentage')
memory_usage = Gauge('agent_memory_usage_percent', 'Memory usage percentage')
disk_usage = Gauge('agent_disk_usage_percent', 'Disk usage percentage')
requests_total = Counter('agent_requests_total', 'Total requests processed')

# Start metrics server
start_http_server($metrics_port)
print(f'Metrics server started on port $metrics_port')

# Update metrics loop
while True:
    try:
        cpu_usage.set(psutil.cpu_percent(interval=1))
        memory_usage.set(psutil.virtual_memory().percent)
        disk_usage.set(psutil.disk_usage('/').percent)
        time.sleep(30)
    except KeyboardInterrupt:
        break
    except Exception as e:
        print(f'Metrics error: {e}')
        time.sleep(30)
" 2>/dev/null &
}

# Container introspection
get_container_info() {
    echo "Container Information:"
    echo "  User: $(whoami)"
    echo "  Home: ${HOME:-unknown}"
    echo "  Working Dir: $(pwd)"
    echo "  Python Path: ${PYTHONPATH:-default}"
    echo "  Agent Type: ${AGENT_TYPE:-unknown}"
    echo "  Container IP: $(get_container_ip)"
    echo "  Memory Usage: $(get_memory_usage)%"
    echo "  CPU Usage: $(get_cpu_usage)%"
    echo "  Disk Usage: $(get_disk_usage)%"
}

# Emergency debugging
debug_container() {
    echo "=== CONTAINER DEBUG INFO ==="
    get_container_info
    echo ""

    echo "=== ENVIRONMENT ==="
    env | grep -E "(AUTOBOT|REDIS|OLLAMA|PYTHON)" | sort
    echo ""

    echo "=== NETWORK ==="
    netstat -ln 2>/dev/null | head -20 || ss -ln 2>/dev/null | head -20 || echo "No network info available"
    echo ""

    echo "=== PROCESSES ==="
    ps aux | head -10
    echo ""

    echo "=== DISK SPACE ==="
    df -h / /tmp /app 2>/dev/null || echo "Disk info not available"
    echo ""

    echo "=== RECENT LOGS ==="
    if [[ -f "/app/logs/agent.log" ]]; then
        tail -20 "/app/logs/agent.log"
    else
        echo "No log file found at /app/logs/agent.log"
    fi
}
