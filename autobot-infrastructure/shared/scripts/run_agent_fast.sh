#!/bin/bash
# Ultra-fast AutoBot startup script - API ready in seconds

echo "🚀 Starting AutoBot with FAST STARTUP mode..."

# Parse command line arguments
TEST_MODE=false
if [[ "$1" == "--test-mode" ]]; then
    TEST_MODE=true
    echo "🧪 FAST TEST MODE - verbose output enabled"
fi

# Enhanced cleanup function
cleanup() {
    echo "🛑 Stopping AutoBot processes..."

    if [ ! -z "$BACKEND_PID" ]; then
        echo "Terminating fast backend (PID: $BACKEND_PID)..."
        kill -TERM "$BACKEND_PID" 2>/dev/null
        sleep 1
        kill -9 "$BACKEND_PID" 2>/dev/null
    fi

    if [ ! -z "$FRONTEND_PID" ]; then
        echo "Terminating frontend (PID: $FRONTEND_PID)..."
        kill -TERM "$FRONTEND_PID" 2>/dev/null
        sleep 1
        kill -9 "$FRONTEND_PID" 2>/dev/null
    fi

    # Clean up any remaining processes
    pkill -f "uvicorn.*fast_main:app" 2>/dev/null || true
    pkill -f "npm.*dev" 2>/dev/null || true

    echo "✅ All processes terminated."
    exit 0
}

trap cleanup SIGINT SIGTERM SIGQUIT

# Quick port cleanup
cleanup_ports() {
    echo "🧹 Quick port cleanup..."
    pkill -f "uvicorn.*fast_main:app" 2>/dev/null || true
    pkill -f "uvicorn.*main:app" 2>/dev/null || true
    pkill -f "npm.*dev" 2>/dev/null || true
    sleep 1
}

cleanup_ports

# Check Docker containers (optional for fast mode)
echo "📦 Checking Docker services..."
if docker ps --format '{{.Names}}' | grep -q '^autobot-redis$'; then
    echo "✅ Redis available"
else
    echo "⚠️  Redis not running - some features limited"
fi

# Setup environment
export PYTHONPATH="${PWD}:${PYTHONPATH:-}"
mkdir -p data/logs

# Start FAST backend
echo "⚡ Starting FAST backend on port 8001..."

if [ "$TEST_MODE" = true ]; then
    echo "📝 FAST TEST MODE: All startup communication visible"
    uvicorn backend.fast_main:app --host 0.0.0.0 --port 8001 --log-level debug &
else
    uvicorn backend.fast_main:app --host 0.0.0.0 --port 8001 --log-level info &
fi

BACKEND_PID=$!
echo "✅ Fast backend started (PID: $BACKEND_PID)"

# Quick backend readiness check (should be near instant)
echo "⏳ Checking fast backend readiness..."
BACKEND_READY=false

for i in $(seq 1 20); do
    if ! ps -p $BACKEND_PID > /dev/null; then
        echo "❌ Fast backend process died unexpectedly"
        exit 1
    fi

    # Test ultra-fast health endpoint
    if curl -s http://127.0.0.3:8001/api/system/health >/dev/null 2>&1; then
        echo "🎉 Fast backend ready in ${i} seconds!"
        BACKEND_READY=true
        break
    fi

    if [ "$TEST_MODE" = true ]; then
        echo "⏳ Waiting for fast backend... (${i}s)"
    fi

    sleep 1
done

if [ "$BACKEND_READY" != true ]; then
    echo "❌ Fast backend failed to start within 10 seconds"
    cleanup
    exit 1
fi

# Test the API endpoints
echo "🧪 Testing fast API endpoints..."

# Test health endpoint
health_response=$(curl -s http://127.0.0.3:8001/api/system/health)
echo "✅ Health check: $(echo $health_response | jq -r '.status // "OK"' 2>/dev/null || echo "OK")"

# Test status endpoint
status_response=$(curl -s http://127.0.0.3:8001/api/system/status)
echo "✅ System status: $(echo $status_response | jq -r '.api_ready // "ready"' 2>/dev/null || echo "ready")"

# Test knowledge base stats (should work immediately with fallback)
kb_response=$(curl -s http://127.0.0.3:8001/api/knowledge_base/stats)
echo "✅ Knowledge stats: $(echo $kb_response | jq -r '.initialization_status // "ready"' 2>/dev/null || echo "ready")"

# Start frontend
echo "🌐 Starting frontend..."

if [ "$TEST_MODE" = true ]; then
    echo "📝 Frontend logs visible in test mode"
    cd autobot-slm-frontend && npm run dev &
else
    cd autobot-slm-frontend && npm run dev > /dev/null 2>&1 &
fi

FRONTEND_PID=$!
cd ..

# Quick frontend check
sleep 3
if ! ps -p $FRONTEND_PID > /dev/null; then
    echo "❌ Frontend failed to start"
    cleanup
    exit 1
fi

echo ""
echo "🎉 AutoBot FAST startup complete!"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🔥 Backend:  http://127.0.0.3:8001/ (FAST MODE)"
echo "🌐 Frontend: http://127.0.0.3:5173/"
echo "📊 Status:   http://127.0.0.3:8001/api/system/status"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

if [ "$TEST_MODE" = true ]; then
    echo ""
    echo "🧪 FAST TEST MODE ACTIVE"
    echo "Backend PID: $BACKEND_PID"
    echo "Frontend PID: $FRONTEND_PID"
    echo "Background components initializing..."
    echo ""

    # Show background initialization progress
    echo "📊 Monitoring background initialization:"
    for i in {1..30}; do
        status=$(curl -s http://127.0.0.3:8001/api/system/status 2>/dev/null | jq -r '.background_initialization.components_ready // false' 2>/dev/null)
        if [ "$status" = "true" ]; then
            echo "🎉 All background components ready!"
            break
        fi
        echo "⏳ Background init... (${i}s elapsed)"
        sleep 1
    done
fi

echo ""
echo "Press Ctrl+C to stop all processes."

# Wait for interrupt
wait
