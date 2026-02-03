#!/bin/bash

# AutoBot Environment Loader
# Supports multiple deployment configurations

# Parse command line arguments
DEPLOYMENT_MODE="docker"
ENV_FILE=""

while [[ $# -gt 0 ]]; do
    case $1 in
        --docker)
            DEPLOYMENT_MODE="docker"
            ENV_FILE=".env.docker"
            shift
            ;;
        --localhost)
            DEPLOYMENT_MODE="localhost"
            ENV_FILE=".env.localhost"
            shift
            ;;
        --distributed)
            DEPLOYMENT_MODE="distributed"
            ENV_FILE=".env.distributed"
            shift
            ;;
        --docker-desktop)
            DEPLOYMENT_MODE="docker-desktop"
            ENV_FILE=".env.docker-desktop"
            shift
            ;;
        --file)
            ENV_FILE="$2"
            DEPLOYMENT_MODE="custom"
            shift 2
            ;;
        --help)
            echo "AutoBot Environment Loader"
            echo ""
            echo "Usage: source ./load-env.sh [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  --docker       Load Docker container IPs (default)"
            echo "  --localhost    Load localhost development config"
            echo "  --distributed  Load distributed deployment config"
            echo "  --docker-desktop Load Docker Desktop config (192.168.65.x)"
            echo "  --file FILE    Load custom environment file"
            echo "  --help         Show this help"
            echo ""
            echo "Examples:"
            echo "  source ./load-env.sh --docker      # Single-host Docker (172.18.x)"
            echo "  source ./load-env.sh --localhost   # Local development"
            echo "  source ./load-env.sh --distributed # Multi-host deployment"
            echo "  source ./load-env.sh --docker-desktop # Docker Desktop (192.168.65.x)"
            return 0
            ;;
        *)
            echo "Unknown option: $1"
            echo "Use --help for usage information"
            return 1
            ;;
    esac
done

# Set default env file if not specified
if [ -z "$ENV_FILE" ]; then
    ENV_FILE=".env.docker"
fi

echo "Loading AutoBot environment configuration..."
echo "Mode: $DEPLOYMENT_MODE"
echo "File: $ENV_FILE"
echo ""

# Source the environment file
if [ -f "$ENV_FILE" ]; then
    export $(grep -v '^#' "$ENV_FILE" | grep -v '^$' | xargs)
    echo "✅ Loaded $DEPLOYMENT_MODE configuration:"
    echo "   Redis: ${AUTOBOT_REDIS_HOST}:${AUTOBOT_REDIS_PORT:-6379}"
    echo "   Ollama: ${AUTOBOT_OLLAMA_HOST}:${AUTOBOT_OLLAMA_PORT:-11434}"
    echo "   Backend: ${AUTOBOT_BACKEND_HOST}:${AUTOBOT_BACKEND_PORT:-8001}"
    echo "   Frontend: ${AUTOBOT_FRONTEND_HOST}:${AUTOBOT_FRONTEND_PORT:-5173}"
    echo "   Playwright: ${AUTOBOT_PLAYWRIGHT_HOST}:${AUTOBOT_PLAYWRIGHT_API_PORT:-3000}"
    echo "   NPU Worker: ${AUTOBOT_NPU_WORKER_HOST}:${AUTOBOT_NPU_WORKER_PORT:-8081}"
    echo "   Deployment: ${AUTOBOT_DEPLOYMENT_MODE:-$DEPLOYMENT_MODE}"
else
    echo "❌ Environment file not found: $ENV_FILE"
    echo "Available files:"
    ls -la .env.* 2>/dev/null | grep "^-" | awk '{print "   " $9}'
    return 1
fi

echo ""
echo "Environment loaded! You can now:"
echo "  ./run_agent.sh --dev          # Start AutoBot with loaded configuration"
echo "  docker-compose up -d          # Start Docker services"