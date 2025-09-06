#!/bin/bash
# AutoBot WSL + Docker Desktop Startup Script
# For running AutoBot in WSL with Docker Desktop on Windows

echo "🔧 Starting AutoBot in WSL with Docker Desktop..."

# Set Docker API version for compatibility
export DOCKER_API_VERSION=1.43

# Disable proxy for Docker operations
export HTTP_PROXY=
export HTTPS_PROXY=
export NO_PROXY=*

# Load WSL + Docker Desktop environment
if [ -f .env.wsl-docker-desktop ]; then
    export $(grep -v '^#' .env.wsl-docker-desktop | xargs)
    echo "✅ WSL + Docker Desktop environment loaded"
    echo "   Containers will use internal IPs (192.168.65.x)"
    echo "   WSL accesses services via localhost:port"
else
    echo "❌ .env.wsl-docker-desktop not found!"
    exit 1
fi

# Display configuration
echo ""
echo "📦 Service Access from WSL:"
echo "   Redis: localhost:6379"
echo "   Backend: localhost:8001"
echo "   Frontend: localhost:5173"
echo "   Seq Logs: localhost:5341"
echo ""

# Pass all arguments to run_agent.sh
./run_agent.sh "$@"