#!/bin/bash
# Configuration Loader for Shell Scripts
# Loads configuration from complete.yaml and provides helper functions

# Get the directory where this script is located (config/)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" &> /dev/null && pwd)"
CONFIG_FILE="${SCRIPT_DIR}/complete.yaml"

# Check if yq is available for YAML parsing
# NOTE: yq is installed automatically by setup_agent.sh in system dependencies
if ! command -v yq &> /dev/null; then
    echo "Warning: yq not found. Install with: sudo apt-get install yq" >&2
    echo "Note: yq should be installed by setup_agent.sh automatically" >&2
    echo "Falling back to hardcoded values for critical services" >&2
    YQ_AVAILABLE=false
else
    YQ_AVAILABLE=true
fi

# Function to get configuration value from complete.yaml
# Usage: get_config "infrastructure.hosts.backend"
get_config() {
    local key="$1"
    
    if [[ "$YQ_AVAILABLE" == "true" && -f "$CONFIG_FILE" ]]; then
        yq eval ".${key}" "$CONFIG_FILE" 2>/dev/null
    else
        # Fallback to hardcoded critical values if yq unavailable
        case "$key" in
            "infrastructure.hosts.backend") echo "172.16.168.20" ;;
            "infrastructure.hosts.frontend") echo "172.16.168.21" ;;
            "infrastructure.hosts.redis") echo "172.16.168.23" ;;
            "infrastructure.hosts.ollama") echo "localhost" ;;
            "infrastructure.hosts.ai_stack") echo "172.16.168.24" ;;
            "infrastructure.hosts.npu_worker") echo "172.16.168.22" ;;
            "infrastructure.hosts.browser_service") echo "172.16.168.25" ;;
            "infrastructure.ports.backend") echo "8001" ;;
            "infrastructure.ports.frontend") echo "5173" ;;
            "infrastructure.ports.redis") echo "6379" ;;
            "infrastructure.ports.ollama") echo "11434" ;;
            "infrastructure.ports.vnc") echo "6080" ;;
            "infrastructure.ports.websocket") echo "8001" ;;
            *) echo "null" ;;
        esac
    fi
}

# Function to build service URL
# Usage: get_service_url "backend" or get_service_url "redis"
get_service_url() {
    local service="$1"
    local protocol="${2:-http}"
    
    case "$service" in
        "backend")
            local host=$(get_config "infrastructure.hosts.backend")
            local port=$(get_config "infrastructure.ports.backend")
            echo "${protocol}://${host}:${port}"
            ;;
        "frontend")
            local host=$(get_config "infrastructure.hosts.frontend")
            local port=$(get_config "infrastructure.ports.frontend")
            echo "${protocol}://${host}:${port}"
            ;;
        "redis")
            local host=$(get_config "infrastructure.hosts.redis")
            local port=$(get_config "infrastructure.ports.redis")
            echo "redis://${host}:${port}"
            ;;
        "ollama")
            local host=$(get_config "infrastructure.hosts.ollama")
            local port=$(get_config "infrastructure.ports.ollama")
            echo "${protocol}://${host}:${port}"
            ;;
        "ai_stack")
            local host=$(get_config "infrastructure.hosts.ai_stack")
            local port=$(get_config "infrastructure.ports.ai_stack")
            echo "${protocol}://${host}:${port}"
            ;;
        "npu_worker")
            local host=$(get_config "infrastructure.hosts.npu_worker")
            local port=$(get_config "infrastructure.ports.npu_worker")
            echo "${protocol}://${host}:${port}"
            ;;
        "browser_service")
            local host=$(get_config "infrastructure.hosts.browser_service")
            local port=$(get_config "infrastructure.ports.browser_service")
            echo "${protocol}://${host}:${port}"
            ;;
        *)
            echo "Unknown service: $service" >&2
            return 1
            ;;
    esac
}

# Function to get timeout value
# Usage: get_timeout "llm.chat" or get_timeout "http.standard"
get_timeout() {
    local key="$1"
    get_config "timeouts.${key}"
}

# Function to get path configuration
# Usage: get_path "logs.directory" or get_path "data.knowledge_base"
get_path() {
    local key="$1"
    get_config "paths.${key}"
}

