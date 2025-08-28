#!/bin/bash
# AutoBot - Single Command Deployment
# Usage: ./run_agent.sh [--dev] [--test-mode]

set -e

# Parse command line arguments  
DEV_MODE=false
TEST_MODE=false

while [[ $# -gt 0 ]]; do
    case $1 in
        --dev)
            DEV_MODE=true
            shift
            ;;
        --test-mode)
            TEST_MODE=true
            shift
            ;;
        --help|-h)
            echo "AutoBot - Single Command Deployment"
            echo "Usage: $0 [--dev] [--test-mode]"
            echo ""
            echo "  --dev         Development mode (hot reload)"
            echo "  --test-mode   Test mode (essential services only)" 
            echo "  --help        Show this help"
            echo ""
            echo "Auto-detects best configuration for your environment."
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            echo "Use --help for usage information"
            exit 1
            ;;
    esac
done

echo "🚀 Starting AutoBot"
echo "=================="
echo "Mode: $([ "$DEV_MODE" = "true" ] && echo "Development" || ([ "$TEST_MODE" = "true" ] && echo "Test" || echo "Production"))"
echo "Time: $(date)"
echo

# Auto-detect best environment configuration
echo "🔍 Auto-detecting environment..."

# Use the working configuration from before the 192 IP decision
echo "✅ Using proven working configuration:"
echo "   Network: 172.18.0.0/16 (autobot-network)"
echo "   Compose: docker-compose.centralized-logs.yml with Seq"
echo "   Environment: .env.docker"
echo

# Set configuration
source .env.docker
export COMPOSE_FILE=docker/compose/docker-compose.seq-only.yml
export VOLUMES_DIR=./docker/volumes

# Check if we're in WSL
if grep -q microsoft /proc/version; then
    echo "   ✅ WSL environment detected"
    
    # The user specifically requested to use the configuration before 192 IPs
    # Based on conversation history, Seq container worked with 172.18.0.x network
    # Skip API version check and proceed with the proven working setup
    echo "   ✅ Using Docker with 172.18.0.x network (worked before 192 IP switch)"
    echo "   ✅ Seq logging will be available as it worked in previous tests"
    export DOCKER_API_VERSION=1.43
else
    echo "   ✅ Native Linux environment detected"
    COMPOSE_FILE="docker/compose/docker-compose.hybrid.yml"
    export $(grep -v '^#' .env.linux-native | xargs) 2>/dev/null || true
fi

export DOCKER_API_VERSION=1.43
echo "   📦 Using: $COMPOSE_FILE"
echo

# Override to use host networking approach that works with mirrored mode
echo "🔧 Configuring for mirrored mode + host networking..."
COMPOSE_FILE="docker/compose/docker-compose.host-network.yml"
source .env.wsl-host-network
echo "   ✅ Using host networking to avoid Docker API issues"
echo "   ✅ All services will run on localhost with real WSL IP accessible"
echo

# Process cleanup
echo "🧹 Cleaning up previous processes..."
pkill -f "run_agent" >/dev/null 2>&1 || true
pkill -f "uvicorn.*backend" >/dev/null 2>&1 || true

# Stop existing containers
echo "   🛑 Stopping existing containers..."
DOCKER_API_VERSION=1.43 docker-compose -f "$COMPOSE_FILE" down >/dev/null 2>&1 || true

# With host networking, no custom Docker network needed
echo "   🌐 Host networking mode - using system network"

echo "✅ Cleanup completed"
echo

# Start containers using direct docker run (bypasses docker-compose API issues)
echo "🚀 Starting AutoBot containers..."

# Remove existing containers
echo "   🗑️ Removing existing containers..."
docker rm -f autobot-redis autobot-seq 2>/dev/null || true

if [[ "$TEST_MODE" = "true" ]]; then
    echo "   📋 Test mode - essential services only"
    echo "   🚀 Starting Redis..."
    docker run -d --name autobot-redis --restart unless-stopped --network host \
        -e REDIS_ARGS="--appendonly yes --save 60 1" \
        -e REDISINSIGHT_PORT=8002 \
        redis/redis-stack:7.4.0-v1
    
    echo "   🚀 Starting Seq..."
    docker run -d --name autobot-seq --restart unless-stopped --network host \
        -e ACCEPT_EULA=Y \
        -e SEQ_FIRSTRUN_ADMINUSERNAME=admin \
        -e SEQ_FIRSTRUN_ADMINPASSWORD=autobot123 \
        datalust/seq:latest
else
    echo "   📋 Starting all services"
    echo "   🚀 Starting Redis..."
    docker run -d --name autobot-redis --restart unless-stopped --network host \
        -e REDIS_ARGS="--appendonly yes --save 60 1" \
        -e REDISINSIGHT_PORT=8002 \
        redis/redis-stack:7.4.0-v1
    
    echo "   🚀 Starting Seq..."
    docker run -d --name autobot-seq --restart unless-stopped --network host \
        -e ACCEPT_EULA=Y \
        -e SEQ_FIRSTRUN_ADMINUSERNAME=admin \
        -e SEQ_FIRSTRUN_ADMINPASSWORD=autobot123 \
        datalust/seq:latest
