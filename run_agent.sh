#!/bin/bash

# Script to run the AutoBot application with backend and frontend components

echo "Starting AutoBot application..."

# Function to stop processes
stop_processes() {
  echo "Stopping all processes..."
  # Stop backend
  if [ ! -z "$BACKEND_PID" ]; then
    kill -9 $BACKEND_PID 2>/dev/null
    echo "Backend process (PID: $BACKEND_PID) terminated."
  fi
  # Stop frontend
  if [ ! -z "$FRONTEND_PID" ]; then
    kill -9 $FRONTEND_PID 2>/dev/null
    echo "Frontend process (PID: $FRONTEND_PID) terminated."
  fi
  exit 0
}

# Trap Ctrl+C and call stop_processes
trap stop_processes INT

# Stop any existing processes on port 8001 (backend)
echo "Stopping any existing processes on port 8001..."
lsof -i :8001 -t | xargs kill -9 2>/dev/null
echo "Processes on port 8001 terminated."

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
cd backend && python3 main.py &
BACKEND_PID=$!
cd ..

# Check if backend started successfully
sleep 2
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
  stop_processes
  exit 1
fi

echo "AutoBot application started."
echo "Backend available at http://localhost:8001/"
echo "Frontend available at http://localhost:5173/"
echo "Press Ctrl+C to stop all processes."

# Wait for Ctrl+C
wait
