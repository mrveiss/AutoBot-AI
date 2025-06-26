#!/bin/bash

# Script to start both backend and frontend for AutoBot

echo "Starting AutoBot application..."

# Start the FastAPI backend in a new terminal
echo "Starting FastAPI backend on port 8000..."
# Assuming your main.py uses an environment variable or argument for port,
# or you are using uvicorn which can be configured.
# Example using uvicorn with a common pattern:
# uvicorn main:app --host 0.0.0.0 --port 8000 &
# For simplicity, we'll assume python main.py starts on 8000 or can be configured.
python main.py &

# Serve the static frontend files using a simple HTTP server
echo "Serving static frontend files from frontend/static on port 8080..."
cd frontend/static
python -m http.server 8080 &

echo "AutoBot application started."
echo "Backend available on port 8000."
echo "Frontend available at http://localhost:8080/"
