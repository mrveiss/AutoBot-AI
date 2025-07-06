#!/bin/bash

# Script to start both backend and frontend for AutoBot

echo "Starting AutoBot application..."

# Stop any existing processes on port 8001 (backend)
echo "Stopping any existing processes on port 8001..."
if lsof -i :8001 -t > /dev/null; then
    lsof -i :8001 -t | xargs kill -9
    echo "Processes on port 8001 terminated."
else
    echo "No process found on port 8001."
fi

# Stop any existing processes on port 8080 (frontend)
echo "Stopping any existing processes on port 8080..."
if lsof -i :8080 -t > /dev/null; then
    lsof -i :8080 -t | xargs kill -9
    echo "Processes on port 8080 terminated."
else
    echo "No process found on port 8080."
fi

# Start the FastAPI backend on port 8001
echo "Starting FastAPI backend on port 8001..."
python main.py &

# Start the Vue frontend on port 8080 from autobot-vue/dist
echo "Starting Vue frontend on port 8080..."
if [ -d "autobot-vue/dist" ]; then
    cd autobot-vue/dist
    python -m http.server 8080 &
    cd ../..
    echo "Vue frontend started at http://localhost:8080/"
else
    echo "Vue frontend directory autobot-vue/dist not found. Please ensure the frontend is built."
fi

echo "AutoBot application started."
echo "Backend available at http://localhost:8001/"
echo "Frontend available at http://localhost:8080/"
