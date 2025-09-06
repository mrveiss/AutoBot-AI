#!/bin/bash

# Load Docker IP configuration for AutoBot
# This script sets environment variables for Docker container real IPs

echo "Loading Docker IP environment variables..."

# Source the Docker environment file
if [ -f ".env.docker" ]; then
    export $(grep -v '^#' .env.docker | xargs)
    echo "✅ Loaded Docker IP configuration:"
    echo "   Redis: ${AUTOBOT_REDIS_HOST:-172.18.0.10}:${AUTOBOT_REDIS_PORT:-6379}"
    echo "   Ollama: ${AUTOBOT_OLLAMA_HOST:-172.18.0.20}:${AUTOBOT_OLLAMA_PORT:-11434}"
    echo "   Backend: ${AUTOBOT_BACKEND_HOST:-172.18.0.30}:${AUTOBOT_BACKEND_PORT:-8001}"
    echo "   Frontend: ${AUTOBOT_FRONTEND_HOST:-172.18.0.40}:${AUTOBOT_FRONTEND_PORT:-5173}"
    echo "   Playwright: ${AUTOBOT_PLAYWRIGHT_HOST:-172.18.0.80}:${AUTOBOT_PLAYWRIGHT_API_PORT:-3000}"
    echo "   NPU Worker: ${AUTOBOT_NPU_WORKER_HOST:-172.18.0.72}:${AUTOBOT_NPU_WORKER_PORT:-8081}"
else
    echo "❌ .env.docker file not found. Using default localhost IPs."
fi

echo ""
echo "Usage:"
echo "  source ./load-docker-env.sh    # Load environment variables"
echo "  ./run_agent.sh --dev          # Start with Docker IPs"