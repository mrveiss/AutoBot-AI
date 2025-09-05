#!/bin/bash
# Runtime setup - only runs when container starts, not during build
# This avoids Docker build hanging on apt-get

# Check if we need to install packages (only on first run)
if [ ! -f /app/.packages_installed ]; then
    echo "Installing runtime packages (first run only)..."
    
    # Set non-interactive to avoid prompts
    export DEBIAN_FRONTEND=noninteractive
    
    # Quick timeout on apt-get - if it fails, continue anyway
    timeout 30 apt-get update 2>/dev/null || echo "Skipping apt update"
    
    # Only install if really needed
    # timeout 30 apt-get install -y curl git 2>/dev/null || echo "Skipping package install"
    
    # Mark as complete so we don't run again
    touch /app/.packages_installed
fi

# Start the actual application
exec "$@"