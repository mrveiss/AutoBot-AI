#!/bin/bash
# AutoBot Standardized Agent Entrypoint
# Eliminates duplicate startup patterns across 8+ containers
# Provides consistent initialization, validation, and startup sequence

set -euo pipefail

# Source common functions
source "$(dirname "$0")/common-functions.sh"

# Configuration
SCRIPT_NAME="$(basename "$0")"
LOG_PREFIX="[${AUTOBOT_USER:-autobot}]"

# Default values (can be overridden by environment)
HEALTH_CHECK_PORT="${HEALTH_CHECK_PORT:-8000}"
STARTUP_TIMEOUT="${STARTUP_TIMEOUT:-120}"
DEPENDENCY_CHECK_TIMEOUT="${DEPENDENCY_CHECK_TIMEOUT:-60}"

# Logging functions
log_info() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') ${LOG_PREFIX} INFO: $*" >&1
}

log_warn() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') ${LOG_PREFIX} WARN: $*" >&2
}

log_error() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') ${LOG_PREFIX} ERROR: $*" >&2
}

# Signal handlers for graceful shutdown
cleanup() {
    log_info "Received termination signal, shutting down gracefully..."

    # Kill background processes
    if [[ -n "${HEALTH_MONITOR_PID:-}" ]]; then
        kill -TERM "${HEALTH_MONITOR_PID}" 2>/dev/null || true
    fi

    # Run agent-specific cleanup if defined
    if declare -f agent_cleanup >/dev/null; then
        log_info "Running agent-specific cleanup..."
        agent_cleanup || log_warn "Agent cleanup failed"
    fi

    log_info "Shutdown complete"
    exit 0
}

trap cleanup TERM INT

# Startup sequence
main() {
    log_info "🚀 Starting AutoBot Agent Container"
    log_info "Agent Type: ${AGENT_TYPE:-unknown}"
    log_info "User: $(whoami), Home: ${HOME:-/app}"
    log_info "Python Path: ${PYTHONPATH:-default}"

    # Step 1: Validate environment
    log_info "📋 Step 1: Validating environment..."
    validate_environment || {
        log_error "Environment validation failed"
        exit 1
    }

    # Step 2: Check dependencies
    log_info "🔗 Step 2: Checking dependencies..."
    check_dependencies || {
        log_error "Dependency check failed"
        exit 1
    }

    # Step 3: Initialize data volumes
    log_info "📁 Step 3: Initializing data volumes..."
    initialize_volumes || {
        log_error "Volume initialization failed"
        exit 1
    }

    # Step 4: Agent-specific initialization
    log_info "⚙️  Step 4: Running agent-specific initialization..."
    if declare -f agent_init >/dev/null; then
        agent_init || {
            log_error "Agent initialization failed"
            exit 1
        }
    else
        log_info "No agent-specific initialization defined"
    fi

    # Step 5: Start health monitoring
    log_info "❤️  Step 5: Starting health monitoring..."
    start_health_monitor &
    HEALTH_MONITOR_PID=$!

    # Step 6: Wait for readiness
    log_info "⏳ Step 6: Waiting for agent readiness..."
    wait_for_readiness || {
        log_error "Agent failed to become ready within timeout"
        exit 1
    }

    log_info "✅ Agent startup complete, executing main process..."
    log_info "Command: $*"

    # Execute the main process
    exec "$@"
}

# Environment validation (standardizes duplicate patterns)
validate_environment() {
    local errors=0

    # Check required environment variables
    local required_vars=(
        "PYTHONPATH"
        "AUTOBOT_USER"
    )

    for var in "${required_vars[@]}"; do
        if [[ -z "${!var:-}" ]]; then
            log_error "Required environment variable $var is not set"
            ((errors++))
        fi
    done

    # Check required directories
    local required_dirs=(
        "/app"
        "/app/data"
        "/app/logs"
    )

    for dir in "${required_dirs[@]}"; do
        if [[ ! -d "$dir" ]]; then
            log_warn "Required directory $dir does not exist, creating..."
            mkdir -p "$dir" || {
                log_error "Failed to create directory $dir"
                ((errors++))
            }
        fi
    done

    # Check write permissions
    if [[ ! -w "/app/data" ]]; then
        log_error "No write permission to /app/data"
        ((errors++))
    fi

    if [[ ! -w "/app/logs" ]]; then
        log_error "No write permission to /app/logs"
        ((errors++))
    fi

    return $errors
}

