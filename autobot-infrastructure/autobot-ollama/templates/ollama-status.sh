#!/bin/bash
# AutoBot Ollama - Status Script
# Manual intervention script for checking the Ollama service status

SERVICE_NAME="autobot-ollama"
HEALTH_PORT=11434

echo "=== AutoBot Ollama Status ==="
echo ""

# Check systemd status
echo "Systemd Status:"
systemctl status "${SERVICE_NAME}" --no-pager 2>/dev/null | head -10 || echo "Service not installed via systemd"
echo ""

# Check if process is running
echo "Process Check:"
if pgrep -f "ollama serve" > /dev/null; then
    echo "Ollama process is running"
    pgrep -af "ollama serve" | head -3
else
    echo "Ollama process is NOT running"
fi
echo ""

# Health check
echo "API Health Check:"
if curl -s "http://127.0.0.1:${HEALTH_PORT}/api/tags" > /dev/null 2>&1; then
    echo "Ollama API is responding"
else
    echo "Ollama API is NOT responding"
fi
echo ""

# Available models
echo "Loaded Models:"
MODELS=$(curl -s "http://127.0.0.1:${HEALTH_PORT}/api/tags" 2>/dev/null)
if [[ -n "${MODELS}" ]]; then
    echo "${MODELS}" | grep -o '"name":"[^"]*"' | cut -d'"' -f4 || echo "No models found"
else
    echo "Could not query models"
fi
echo ""

# GPU status
echo "GPU Status:"
if command -v nvidia-smi &> /dev/null; then
    nvidia-smi --query-gpu=name,memory.used,memory.total,utilization.gpu --format=csv,noheader 2>/dev/null || echo "GPU query failed"
else
    echo "nvidia-smi not available"
fi
echo ""

# Disk usage for models
echo "Model Storage:"
MODEL_PATH="/opt/autobot/ollama/models"
if [[ -d "${MODEL_PATH}" ]]; then
    du -sh "${MODEL_PATH}" 2>/dev/null || echo "Could not check storage"
else
    echo "Model path not found: ${MODEL_PATH}"
fi
echo ""

# Recent logs
echo "Recent Logs (last 10 lines):"
if systemctl list-unit-files "${SERVICE_NAME}.service" &>/dev/null; then
    sudo journalctl -u "${SERVICE_NAME}" -n 10 --no-pager 2>/dev/null || echo "No systemd logs"
elif [[ -f /opt/autobot/ollama/ollama.log ]]; then
    tail -10 /opt/autobot/ollama/ollama.log
else
    echo "No logs available"
fi
