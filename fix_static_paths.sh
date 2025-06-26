#!/bin/bash

SCRIPT_NAME="fix_static_paths.sh"

echo "--- Starting $SCRIPT_NAME ---"

# Kill any lingering 'mv' processes from previous attempts
echo "Killing any lingering 'mv' processes related to frontend/index.html..."
ps aux | grep "mv frontend/index.html frontend/templates/index.html" | grep -v grep | awk '{print $2}' | xargs kill || true
sleep 1 # Give a moment for processes to terminate

# Check if frontend/index.html exists before attempting to move
if [ -f "frontend/index.html" ]; then
    echo "frontend/index.html found. Moving it to frontend/templates/index.html..."
    # Use timeout to prevent hanging indefinitely
    timeout 10s mv frontend/index.html frontend/templates/index.html
    MV_EXIT_CODE=$?
    if [ $MV_EXIT_CODE -eq 124 ]; then
        echo "Error: 'mv' command timed out. The file might be locked or there's a permission issue."
        echo "Please check 'frontend/index.html' manually."
        exit 1
    elif [ $MV_EXIT_CODE -ne 0 ]; then
        echo "Error: Failed to move frontend/index.html. Exit code: $MV_EXIT_CODE"
        echo "Please check permissions or if the file is in use."
        exit 1
    else
        echo "Successfully moved frontend/index.html to frontend/templates/index.html."
    fi
else
    echo "frontend/index.html not found. Assuming it has already been moved or does not exist."
fi

echo "--- Finished $SCRIPT_NAME ---"