# Dependency checking (consolidates duplicate Redis/DB checks)
check_dependencies() {
    local timeout=$DEPENDENCY_CHECK_TIMEOUT
    local redis_host="${REDIS_HOST:-autobot-redis}"
    local redis_port="${REDIS_PORT:-6379}"

    # Check Redis if configured
    if [[ -n "${REDIS_HOST:-}" ]]; then
        log_info "Checking Redis connection to ${redis_host}:${redis_port}..."
        if ! wait_for_service "${redis_host}" "${redis_port}" "$timeout"; then
            log_error "Redis is not available at ${redis_host}:${redis_port}"
            return 1
        fi
        log_info "✅ Redis connection verified"
    fi

    # Check Ollama if configured
    if [[ -n "${OLLAMA_HOST:-}" ]]; then
        local ollama_url="${OLLAMA_HOST}/api/tags"
        log_info "Checking Ollama connection to ${OLLAMA_HOST}..."
        if ! curl -f -s --max-time 10 "$ollama_url" >/dev/null; then
            log_warn "Ollama is not available at ${OLLAMA_HOST} (continuing anyway)"
        else
            log_info "✅ Ollama connection verified"
        fi
    fi

    return 0
}

# Volume initialization (standardizes data directory setup)
initialize_volumes() {
    # Initialize prompts
    if [[ -d "/app/prompts" ]]; then
        local prompt_count=$(find /app/prompts -name "*.md" -o -name "*.txt" | wc -l)
        log_info "📝 Found $prompt_count prompt files"

        if [[ $prompt_count -eq 0 ]]; then
            log_warn "No prompt files found in /app/prompts"
        fi
    else
        log_warn "Prompts directory /app/prompts not found"
    fi

    # Initialize knowledge base
    if [[ -d "/app/knowledge_base" ]]; then
        local kb_count=$(find /app/knowledge_base -name "*.md" -o -name "*.txt" | wc -l)
        log_info "📚 Found $kb_count knowledge base documents"

        # Load knowledge base if script exists and enabled
        if [[ -f "/app/knowledge_base/load_to_db.py" ]] && [[ "${LOAD_KNOWLEDGE_BASE:-true}" == "true" ]]; then
            log_info "Loading knowledge base into vector database..."
            python /app/knowledge_base/load_to_db.py || {
                log_warn "Failed to load knowledge base (continuing anyway)"
            }
        fi
    else
        log_warn "Knowledge base directory /app/knowledge_base not found"
    fi

    # Initialize models directory
    if [[ -d "/app/models" ]]; then
        log_info "🤖 Models directory initialized"
    fi

    return 0
}

# Health monitoring (eliminates duplicate health check patterns)
start_health_monitor() {
    while true; do
        sleep 30

        # Basic health check
        if ! curl -f -s "http://localhost:${HEALTH_CHECK_PORT}/health" >/dev/null 2>&1; then
            log_warn "Health check failed for port ${HEALTH_CHECK_PORT}"
        fi

        # Memory usage check
        local memory_usage
        memory_usage=$(python -c "import psutil; print(psutil.virtual_memory().percent)" 2>/dev/null || echo "unknown")
        if [[ "$memory_usage" != "unknown" ]] && (( $(echo "$memory_usage > 90" | bc -l) )); then
            log_warn "High memory usage: ${memory_usage}%"
        fi

    done
}

# Wait for service availability
wait_for_service() {
    local host=$1
    local port=$2
    local timeout=$3
    local elapsed=0

    while ! nc -z "$host" "$port" 2>/dev/null; do
        if (( elapsed >= timeout )); then
            return 1
        fi
        sleep 2
        ((elapsed += 2))
    done

    return 0
}

# Wait for agent readiness
wait_for_readiness() {
    local timeout=$STARTUP_TIMEOUT
    local elapsed=0

    while ! curl -f -s "http://localhost:${HEALTH_CHECK_PORT}/health" >/dev/null 2>&1; do
        if (( elapsed >= timeout )); then
            log_error "Agent failed to become ready within ${timeout}s"
            return 1
        fi
        sleep 5
        ((elapsed += 5))
        log_info "Waiting for agent to be ready... (${elapsed}s/${timeout}s)"
    done

    log_info "✅ Agent is ready and responding to health checks"
    return 0
}

# Agent-specific functions can be defined in derived images
# These are optional and will be called if they exist:
# - agent_init(): Custom initialization logic
# - agent_cleanup(): Custom cleanup logic

# Run main function
main "$@"
