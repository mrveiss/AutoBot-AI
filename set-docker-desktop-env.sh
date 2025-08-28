#!/bin/bash

# Set Docker Desktop Environment Variables for Current Session
# This ensures the backend uses the new 192.168.65.x IPs

echo "🔧 Setting Docker Desktop Environment (192.168.65.x)"
echo "================================================="

# Core service IPs
export AUTOBOT_REDIS_HOST=192.168.65.10
export AUTOBOT_REDIS_IP=192.168.65.10
export AUTOBOT_OLLAMA_HOST=192.168.65.20
export AUTOBOT_OLLAMA_IP=192.168.65.20
export AUTOBOT_BACKEND_HOST=192.168.65.30
export AUTOBOT_BACKEND_IP=192.168.65.30
export AUTOBOT_FRONTEND_HOST=192.168.65.40
export AUTOBOT_FRONTEND_IP=192.168.65.40

# Service ports  
export AUTOBOT_REDIS_PORT=6379
export AUTOBOT_OLLAMA_PORT=11434
export AUTOBOT_BACKEND_PORT=8001
export AUTOBOT_FRONTEND_PORT=5173

# Additional services
export AUTOBOT_PLAYWRIGHT_HOST=192.168.65.80
export AUTOBOT_PLAYWRIGHT_IP=192.168.65.80
export AUTOBOT_NPU_WORKER_HOST=192.168.65.72
export AUTOBOT_NPU_WORKER_IP=192.168.65.72
export AUTOBOT_AI_STACK_HOST=192.168.65.90
export AUTOBOT_AI_STACK_IP=192.168.65.90
export AUTOBOT_LOG_VIEWER_HOST=192.168.65.90

# Network configuration
export AUTOBOT_DOCKER_SUBNET=192.168.65.0/24
export AUTOBOT_DOCKER_GATEWAY=192.168.65.1
export AUTOBOT_DEPLOYMENT_MODE=docker-desktop

# Backend WebSocket and API URLs
export AUTOBOT_WS_BASE_URL="ws://192.168.65.30:8001/ws"
export AUTOBOT_API_BASE_URL="http://192.168.65.30:8001"

# Frontend environment variables
export VITE_API_BASE_URL="http://192.168.65.30:8001"
export VITE_WS_BASE_URL="ws://192.168.65.30:8001/ws"
export VITE_BACKEND_HOST=192.168.65.30
export VITE_BACKEND_PORT=8001

echo "✅ Environment variables set:"
echo "   Redis: $AUTOBOT_REDIS_HOST:$AUTOBOT_REDIS_PORT"
echo "   Ollama: $AUTOBOT_OLLAMA_HOST:$AUTOBOT_OLLAMA_PORT" 
echo "   Backend: $AUTOBOT_BACKEND_HOST:$AUTOBOT_BACKEND_PORT"
echo "   Frontend: $AUTOBOT_FRONTEND_HOST:$AUTOBOT_FRONTEND_PORT"
echo "   WebSocket: $AUTOBOT_WS_BASE_URL"
echo ""
echo "🚀 Ready for Docker Desktop deployment!"
echo "   Network: 192.168.65.0/24"
echo "   Backend containers can communicate directly via 192.168.65.x IPs"