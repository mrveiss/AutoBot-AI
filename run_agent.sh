#!/bin/bash

# Script to start both backend and frontend for AutoBot

echo "Starting AutoBot application..."

# --- Start Xvfb and VNC Server ---
XVFB_DISPLAY=":1"
VNC_PORT="5900"
echo "Starting X virtual framebuffer on display ${XVFB_DISPLAY}..."
Xvfb ${XVFB_DISPLAY} -screen 0 1280x720x24 &
XVFB_PID=$!
echo "Starting x11vnc on display ${XVFB_DISPLAY} port ${VNC_PORT}..."
x11vnc -display ${XVFB_DISPLAY} -nopw -listen localhost -rfbport ${VNC_PORT} -bg -quiet &
X11VNC_PID=$!
echo "Xvfb and x11vnc started."

# Start the FastAPI backend in a new terminal
echo "Starting FastAPI backend on port 8000..."
python /path/to/your/project/root/main.py & # Replace with your actual path

# Serve the static frontend files using a simple HTTP server
echo "Serving static frontend files from frontend/static on port 8080..."
cd frontend/static
python -m http.server 8080 &

echo "AutoBot application started."
echo "Backend available on port 8000."
echo "Frontend available at http://localhost:8080/"
