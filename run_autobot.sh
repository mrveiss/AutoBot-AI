#!/bin/bash

# Script to start both backend and frontend for AutoBot

echo "Starting AutoBot application..."

# Start the FastAPI backend in a new terminal
echo "Starting FastAPI backend..."
gnome-terminal -- bash -c "cd /home/kali/Desktop/AutoBot && python main.py; exec bash" &

# Wait a bit to ensure backend is starting
sleep 3

# Start the Vue.js frontend development server
echo "Starting Vue.js frontend..."
cd /home/kali/Desktop/AutoBot/autobot-vue
npm run dev &

echo "AutoBot application started. Backend on port 8000, Frontend on port 5173."
echo "You can access the frontend at http://localhost:5173/"
