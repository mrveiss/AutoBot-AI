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

# #15143: four of the five branches used to name a file nothing tracks or
# generates (.env.wsl-docker-desktop, .env.linux-native x2, .env.distributed).
# generate-env-files.py/validate-env-files.py only know three modes --
# localhost, native-vm, network -- and native-vm is for a genuinely
# distributed multi-machine deployment this script has no way to detect.
# Every non-localhost Docker scenario here (native Linux+Docker, WSL with a
# native Docker daemon, or the script itself running inside a container)
# needs container/service network addressing rather than localhost
# port-forwarding, which is what .env.network provides -- so all three map
# to it.
case $AUTOBOT_ENVIRONMENT in
    "wsl-docker-desktop")
        echo "📦 WSL with Docker Desktop on Windows"
        echo "   Using localhost for service access"
        ENV_FILE=".env.localhost"
        ;;
    "linux-native")
        echo "🐧 Native Linux with Docker"
        echo "   Using network addressing for direct container access"
        ENV_FILE=".env.network"
        ;;
    "wsl-native-docker")
        echo "📦 WSL with native Docker"
        echo "   Using network addressing for direct container access"
        ENV_FILE=".env.network"
        ;;
    "containerized")
        echo "🐳 Running inside Docker"
        echo "   Using network addressing for container-to-container access"
        ENV_FILE=".env.network"
        ;;
    *)
        echo "⚠️  No Docker detected or unsupported environment"
        ENV_FILE=".env.localhost"
        ;;
esac

# Load the appropriate environment file. #15143: every branch above now
# names a file generate-env-files.py actually produces and this repo tracks,
# so a miss here means that file was deleted or renamed, not a mapping gap --
# fail loudly rather than silently export nothing and continue on defaults.
if [ -f "$ENV_FILE" ]; then
    export $(grep -v '^#' "$ENV_FILE" | xargs)
    echo "✅ Loaded environment from $ENV_FILE"
else
    echo "❌ Environment file $ENV_FILE not found for detected environment '$AUTOBOT_ENVIRONMENT' -- run generate-env-files.py, or check it was not deleted/renamed" >&2
    exit 1
fi

# Export for use in other scripts
export AUTOBOT_ENVIRONMENT
export AUTOBOT_ENV_FILE="$ENV_FILE"