# Function to check if feature is enabled
# Usage: is_feature_enabled "semantic_chunking"
is_feature_enabled() {
    local feature="$1"
    local enabled=$(get_config "features.${feature}")
    [[ "$enabled" == "true" ]]
}

# Function to get network configuration
get_network_config() {
    echo "Network Configuration:"
    echo "  Backend:      $(get_service_url "backend")"
    echo "  Frontend:     $(get_service_url "frontend")"
    echo "  Redis:        $(get_service_url "redis")"
    echo "  Ollama:       $(get_service_url "ollama")"
    echo "  AI Stack:     $(get_service_url "ai_stack")"
    echo "  NPU Worker:   $(get_service_url "npu_worker")"
    echo "  Browser:      $(get_service_url "browser_service")"
}

# Function to export all infrastructure variables for scripts
export_infrastructure_vars() {
    export BACKEND_HOST=$(get_config "infrastructure.hosts.backend")
    export FRONTEND_HOST=$(get_config "infrastructure.hosts.frontend")
    export REDIS_HOST=$(get_config "infrastructure.hosts.redis")
    export OLLAMA_HOST=$(get_config "infrastructure.hosts.ollama")
    export AI_STACK_HOST=$(get_config "infrastructure.hosts.ai_stack")
    export NPU_WORKER_HOST=$(get_config "infrastructure.hosts.npu_worker")
    export BROWSER_SERVICE_HOST=$(get_config "infrastructure.hosts.browser_service")
    
    export BACKEND_PORT=$(get_config "infrastructure.ports.backend")
    export FRONTEND_PORT=$(get_config "infrastructure.ports.frontend")
    export REDIS_PORT=$(get_config "infrastructure.ports.redis")
    export OLLAMA_PORT=$(get_config "infrastructure.ports.ollama")
    export AI_STACK_PORT=$(get_config "infrastructure.ports.ai_stack")
    export NPU_WORKER_PORT=$(get_config "infrastructure.ports.npu_worker")
    export BROWSER_SERVICE_PORT=$(get_config "infrastructure.ports.browser_service")
    export VNC_PORT=$(get_config "infrastructure.ports.vnc")
    export WEBSOCKET_PORT=$(get_config "infrastructure.ports.websocket")
    
    # Service URLs
    export BACKEND_URL=$(get_service_url "backend")
    export FRONTEND_URL=$(get_service_url "frontend")
    export REDIS_URL=$(get_service_url "redis")
    export OLLAMA_URL=$(get_service_url "ollama")
    export AI_STACK_URL=$(get_service_url "ai_stack")
    export NPU_WORKER_URL=$(get_service_url "npu_worker")
    export BROWSER_SERVICE_URL=$(get_service_url "browser_service")
}

# Function to validate configuration loading
validate_config() {
    local errors=0
    
    echo "Validating configuration loading..."
    
    # Test critical service URLs
    local services=("backend" "frontend" "redis" "ollama")
    for service in "${services[@]}"; do
        local url=$(get_service_url "$service")
        if [[ "$url" == *"null"* || -z "$url" ]]; then
            echo "ERROR: Failed to load $service URL" >&2
            ((errors++))
        else
            echo "✓ $service: $url"
        fi
    done
    
    # Test timeout configurations
    local timeout=$(get_timeout "llm.chat")
    if [[ "$timeout" == "null" || -z "$timeout" ]]; then
        echo "ERROR: Failed to load timeout configuration" >&2
        ((errors++))
    else
        echo "✓ LLM chat timeout: ${timeout}s"
    fi
    
    if [[ $errors -eq 0 ]]; then
        echo "✓ Configuration loading validated successfully"
        return 0
    else
        echo "✗ Configuration loading failed with $errors errors"
        return 1
    fi
}

# Auto-export infrastructure variables when script is sourced
if [[ "${BASH_SOURCE[0]}" != "${0}" ]]; then
    # Script is being sourced, not executed directly
    export_infrastructure_vars
fi

# Show configuration if run directly
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    echo "Configuration Loader - Direct Execution Mode"
    echo "============================================="
    echo
    get_network_config
    echo
    validate_config
    echo
    echo "To use in other scripts:"
    echo "  source config/load_config.sh"
    echo "  BACKEND_URL=\$(get_service_url 'backend')"
    echo "  TIMEOUT=\$(get_timeout 'llm.chat')"
fi