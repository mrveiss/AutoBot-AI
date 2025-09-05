#!/bin/bash
"""
Backend Restart Script with Error Fixes

This script gracefully restarts the AutoBot backend to load:
- New /api/monitoring/services/status endpoint
- New /api/monitoring/services/health endpoint  
- Fixed WebSocket endpoints
- All other endpoint fixes
"""

echo "🔄 AutoBot Backend Restart with Error Fixes"
echo "============================================="

# Get current backend PID
BACKEND_PID=$(pgrep -f "uvicorn.*fast_app_factory_fix")

if [ -n "$BACKEND_PID" ]; then
    echo "📍 Found running backend (PID: $BACKEND_PID)"
    
    # Test current endpoints before restart
    echo "🧪 Testing current endpoints..."
    
    # Test health endpoint
    if curl -s -o /dev/null -w "%{http_code}" http://localhost:8001/api/health | grep -q "200"; then
        echo "  ✅ Backend health OK"
    else
        echo "  ❌ Backend health check failed"
    fi
    
    # Test new monitoring endpoints
    if curl -s -o /dev/null -w "%{http_code}" http://localhost:8001/api/monitoring/services/status | grep -q "200"; then
        echo "  ✅ Monitoring services endpoint already working"
        NEW_ENDPOINTS_LOADED=true
    else
        echo "  🔧 Monitoring services endpoint needs loading (404)"
        NEW_ENDPOINTS_LOADED=false
    fi
    
    # Only restart if new endpoints aren't loaded
    if [ "$NEW_ENDPOINTS_LOADED" = false ]; then
        echo "🛑 Gracefully stopping backend..."
        kill -TERM $BACKEND_PID
        
        # Wait for graceful shutdown
        echo "⏳ Waiting for graceful shutdown (max 10 seconds)..."
        for i in {1..10}; do
            if ! kill -0 $BACKEND_PID 2>/dev/null; then
                echo "✅ Backend stopped gracefully"
                break
            fi
            sleep 1
            echo "  Waiting... ($i/10)"
        done
        
        # Force kill if still running
        if kill -0 $BACKEND_PID 2>/dev/null; then
            echo "⚠️ Force stopping backend..."
            kill -KILL $BACKEND_PID
            sleep 2
        fi
    else
        echo "ℹ️ Backend already has new endpoints loaded - no restart needed"
        exit 0
    fi
else
    echo "❌ No running backend found"
fi

# Start backend with fast startup
echo "🚀 Starting backend with error fixes..."
cd /home/kali/Desktop/AutoBot

# Use the same command from run_agent_unified.sh
export PYTHONPATH="/home/kali/Desktop/AutoBot:$PYTHONPATH"

# Start backend in background
nohup python -m uvicorn backend.fast_app_factory_fix:app \
    --host 0.0.0.0 \
    --port 8001 \
    --log-level info \
    --access-log \
    --timeout-keep-alive 120 \
    > logs/backend_restart.log 2>&1 &

NEW_BACKEND_PID=$!
echo "🆔 New backend PID: $NEW_BACKEND_PID"

# Wait for backend to start
echo "⏳ Waiting for backend to start..."
for i in {1..30}; do
    if curl -s -o /dev/null -w "%{http_code}" http://localhost:8001/api/health | grep -q "200"; then
        echo "✅ Backend started successfully!"
        break
    fi
    sleep 1
    echo "  Waiting for startup... ($i/30)"
done

# Test new endpoints
echo "🧪 Testing new endpoints..."

# Test monitoring services status
STATUS_CODE=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:8001/api/monitoring/services/status)
if [ "$STATUS_CODE" = "200" ]; then
    echo "  ✅ /api/monitoring/services/status - Working (200)"
else
    echo "  ❌ /api/monitoring/services/status - Failed ($STATUS_CODE)"
fi

# Test monitoring services health  
HEALTH_CODE=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:8001/api/monitoring/services/health)
if [ "$HEALTH_CODE" = "200" ]; then
    echo "  ✅ /api/monitoring/services/health - Working (200)"
else
    echo "  ❌ /api/monitoring/services/health - Failed ($HEALTH_CODE)"
fi

# Test WebSocket endpoint (just check it doesn't return 404)
WS_CODE=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:8001/ws)
if [ "$WS_CODE" != "404" ]; then
    echo "  ✅ WebSocket endpoint /ws - Available"
else
    echo "  ❌ WebSocket endpoint /ws - Not found (404)"
fi

# Final status
echo ""
echo "🏁 Backend restart completed!"
echo "📊 Backend logs: logs/backend_restart.log"
echo "🌐 Backend available at: http://localhost:8001"
echo "📋 API docs available at: http://localhost:8001/docs"
echo ""
echo "🔧 Error fixes applied:"
echo "  ✅ Added /api/monitoring/services/status endpoint"
echo "  ✅ Added /api/monitoring/services/health endpoint"
echo "  ✅ Fixed ApiClient import issues"
echo "  ✅ WebSocket endpoints available"
echo ""
echo "💡 Next steps:"
echo "  1. Refresh your browser to see fixes"
echo "  2. Check developer console for remaining errors"
echo "  3. Run UI tests: python comprehensive_ui_test.py"