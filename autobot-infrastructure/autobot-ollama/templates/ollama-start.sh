#!/bin/bash
# AutoBot Ollama - Start Script
# Manual intervention script for starting the Ollama LLM service

set -e

SERVICE_NAME="autobot-ollama"
HEALTH_PORT=11434

echo "Starting AutoBot Ollama..."

# Check if Ollama is installed
if ! command -v ollama &> /dev/null; then
    echo "Error: Ollama is not installed"
    echo "Install with: curl -fsSL https://ollama.com/install.sh | sh"
    exit 1
fi

# Check if service file exists
if ! systemctl list-unit-files "${SERVICE_NAME}.service" &>/dev/null; then
    echo "Warning: Systemd service not installed, starting directly..."

    # Ensure directories exist
    mkdir -p /opt/autobot/ollama/models

    # Start directly
    OLLAMA_HOST="0.0.0.0:${HEALTH_PORT}" \
    OLLAMA_MODELS="/opt/autobot/ollama/models" \
    nohup ollama serve > /opt/autobot/ollama/ollama.log 2>&1 &

    echo "Started Ollama directly (PID: $!)"
else
    # Check if already running
    if systemctl is-active --quiet "${SERVICE_NAME}"; then
        echo "Ollama is already running"
        exit 0
    fi

    # Start via systemd
    echo "Starting via systemd..."
    sudo systemctl start "${SERVICE_NAME}"
fi

# Wait for service to be ready
echo "Waiting for Ollama to be ready..."
sleep 3

# Verify it's responding
MAX_WAIT=30
WAITED=0
while [[ ${WAITED} -lt ${MAX_WAIT} ]]; do
    if curl -s "http://127.0.0.1:${HEALTH_PORT}/api/tags" > /dev/null 2>&1; then
        echo "AutoBot Ollama started successfully"

        # List available models
        echo ""
        echo "Available models:"
        curl -s "http://127.0.0.1:${HEALTH_PORT}/api/tags" | grep -o '"name":"[^"]*"' | cut -d'"' -f4 || echo "No models loaded"
        exit 0
    fi
    sleep 1
    ((WAITED++))
done

echo "Warning: Ollama started but API not responding"
exit 1
