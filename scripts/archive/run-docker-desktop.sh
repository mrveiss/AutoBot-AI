#!/bin/bash
# AutoBot Docker Desktop Startup Script
# This script ensures proper Docker Desktop environment is loaded before starting

# Set Docker API version for compatibility with Docker Desktop 4.44.3
export DOCKER_API_VERSION=1.43

# Disable proxy for Docker operations in WSL
export HTTP_PROXY=
export HTTPS_PROXY=
export NO_PROXY=*

# Load Docker Desktop environment
source ./set-docker-desktop-env.sh

# Pass all arguments to run_agent.sh
./run_agent.sh "$@"