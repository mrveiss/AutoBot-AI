#!/bin/bash
# AutoBot Ollama - Stop Script
# Manual intervention script for stopping the Ollama LLM service

set -e

SERVICE_NAME="autobot-ollama"

echo "Stopping AutoBot Ollama..."

# Try systemd first
if systemctl list-unit-files "${SERVICE_NAME}.service" &>/dev/null; then
    if systemctl is-active --quiet "${SERVICE_NAME}"; then
        echo "Stopping via systemd..."
        sudo systemctl stop "${SERVICE_NAME}"
    fi
fi

# Also kill any direct ollama processes
if pgrep -f "ollama serve" > /dev/null; then
    echo "Stopping ollama processes..."
    pkill -f "ollama serve" 2>/dev/null || true
fi

# Wait for clean stop
MAX_WAIT=15
WAITED=0
while pgrep -f "ollama serve" > /dev/null; do
    if [[ ${WAITED} -ge ${MAX_WAIT} ]]; then
        echo "Warning: Ollama did not stop within ${MAX_WAIT} seconds"
        echo "Force killing..."
        pkill -9 -f "ollama serve" 2>/dev/null || true
        break
    fi
    sleep 1
    ((WAITED++))
done

echo "AutoBot Ollama stopped"
