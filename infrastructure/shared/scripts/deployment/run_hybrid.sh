#!/bin/bash
# =============================================================================
# DEV/SANDBOX ONLY - This script assumes Docker containers.
# Production uses native deployments. See Ansible roles for equivalent.
# =============================================================================

# Script to run AutoBot in hybrid mode (local orchestrator + containerized AI stack)

echo "Starting AutoBot in hybrid deployment mode..."

# Enhanced cleanup function
cleanup() {
    echo "Received signal. Terminating all processes..."

    # Kill backend process
    if [ ! -z "$BACKEND_PID" ]; then
        echo "Terminating backend process (PID: $BACKEND_PID)..."
        kill -TERM "$BACKEND_PID" 2>/dev/null
        sleep 1
        kill -9 "$BACKEND_PID" 2>/dev/null
    fi

    # Kill frontend process
    if [ ! -z "$FRONTEND_PID" ]; then
        echo "Terminating frontend process (PID: $FRONTEND_PID)..."
        kill -TERM "$FRONTEND_PID" 2>/dev/null
        sleep 1
        kill -9 "$FRONTEND_PID" 2>/dev/null
    fi

    # Clean up ports
    for port in 8001 5173; do
        PIDS=$(sudo lsof -t -i :$port 2>/dev/null)
        if [ -n "$PIDS" ]; then
            echo "Killing processes on port $port: $PIDS"
            sudo kill -9 $PIDS 2>/dev/null
        fi
    done

    echo "All processes terminated."
    exit 0
}

# Trap signals for cleanup
trap cleanup SIGINT SIGTERM SIGQUIT

# Enhanced port cleanup function
cleanup_port() {
    local port=$1
    local service_name=$2

    echo "Stopping any existing $service_name processes on port $port..."
    if sudo lsof -i :$port -t > /dev/null 2>&1; then
        PIDS=$(sudo lsof -t -i :$port 2>/dev/null)
        if [ -n "$PIDS" ]; then
            echo "Killing processes on port $port: $PIDS"
            sudo kill -9 $PIDS 2>/dev/null
        fi
        echo "$service_name processes on port $port terminated."
    else
        echo "No $service_name process found on port $port."
    fi
}

# Clean up ports before starting
cleanup_port 8001 "backend"
cleanup_port 5173 "frontend"

# Ensure Docker services are running
echo "Starting hybrid Docker services..."
docker-compose -f docker/compose/docker-compose.hybrid.yml up -d || {
    echo "❌ Failed to start Docker services. Please check docker-compose.hybrid.yml"
    exit 1
}

# Wait for services to be ready
echo "⏳ Waiting for AI stack to be ready..."
for i in {1..30}; do
    if curl -sf http://localhost:8080/health > /dev/null 2>&1; then
        echo "✅ AI stack is ready."
        break
    fi
    echo "⏳ Waiting for AI stack... (attempt $i/30)"
    sleep 2
done

# Check if Redis is ready
echo "⏳ Waiting for Redis to be ready..."
for i in {1..15}; do
    if docker exec autobot-redis redis-cli ping > /dev/null 2>&1; then
        echo "✅ Redis is ready."
        break
    fi
    echo "⏳ Waiting for Redis... (attempt $i/15)"
    sleep 1
done

# Check if Playwright service is running
echo "Checking Playwright service..."
if docker ps --format '{{.Names}}' | grep -q '^autobot-playwright$'; then
    if curl -sf http://localhost:3000/health > /dev/null 2>&1; then
        echo "✅ Playwright service is ready."
    else
        echo "⏳ Starting Playwright service..."
        docker start autobot-playwright 2>/dev/null || echo "ℹ️ Playwright service not available (optional)"
    fi
else
    echo "ℹ️ Playwright service not found (optional)"
fi

# Set environment for hybrid mode
export AUTOBOT_DEPLOYMENT_MODE=hybrid
export REDIS_HOST=localhost  # Connect to local port forwarded from container
export AI_STACK_URL=http://localhost:8080

# Start backend (FastAPI) in background
echo "Starting FastAPI backend on port 8001..."
uvicorn main:app --host 0.0.0.0 --port 8001 --log-level info &
BACKEND_PID=$!

# Give backend time to start
sleep 5

# Check if backend process is running
if ! ps -p $BACKEND_PID > /dev/null; then
    echo "❌ Backend process (PID: $BACKEND_PID) failed to start. Check logs for details."
    cleanup
    exit 1
fi

# Wait for backend to listen on port 8001
echo "⏳ Waiting for backend to listen on port 8001..."
TIMEOUT=60
for i in $(seq 1 $TIMEOUT); do
    if ! ps -p $BACKEND_PID > /dev/null; then
        echo "❌ Backend process (PID: $BACKEND_PID) died unexpectedly."
        cleanup
        exit 1
    fi

    if sudo netstat -tlnp | grep -q ":8001"; then
        echo "✅ Backend is listening on port 8001."
        break
    fi

    if [ $i -eq $TIMEOUT ]; then
        echo "❌ Backend did not start listening on port 8001 within $TIMEOUT seconds."
        cleanup
        exit 1
    fi
    sleep 1
done

echo "✅ Backend started successfully (PID: $BACKEND_PID)"

# Start frontend (Vue)
echo "Starting Vue frontend server..."
cd autobot-slm-frontend
npm run dev &
FRONTEND_PID=$!
cd ..

# Check if frontend started successfully
sleep 5
if ! ps -p $FRONTEND_PID > /dev/null; then
    echo "❌ Frontend failed to start. Check logs for details."
    cleanup
    exit 1
fi

echo ""
echo "🚀 AutoBot hybrid deployment started successfully!"
echo ""
echo "📊 Service Status:"
echo "  • Redis:        http://localhost:6379 (Docker container)"
echo "  • AI Stack:     http://localhost:8080 (Docker container)"
echo "  • Backend:      http://localhost:8001 (Local, PID: $BACKEND_PID)"
echo "  • Frontend:     http://localhost:5173 (Local, PID: $FRONTEND_PID)"
echo ""
echo "🔗 Access AutoBot at: http://localhost:5173"
echo ""
echo "Press Ctrl+C to stop all processes."

# Wait for Ctrl+C
wait
