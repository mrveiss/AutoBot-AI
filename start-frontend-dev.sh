#!/bin/bash

# Simple script to start just the frontend development server
# Backend is already running on 172.16.168.20:8001

echo "🚀 Starting AutoBot Frontend Development Server"
echo "=============================================="
echo ""

# Check if backend is accessible
echo -n "Checking backend API health... "
if curl -s http://172.16.168.20:8001/api/health > /dev/null 2>&1; then
    echo "✅ Backend is healthy"
else
    echo "⚠️  Backend may not be accessible"
fi

# Sync frontend code to VM
echo ""
echo "📦 Syncing frontend code to VM1..."
if [ -f "scripts/utilities/sync-frontend.sh" ]; then
    ./scripts/utilities/sync-frontend.sh
elif [ -f "sync-frontend.sh" ]; then
    ./sync-frontend.sh
else
    ./scripts/utilities/sync-to-vm.sh frontend autobot-vue/ /home/autobot/
fi

# Check if frontend is already running
echo ""
echo -n "Checking if frontend is already running... "
if timeout 5 curl -s "http://172.16.168.21:5173" >/dev/null 2>&1; then
    echo "✅ Already running"
    echo ""
    echo "🌐 Frontend URL: http://172.16.168.21:5173"
    echo "📝 Logs: ssh autobot@172.16.168.21 'tail -f /tmp/vite.log'"
    exit 0
fi

echo "Not running, starting now..."

# Start frontend on VM1
echo "🚀 Starting Vite dev server on VM1..."
ssh -i ~/.ssh/autobot_key autobot@172.16.168.21 "cd /home/autobot/autobot-vue && VITE_BACKEND_HOST=172.16.168.20 VITE_BACKEND_PORT=8001 nohup npm run dev -- --host 0.0.0.0 --port 5173 > /tmp/vite.log 2>&1 < /dev/null &"

echo "⏳ Waiting for frontend to start..."
sleep 5

# Check if frontend started successfully
echo -n "Testing frontend response... "
if timeout 10 curl -s "http://172.16.168.21:5173" >/dev/null 2>&1; then
    echo "✅ Success!"
    echo ""
    echo "=============================================="
    echo "🎉 Frontend Development Server Ready!"
    echo "=============================================="
    echo ""
    echo "🌐 Frontend URL: http://172.16.168.21:5173"
    echo "🔧 Backend API: http://172.16.168.20:8001"
    echo "📝 Frontend Logs: ssh autobot@172.16.168.21 'tail -f /tmp/vite.log'"
    echo "📝 Backend Logs: tail -f logs/backend.log"
    echo ""
else
    echo "❌ Failed"
    echo ""
    echo "Frontend failed to start. Debug with:"
    echo "  ssh autobot@172.16.168.21 'tail -f /tmp/vite.log'"
    echo "  ssh autobot@172.16.168.21 'cd autobot-vue && npm run dev -- --host 0.0.0.0 --port 5173'"
    exit 1
fi