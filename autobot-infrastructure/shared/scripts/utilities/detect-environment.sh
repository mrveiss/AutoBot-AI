#!/bin/bash
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# Detect AutoBot deployment environment

detect_environment() {
    # Check if running in WSL
    if grep -qi microsoft /proc/version 2>/dev/null; then
        # In WSL, check for Docker Desktop integration
        if [ -S /var/run/docker.sock ] && ls -la /var/run/docker.sock | grep -q root; then
            # Docker socket exists and owned by root = Docker Desktop integration
            echo "wsl-docker-desktop"
        elif docker version 2>&1 | grep -q "Docker Desktop"; then
            echo "wsl-docker-desktop"
        else
            echo "wsl-native-docker"
        fi
    elif [ -f /.dockerenv ]; then
        # Running inside a Docker container
        echo "containerized"
    else
        # Native Linux
        if command -v docker >/dev/null 2>&1; then
            echo "linux-native"
        else
            echo "no-docker"
        fi
    fi
}

# Export the detected environment
AUTOBOT_ENVIRONMENT=$(detect_environment)
echo "🔍 Detected environment: $AUTOBOT_ENVIRONMENT"

case $AUTOBOT_ENVIRONMENT in
    "wsl-docker-desktop")
        echo "📦 WSL with Docker Desktop on Windows"
        echo "   Using localhost for service access"
        ENV_FILE=".env.wsl-docker-desktop"
        ;;
    "linux-native")
        echo "🐧 Native Linux with Docker"
        echo "   Using direct Docker IPs for performance"
        ENV_FILE=".env.linux-native"
        ;;
    "wsl-native-docker")
        echo "📦 WSL with native Docker"
        echo "   Using Docker IPs directly"
        ENV_FILE=".env.linux-native"
        ;;
    "containerized")
        echo "🐳 Running inside Docker"
        ENV_FILE=".env.distributed"
        ;;
    *)
        echo "⚠️  No Docker detected or unsupported environment"
        ENV_FILE=".env.localhost"
        ;;
esac

# Load the appropriate environment file
if [ -f "$ENV_FILE" ]; then
    export $(grep -v '^#' "$ENV_FILE" | xargs)
    echo "✅ Loaded environment from $ENV_FILE"
else
    echo "⚠️  Environment file $ENV_FILE not found, using defaults"
fi

# Export for use in other scripts
export AUTOBOT_ENVIRONMENT
export AUTOBOT_ENV_FILE="$ENV_FILE"
