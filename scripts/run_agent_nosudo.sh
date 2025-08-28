#!/bin/bash
# Non-sudo version of run_agent.sh for Claude Code compatibility

# Script to run the AutoBot application without sudo requirements
echo "Starting AutoBot application (no-sudo mode)..."

# Parse command line arguments
TEST_MODE=false
if [[ "$1" == "--test-mode" ]]; then
    TEST_MODE=true
    echo "🧪 Running in TEST MODE - verbose output enabled"
fi

# Enhanced cleanup function without sudo
cleanup() {
    echo "🛑 Received signal. Terminating all processes..."
    
    # Kill processes by PID if they were started in background  
    if [ ! -z "$BACKEND_PID" ]; then
        echo "Terminating backend process (PID: $BACKEND_PID)..."
        kill -TERM "$BACKEND_PID" 2>/dev/null
        sleep 1
        kill -9 "$BACKEND_PID" 2>/dev/null
    fi

    if [ ! -z "$FRONTEND_PID" ]; then
        echo "Terminating frontend process (PID: $FRONTEND_PID)..."
        kill -TERM "$FRONTEND_PID" 2>/dev/null
        sleep 1
        kill -9 "$FRONTEND_PID" 2>/dev/null
    fi

    # Kill any remaining uvicorn processes (without sudo)
    echo "Killing any remaining uvicorn processes..."
    pkill -f "uvicorn.*main:app" 2>/dev/null || true
    
    # Clean up startup state file
    rm -f data/startup_state.json 2>/dev/null || true

    echo "✅ All processes terminated."
    exit 0
}

# Trap signals for robust cleanup
trap cleanup SIGINT SIGTERM SIGQUIT

# Port cleanup without sudo
cleanup_port() {
    local port=$1
    local service_name=$2

    echo "Checking for existing $service_name processes on port $port..."
    
    # Use netstat instead of lsof (doesn't require sudo)
    if netstat -tuln 2>/dev/null | grep ":$port " > /dev/null; then
        echo "Port $port is in use, attempting cleanup with pkill..."
        
        if [ "$port" == "8001" ]; then
            pkill -f "uvicorn.*main:app" 2>/dev/null || true
            pkill -f "python.*main.py" 2>/dev/null || true
        elif [ "$port" == "5173" ]; then
            pkill -f "npm.*dev" 2>/dev/null || true
            pkill -f "vite" 2>/dev/null || true
        fi
        
        # Wait a moment for processes to die
        sleep 2
        echo "$service_name processes cleaned up"
    else
        echo "No $service_name process found on port $port."
    fi
}

# Clean up ports before starting
cleanup_port 8001 "backend"
cleanup_port 5173 "frontend"

# Check Docker containers (read-only, no sudo needed)
echo "📦 Checking Docker containers status..."

# Check Redis
if docker ps --format '{{.Names}}' | grep -q '^autobot-redis$'; then
    echo "✅ Redis container is running"
else
    echo "⚠️  Redis container not found - some features may not work"
fi

# Check NPU Worker
if docker ps --format '{{.Names}}' | grep -q '^autobot-npu-worker$'; then
    echo "✅ NPU Worker container is running"
else
    echo "⚠️  NPU Worker container not found - no NPU acceleration"
fi

# Setup logging directory
LOGS_DIR="data/logs"
mkdir -p "$LOGS_DIR"

# Start backend (FastAPI) in background using uvicorn
echo "🚀 Starting FastAPI backend on port 8001..."

# Set Python path to include project root for src.* imports
export PYTHONPATH="${PWD}:${PYTHONPATH:-}"

if [ "$TEST_MODE" = true ]; then
    echo "📝 TEST MODE: Backend logs will be visible in terminal"
    uvicorn backend.main:app --host 0.0.0.0 --port 8001 --log-level debug &
else
    uvicorn backend.main:app --host 0.0.0.0 --port 8001 --log-level info &
fi

BACKEND_PID=$!
echo "Backend started with PID: $BACKEND_PID"

# Give backend time to start
sleep 3

# Check if backend process is running
if ! ps -p $BACKEND_PID > /dev/null; then
  echo "❌ Backend process (PID: $BACKEND_PID) failed to start"
  exit 1
fi

# Wait for backend to be ready with health check
echo "⏳ Waiting for backend to be ready..."
BACKEND_READY=false
for i in $(seq 1 30); do
    if ! ps -p $BACKEND_PID > /dev/null; then
        echo "❌ Backend process (PID: $BACKEND_PID) died unexpectedly."
        exit 1
    fi

    # Test our new fast health endpoint
    if curl -s http://127.0.0.3:8001/api/system/health >/dev/null 2>&1; then
        echo "✅ Backend is ready and responding to health checks!"
        BACKEND_READY=true
        break
    fi

    if [ "$TEST_MODE" = true ] && [ $((i % 5)) -eq 0 ]; then
        echo "⏳ Still waiting for backend... (${i}s elapsed)"
    fi

    sleep 1
done

if [ "$BACKEND_READY" != true ]; then
    echo "❌ Backend did not become ready within 30 seconds."
    cleanup
    exit 1
fi

# Start frontend (Vite with Vue)
echo "🌐 Starting Vite frontend server..."

if [ "$TEST_MODE" = true ]; then
    echo "📝 TEST MODE: Frontend logs will be visible in terminal"
    cd autobot-vue && npm run dev &
else
    cd autobot-vue && npm run dev > /dev/null 2>&1 &
fi

FRONTEND_PID=$!
cd ..

echo "Frontend started with PID: $FRONTEND_PID"

# Check if frontend started successfully
sleep 3
if ! ps -p $FRONTEND_PID > /dev/null; then
  echo "❌ Frontend failed to start"
  cleanup
  exit 1
fi

echo ""
echo "🎉 AutoBot application started successfully!"
echo "Backend:  http://127.0.0.3:8001/"
echo "Frontend: http://127.0.0.3:5173/"
echo ""
if [ "$TEST_MODE" = true ]; then
    echo "🧪 TEST MODE: All communication visible in terminal"
    echo "Backend PID: $BACKEND_PID"
    echo "Frontend PID: $FRONTEND_PID"
    echo ""
fi
echo "Press Ctrl+C to stop all processes."

# Wait for Ctrl+C
wait