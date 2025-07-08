#!/bin/bash

# Script to start both backend and frontend for AutoBot

echo "Starting AutoBot application..."

# Function to handle Ctrl+C (SIGINT)
cleanup() {
    echo "Received Ctrl+C. Terminating all processes..."
    # Kill all background processes started by this script
    pkill -P $$ -f "python main.py"
    pkill -P $$ -f "npm run dev"
    # Kill any gnome-terminal processes started by this script
    pkill -P $$ -f "gnome-terminal"
    echo "All processes terminated."
    exit 1
}

# Trap Ctrl+C (SIGINT) and call cleanup function
trap cleanup SIGINT

# Start the FastAPI backend in a new terminal
echo "Starting FastAPI backend..."
gnome-terminal -- bash -c "cd '$(dirname "$0")' && python main.py; exec bash" &

# Wait a bit to ensure backend is starting
sleep 3

# Start the Vue.js frontend development server
echo "Starting Vue.js frontend..."
cd "$(dirname "$0")/autobot-vue"
npm run dev &

echo "AutoBot application started. Backend on port 8000, Frontend on port 5173."
echo "You can access the frontend at http://localhost:5173/"

# Wait for background processes to keep the script running
wait
