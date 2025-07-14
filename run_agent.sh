#!/bin/bash

# Script to run the AutoBot application with backend and frontend components

echo "Starting AutoBot application..."

# Enhanced cleanup function with better signal handling
cleanup() {
    echo "Received signal. Terminating all processes..."
    
    # Kill specific processes by pattern
    pkill -P $$ -f "python.*main.py" 2>/dev/null
    pkill -P $$ -f "npm run dev" 2>/dev/null
    
    # Stop backend by PID if available
    if [ ! -z "$BACKEND_PID" ]; then
        kill -TERM $BACKEND_PID 2>/dev/null
        sleep 2
        kill -9 $BACKEND_PID 2>/dev/null
        echo "Backend process (PID: $BACKEND_PID) terminated."
    fi
    
    # Stop frontend by PID if available
    if [ ! -z "$FRONTEND_PID" ]; then
        kill -TERM $FRONTEND_PID 2>/dev/null
        sleep 2
        kill -9 $FRONTEND_PID 2>/dev/null
        echo "Frontend process (PID: $FRONTEND_PID) terminated."
    fi
    
    # Clean up any lingering processes on our ports
    echo "Cleaning up any lingering processes on ports 8001 and 5173..."
    if lsof -i :8001 -t > /dev/null 2>&1; then
        lsof -i :8001 -t | xargs kill -9 2>/dev/null
        echo "Processes on port 8001 terminated."
    fi
    if lsof -i :5173 -t > /dev/null 2>&1; then
        lsof -i :5173 -t | xargs kill -9 2>/dev/null
        echo "Processes on port 5173 terminated."
    fi
    
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
cleanup_port 8000 "frontend (alternate)"
cleanup_port 8080 "frontend (alternate)"

# Start Redis server if installed
echo "Starting Redis server if installed..."
if command -v redis-server &>/dev/null; then
    sudo systemctl start redis 2>/dev/null || redis-server --daemonize yes 2>/dev/null
    if [ $? -eq 0 ]; then
        echo "Redis server started successfully."
    else
        echo "Failed to start Redis server. Continuing without Redis."
    fi
else
    echo "Redis server not installed. Skipping Redis startup."
fi

# Start backend (FastAPI)
echo "Starting FastAPI backend on port 8001..."
python3 main.py &
BACKEND_PID=$!

# Check if backend started successfully
sleep 5 # Increased sleep duration to allow backend to fully initialize
if ! ps -p $BACKEND_PID > /dev/null; then
  echo "Error: Backend failed to start. Check logs for details."
  exit 1
fi

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
echo "Backend available at http://localhost:8001/"
echo "Frontend available at http://localhost:5173/"
echo "Press Ctrl+C to stop all processes."

# Wait for Ctrl+C
wait
