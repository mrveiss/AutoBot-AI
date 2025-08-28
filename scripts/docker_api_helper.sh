#!/bin/bash
# Docker API version detection and compatibility helper

detect_docker_api_version() {
    # Get the Docker server API version
    local server_version=$(docker version --format '{{.Server.APIVersion}}' 2>/dev/null)
    
    if [ -z "$server_version" ]; then
        # Fallback to parsing docker version output
        server_version=$(docker version | grep -A1 "Server:" | grep "API version:" | awk '{print $3}')
    fi
    
    echo "$server_version"
}

detect_docker_client_api_version() {
    # Get the Docker client API version
    local client_version=$(docker version --format '{{.Client.APIVersion}}' 2>/dev/null)
    
    if [ -z "$client_version" ]; then
        # Fallback to parsing docker version output
        client_version=$(docker version | grep -A1 "Client:" | grep "API version:" | awk '{print $3}')
    fi
    
    echo "$client_version"
}

check_docker_compose_v2() {
    # Check if docker-compose is v2 (integrated with docker)
    if docker compose version &>/dev/null; then
        echo "v2"
    elif command -v docker-compose &>/dev/null; then
        echo "v1"
    else
        echo "none"
    fi
}

get_compatible_api_version() {
    local server_version=$(detect_docker_api_version)
    local client_version=$(detect_docker_client_api_version)
    
    # If we can't detect versions, don't set anything
    if [ -z "$server_version" ] || [ -z "$client_version" ]; then
        echo ""
        return
    fi
    
    # Compare versions and use the lower one for compatibility
    if [ "$server_version" \< "$client_version" ]; then
        echo "$server_version"
    else
        echo "$client_version"
    fi
}

# Export functions for use in other scripts
export -f detect_docker_api_version
export -f detect_docker_client_api_version
export -f check_docker_compose_v2
export -f get_compatible_api_version

# If script is run directly, output the compatible version
if [ "${BASH_SOURCE[0]}" == "${0}" ]; then
    compatible_version=$(get_compatible_api_version)
    if [ -n "$compatible_version" ]; then
        echo "Compatible Docker API version: $compatible_version"
        echo "Export with: export DOCKER_API_VERSION=$compatible_version"
    else
        echo "Could not detect Docker API version"
        exit 1
    fi
fi