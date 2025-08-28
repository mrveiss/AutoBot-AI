#!/bin/bash

# AutoBot Docker Network Detection
# Automatically detects the best network configuration for your Docker setup

echo "🔍 AutoBot Docker Network Detection"
echo "==================================="
echo ""

# Check Docker version and type
DOCKER_VERSION=$(docker version --format '{{.Server.Version}}' 2>/dev/null)
DOCKER_CONTEXT=$(docker context show 2>/dev/null)

echo "Docker Info:"
echo "  Version: $DOCKER_VERSION"  
echo "  Context: $DOCKER_CONTEXT"
echo ""

# Check if Docker Desktop is being used
IS_DOCKER_DESKTOP=false
if docker version 2>/dev/null | grep -q "Docker Desktop"; then
    IS_DOCKER_DESKTOP=true
fi

echo "Docker Type: $([ "$IS_DOCKER_DESKTOP" = true ] && echo "Docker Desktop" || echo "Docker Engine")"
echo ""

# Check available networks
echo "Available Docker Networks:"
docker network ls --format "table {{.Name}}\t{{.Driver}}\t{{.Scope}}"
echo ""

# Inspect default bridge network
DEFAULT_SUBNET=$(docker network inspect bridge --format '{{range .IPAM.Config}}{{.Subnet}}{{end}}' 2>/dev/null)
echo "Default Bridge Network: $DEFAULT_SUBNET"
echo ""

# Check for existing AutoBot network
AUTOBOT_NETWORK_EXISTS=false
if docker network ls --format '{{.Name}}' | grep -q "autobot-network"; then
    AUTOBOT_NETWORK_EXISTS=true
    AUTOBOT_SUBNET=$(docker network inspect autobot-network --format '{{range .IPAM.Config}}{{.Subnet}}{{end}}' 2>/dev/null)
    echo "Existing AutoBot Network: $AUTOBOT_SUBNET"
fi
echo ""

# Detect best configuration
echo "🎯 Recommended Configuration:"
echo "=============================="

if [ "$IS_DOCKER_DESKTOP" = true ]; then
    echo "✅ Docker Desktop Detected"
    echo ""
    echo "Recommended: Use Docker Desktop configuration"
    echo "Command: source ./load-env.sh --docker-desktop"
    echo "Network: 192.168.65.0/24"
    echo "File: .env.docker-desktop"
    RECOMMENDED_ENV="docker-desktop"
    RECOMMENDED_NETWORK="192.168.65.0/24"
    
elif [ "$AUTOBOT_NETWORK_EXISTS" = true ]; then
    echo "✅ Existing AutoBot Network Found: $AUTOBOT_SUBNET"
    echo ""
    case "$AUTOBOT_SUBNET" in
        "172.18.0.0/16")
            echo "Recommended: Use standard Docker configuration"
            echo "Command: source ./load-env.sh --docker"
            RECOMMENDED_ENV="docker"
            ;;
        "192.168.65.0/24")
            echo "Recommended: Use Docker Desktop configuration"
            echo "Command: source ./load-env.sh --docker-desktop"
            RECOMMENDED_ENV="docker-desktop"
            ;;
        *)
            echo "Recommended: Use custom configuration"
            echo "Network: $AUTOBOT_SUBNET"
            RECOMMENDED_ENV="custom"
            ;;
    esac
    RECOMMENDED_NETWORK="$AUTOBOT_SUBNET"
    
else
    echo "✅ No AutoBot Network Found"
    echo ""
    echo "Recommended: Create new Docker configuration"
    echo "Command: source ./load-env.sh --docker"
    echo "Network: 172.18.0.0/16 (will be created)"
    echo "File: .env.docker"
    RECOMMENDED_ENV="docker"
    RECOMMENDED_NETWORK="172.18.0.0/16"
fi

echo ""
echo "🚀 Quick Start:"
echo "==============="
echo "1. Load environment:"
case "$RECOMMENDED_ENV" in
    "docker-desktop")
        echo "   source ./load-env.sh --docker-desktop"
        ;;
    "docker")
        echo "   source ./load-env.sh --docker"
        ;;
    "custom")
        echo "   source ./load-env.sh --file .env.custom"
        ;;
esac

echo "2. Start AutoBot:"
echo "   ./run_agent.sh --dev"
echo ""

echo "📋 All Available Options:"
echo "========================"
echo "• --docker         : 172.18.0.0/16 (standard Docker)"
echo "• --docker-desktop : 192.168.65.0/24 (Docker Desktop)"  
echo "• --localhost      : 127.0.0.1 (local development)"
echo "• --distributed    : Custom IPs (multi-host)"
echo ""

# Test current connectivity if containers are running
if docker ps --format '{{.Names}}' | grep -q autobot; then
    echo "🔧 Testing Current Setup:"
    echo "========================"
    ./test-container-ping.sh
fi