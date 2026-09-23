#!/bin/bash
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# Detect AutoBot deployment environment

# The env files this repo actually tracks (#15143). Four of the five branches
# below used to name a file outside this set, so every one of them silently
# fell through to "using defaults" instead of loading anything.
TRACKED_ENV_FILES=(".env.docker" ".env.example" ".env.localhost" ".env.native-vm" ".env.network" ".env.network-template")

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

# Export the detected environment. Set already (e.g. by a test forcing one
# branch) wins over detection, since faking /proc/version, /.dockerenv or the
# docker socket to reach a specific branch is not worth the trouble.
AUTOBOT_ENVIRONMENT="${AUTOBOT_ENVIRONMENT:-$(detect_environment)}"
echo "🔍 Detected environment: $AUTOBOT_ENVIRONMENT"

case $AUTOBOT_ENVIRONMENT in
    "wsl-docker-desktop")
        echo "📦 WSL with Docker Desktop on Windows"
        echo "   Using localhost for service access"
        ENV_FILE=".env.localhost"
        ;;
    "linux-native" | "wsl-native-docker" | "containerized")
        # #15143: none of the three real modes this repo tracks -- localhost,
        # native-vm (a genuinely distributed multi-VM deployment), network --
        # is what these three actually describe (same-host Docker networking,
        # and in-container networking, respectively). Guessing one would
        # point services at the wrong host silently; fail instead.
        echo "❌ No environment file is mapped for '$AUTOBOT_ENVIRONMENT' yet (#15143)"
        echo "   Tracked env files: ${TRACKED_ENV_FILES[*]}"
        exit 1
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
