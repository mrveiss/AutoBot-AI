#!/bin/bash
# AutoBot Smart Startup - Auto-detects deployment environment

echo "🚀 AutoBot Smart Startup"
echo "========================"

# Source environment detection
source ./detect-environment.sh

# Handle Docker API version for Docker Desktop
if [[ "$AUTOBOT_ENVIRONMENT" == "wsl-docker-desktop" ]]; then
    export DOCKER_API_VERSION=1.43
    export HTTP_PROXY=
    export HTTPS_PROXY=
    export NO_PROXY=*
fi

# Display network configuration based on environment
echo ""
echo "📡 Network Configuration:"
case $AUTOBOT_ENVIRONMENT in
    "wsl-docker-desktop")
        echo "   External Access: via localhost:port"
        echo "   Internal Network: 192.168.65.0/24"
        echo "   Redis: localhost:${AUTOBOT_REDIS_PORT:-6379}"
        echo "   Backend: localhost:${AUTOBOT_BACKEND_PORT:-8001}"
        echo "   Frontend: localhost:${AUTOBOT_FRONTEND_PORT:-5173}"
        ;;
    "linux-native"|"wsl-native-docker")
        echo "   Direct Docker Network: ${AUTOBOT_DOCKER_SUBNET:-172.18.0.0/16}"
        echo "   Redis: ${AUTOBOT_REDIS_HOST:-172.18.0.10}:${AUTOBOT_REDIS_PORT:-6379}"
        echo "   Backend: ${AUTOBOT_BACKEND_HOST:-172.18.0.30}:${AUTOBOT_BACKEND_PORT:-8001}"
        echo "   Frontend: ${AUTOBOT_FRONTEND_HOST:-172.18.0.40}:${AUTOBOT_FRONTEND_PORT:-5173}"
        ;;
    "distributed")
        echo "   Distributed deployment - services on multiple hosts"
        echo "   Check .env.distributed for service locations"
        ;;
esac

echo ""
echo "▶️  Starting AutoBot with detected configuration..."
echo ""

# Pass all arguments to run_agent.sh
./run_agent.sh "$@"