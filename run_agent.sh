#!/bin/bash

# Script to run the AutoBot application with backend and frontend components

echo "Starting AutoBot application..."

# Enhanced cleanup function with better signal handling
cleanup() {
    echo "Received signal. Terminating all processes..."
    
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

    # Ensure all processes listening on our ports are killed
    echo "Ensuring all processes on ports 8001 and 5173 are terminated..."
    for port in 8001 5173; do
        PIDS=$(lsof -t -i :$port)
        if [ -n "$PIDS" ]; then
            echo "Killing processes on port $port: $PIDS"
            kill -9 $PIDS 2>/dev/null
        fi
    done

    # Kill any remaining child processes of this script
    echo "Killing any remaining child processes..."
    pkill -P $$ -f "python3 main.py" 2>/dev/null
    pkill -P $$ -f "npm run dev" 2>/dev/null
    pkill -P $$ -f "uvicorn" 2>/dev/null # Ensure uvicorn is killed

    echo "All processes terminated."
    exit 0
}

# Trap multiple signals for robust cleanup
trap cleanup SIGINT SIGTERM SIGQUIT

# Enhanced port cleanup function
cleanup_port() {
    local port=$1
    local service_name=$2
    
    echo "Stopping any existing $service_name processes on port $port..."
    if lsof -i :$port -t > /dev/null 2>&1; then
        lsof -i :$port -t | xargs kill -9 2>/dev/null
        echo "$service_name processes on port $port terminated."
    else
        echo "No $service_name process found on port $port."
    fi
}

# Clean up ports before starting
cleanup_port 8001 "backend"
cleanup_port 5173 "frontend"
cleanup_port 5174 "frontend (alternate)"

# Start Redis Stack Docker container
echo "Starting Redis Stack Docker container..."
if sudo docker ps -a --format '{{.Names}}' | grep -q '^redis-stack$'; then
    if sudo docker inspect -f '{{.State.Running}}' redis-stack | grep -q 'true'; then
        echo "✅ 'redis-stack' container is already running."
    else
        echo "🔄 'redis-stack' container found but not running. Starting it..."
        sudo docker start redis-stack || { echo "❌ Failed to start 'redis-stack' container."; exit 1; }
        echo "✅ 'redis-stack' container started."
    fi
else
    echo "❌ 'redis-stack' container not found. Please run setup_agent.sh to deploy it."
    exit 1
fi

# Start backend (FastAPI) in background
echo "Starting FastAPI backend on port 8001..."
python3 main.py &
BACKEND_PID=$!

# Give backend time to start
sleep 3

# Check if backend started successfully
if ! ps -p $BACKEND_PID > /dev/null; then
  echo "Error: Backend failed to start. Check logs for details."
  cleanup
  exit 1
fi

echo "Backend started successfully (PID: $BACKEND_PID)"

# Check for frontend server on port 5173
echo "Checking for Vite frontend server on port 5173..."
lsof -i :5173 -t | xargs kill -9 2>/dev/null
echo "Existing Vite server terminated."

# Start frontend (Vite with Vue)
echo "Starting Vite frontend server..."
echo "Cleaning frontend build artifacts and cache..."
rm -rf /home/kali/Desktop/AutoBot/autobot-vue/node_modules /home/kali/Desktop/AutoBot/autobot-vue/.vite
cd /home/kali/Desktop/AutoBot/autobot-vue && npm install --force && npm run build && npm run dev &
FRONTEND_PID=$!
cd /home/kali/Desktop/AutoBot

# Check if frontend started successfully
sleep 5
if ! ps -p $FRONTEND_PID > /dev/null; then
  echo "Error: Frontend failed to start. Check logs for details."
  cleanup
  exit 1
fi

echo "AutoBot application started."
echo "Backend available at http://localhost:8001/ (PID: $BACKEND_PID)"
echo "Frontend available at http://localhost:5173/ (PID: $FRONTEND_PID)"
echo "Press Ctrl+C to stop all processes."

# Wait for Ctrl+C
wait