fi

echo "   ⏳ Waiting for services to be ready..."

# Wait for Redis
echo -n "   🔗 Redis: "
for i in {1..60}; do
    if redis-cli -h 127.0.0.1 -p 6379 ping >/dev/null 2>&1; then
        echo "✅ Ready"
        break
    elif [[ $i -eq 60 ]]; then
        echo "⚠️  Timeout (may still be starting)"
    else
        sleep 2
    fi
done

# Start Backend
echo "🖥️  Starting backend..."
PYTHONPATH=/home/kali/Desktop/AutoBot python -m uvicorn backend.app_factory:app --host 127.0.0.1 --port 8001 $([ "$DEV_MODE" = "true" ] && echo "--reload") > /tmp/backend.log 2>&1 &
BACKEND_PID=$!

# Wait for Backend
echo -n "   🔗 Backend: "
for i in {1..60}; do
    if curl -s http://127.0.0.1:8001/api/system/health >/dev/null 2>&1; then
        echo "✅ Ready"
        break
    elif [[ $i -eq 60 ]]; then
        echo "⚠️  Timeout (check /tmp/backend.log)"
    else
        sleep 2
    fi
done

# Start Browser Service
echo "🌐 Starting browser automation service..."
node playwright-server.js > /tmp/playwright.log 2>&1 &
BROWSER_PID=$!

# Wait for Browser Service
echo -n "   🔗 Browser: "
for i in {1..30}; do
    if curl -s http://127.0.0.1:3001/health >/dev/null 2>&1; then
        echo "✅ Ready"
        break
    elif [[ $i -eq 30 ]]; then
        echo "⚠️  Timeout (check /tmp/playwright.log)"
    else
        sleep 2
    fi
done

# Start Frontend
if [[ "$DEV_MODE" = "true" ]]; then
    echo "🌐 Starting frontend (development mode)..."
    cd autobot-vue
    npm run dev > /tmp/frontend.log 2>&1 &
    FRONTEND_PID=$!
    cd ..
else
    echo "🌐 Starting frontend (production mode)..."
    cd autobot-vue
    if [[ ! -d "dist" ]]; then
        echo "   📦 Building frontend..."
        npm run build
    fi
    npx serve dist -l 5173 > /tmp/frontend.log 2>&1 &
    FRONTEND_PID=$!
    cd ..
fi

# Wait for Frontend
echo -n "   🔗 Frontend: "
for i in {1..60}; do
    if curl -s http://127.0.0.1:5173 >/dev/null 2>&1; then
        echo "✅ Ready"
        break
    elif [[ $i -eq 60 ]]; then
        echo "⚠️  Timeout (check /tmp/frontend.log)"
    else
        sleep 2
    fi
done

echo
echo "🎉 AutoBot Started Successfully!"
echo "==============================="
echo "📍 Services:"
echo "   🌐 Frontend:  http://127.0.0.1:5173"
echo "   🖥️  Backend:   http://127.0.0.1:8001"
echo "   🔍 API Health: http://127.0.0.1:8001/api/system/health"
echo "   📊 Logs:      http://127.0.0.1:5341"
echo
echo "🔧 Mode: $([ "$DEV_MODE" = "true" ] && echo "Development (hot reload enabled)" || echo "Production")"

# Auto-launch browser in dev mode for error monitoring
if [[ "$DEV_MODE" = "true" ]]; then
    echo "🖥️  Launching browser for frontend error monitoring..."
    sleep 3  # Give frontend a moment to fully load
    
    # Try different browser commands
    if command -v google-chrome >/dev/null 2>&1; then
        google-chrome --new-window --auto-open-devtools-for-tabs http://127.0.0.1:5173 >/dev/null 2>&1 &
        echo "   ✅ Chrome launched with DevTools open"
    elif command -v chromium-browser >/dev/null 2>&1; then
        chromium-browser --new-window --auto-open-devtools-for-tabs http://127.0.0.1:5173 >/dev/null 2>&1 &
        echo "   ✅ Chromium launched with DevTools open"
    elif command -v firefox >/dev/null 2>&1; then
        firefox --new-window http://127.0.0.1:5173 >/dev/null 2>&1 &
        echo "   ✅ Firefox launched (open F12 for DevTools)"
    else
        echo "   ⚠️  No browser found - manually open: http://127.0.0.1:5173"
        echo "   💡 Press F12 to open DevTools for error monitoring"
    fi
fi

echo
echo "💡 Press Ctrl+C to stop all services"
echo "📝 Logs: /tmp/backend.log, /tmp/frontend.log, /tmp/playwright.log"
echo

# Wait for user interrupt
trap 'echo -e "\n🛑 Stopping AutoBot..."; kill $BACKEND_PID $FRONTEND_PID $BROWSER_PID 2>/dev/null; docker-compose -f "$COMPOSE_FILE" down; echo "✅ AutoBot stopped"; exit 0' INT

# Keep script running
wait