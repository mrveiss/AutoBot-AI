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
        # Use sudo with lsof for more comprehensive process identification
        PIDS=$(sudo lsof -t -i :$port 2>/dev/null)
        if [ -n "$PIDS" ]; then
            echo "Killing processes on port $port: $PIDS"
            sudo kill -9 $PIDS 2>/dev/null
        fi
    done

    # Kill any remaining uvicorn processes
    echo "Killing any remaining uvicorn processes..."
    sudo pkill -f "uvicorn main:app" 2>/dev/null

    # Kill any remaining child processes of this script
    echo "Killing any remaining child processes of this script..."
    pkill -P $$ -f "npm run dev" 2>/dev/null
    # The above pkill for uvicorn should cover this, but keeping for robustness
    # pkill -P $$ -f "uvicorn" 2>/dev/null

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
    # Use sudo with lsof for more comprehensive process identification
    if sudo lsof -i :$port -t > /dev/null 2>&1; then
        # Attempt to kill processes associated with uvicorn specifically
        PIDS=$(sudo lsof -t -i :$port -sTCP:LISTEN 2>/dev/null | xargs -r ps -o pid,command | grep -E 'uvicorn main:app|python3 main.py' | awk '{print $1}')
        if [ -n "$PIDS" ]; then
            echo "Killing processes on port $port: $PIDS"
            sudo kill -9 $PIDS 2>/dev/null
        else
            # Fallback to killing any process on the port if not a uvicorn/python3 main.py process
            PIDS=$(sudo lsof -t -i :$port 2>/dev/null)
            if [ -n "$PIDS" ]; then
                echo "Killing non-uvicorn processes on port $port: $PIDS"
                sudo kill -9 $PIDS 2>/dev/null
            fi
        fi
        echo "$service_name processes on port $port terminated."
    else
        echo "No $service_name process found on port $port."
    fi
}

# Clean up ports before starting
cleanup_port 8001 "backend"
cleanup_port 5173 "frontend"
cleanup_port 5174 "frontend (alternate)"

# Ensure user is in docker group and docker command is accessible
if ! id -nG "$USER" | grep -qw "docker"; then
    echo "Adding user '$USER' to the 'docker' group..."
    sudo usermod -aG docker "$USER" || { echo "❌ Failed to add user to docker group."; exit 1; }
    echo "✅ User '$USER' added to 'docker' group. Please log out and log back in for changes to take effect."
    echo "You may need to run 'newgrp docker' or restart your terminal for changes to apply immediately."
    exit 1 # Exit to prompt user to re-login
fi

# Start Redis Stack Docker container
echo "Starting Redis Stack Docker container..."
if docker ps -a --format '{{.Names}}' | grep -q '^redis-stack$'; then
    if docker inspect -f '{{.State.Running}}' redis-stack | grep -q 'true'; then
        echo "✅ 'redis-stack' container is already running."
    else
        echo "🔄 'redis-stack' container found but not running. Starting it..."
        docker start redis-stack || { echo "❌ Failed to start 'redis-stack' container."; exit 1; }
        echo "✅ 'redis-stack' container started."
    fi
else
    echo "❌ 'redis-stack' container not found. Please run setup_agent.sh to deploy it."
    exit 1
fi

# Start backend (FastAPI) in background using uvicorn
echo "Starting FastAPI backend on port 8001..."
uvicorn main:app --host 0.0.0.0 --port 8001 --log-level debug &
BACKEND_PID=$!

# Give backend time to start and bind to port
sleep 5 # Increased sleep to allow more time for startup

# Check if backend process is running
if ! ps -p $BACKEND_PID > /dev/null; then
  echo "Error: Backend process (PID: $BACKEND_PID) failed to start. Check logs for details."
  cleanup
  exit 1
fi

# Wait for backend to listen on port 8001
echo "Waiting for backend to listen on port 8001..."
TIMEOUT=120 # Increased timeout to 120 seconds
for i in $(seq 1 $TIMEOUT); do
    # Check if the uvicorn process is still running
    if ! ps -p $BACKEND_PID > /dev/null; then
        echo "Error: Backend process (PID: $BACKEND_PID) died unexpectedly."
        cleanup
        exit 1
    fi

    # Check if the port is listening
    if sudo netstat -tlnp | grep -q ":8001"; then
        echo "Backend is listening on port 8001."
        break
    fi
    
    if [ $i -eq $TIMEOUT ]; then
        echo "Error: Backend did not start listening on port 8001 within $TIMEOUT seconds."
        cleanup
        exit 1
    fi
    sleep 1
done

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
