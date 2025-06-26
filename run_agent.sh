#!/bin/bash

# Script to start both backend and frontend for AutoBot

echo "Starting AutoBot application..."

# Start the FastAPI backend in a new terminal
echo "Starting FastAPI backend..."
xterm -e "cd /home/kali/Desktop/AutoBot && python main.py; bash" &

# Wait a bit to ensure backend is starting
sleep 3

# Start the Vue.js frontend development server
echo "Starting Vue.js frontend..."
cd /home/kali/Desktop/AutoBot/autobot-vue
npm run dev -- --port=5174 &

echo "AutoBot application started. Backend on port 8000, Vue.js Frontend on port 5174."
echo "You can access the frontend at http://localhost:5174/"
