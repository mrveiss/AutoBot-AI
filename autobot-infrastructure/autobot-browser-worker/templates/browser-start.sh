#!/bin/bash
# AutoBot Browser Worker - Start Script
# Manual intervention script for starting the browser worker service

set -e

SERVICE_NAME="autobot-browser-worker"
HEALTH_PORT=3000
INSTALL_DIR="/opt/autobot/autobot-browser-worker"

echo "Starting AutoBot Browser Worker..."

# Check if service file exists
if ! systemctl list-unit-files "${SERVICE_NAME}.service" &>/dev/null; then
    echo "Error: Systemd service not installed"
    echo "Install with: sudo cp autobot-browser-worker.service /etc/systemd/system/"
    exit 1
fi

# Check if already running
if systemctl is-active --quiet "${SERVICE_NAME}"; then
    echo "Browser Worker is already running"
    exit 0
fi

# Ensure data directories exist
sudo -u autobot mkdir -p "${INSTALL_DIR}"/{data,screenshots,logs,browsers}

# Check if Playwright browsers are installed
if [[ ! -d "${INSTALL_DIR}/browsers/chromium"* ]]; then
    echo "Installing Playwright browsers..."
    sudo -u autobot "${INSTALL_DIR}/venv/bin/playwright" install chromium
fi

# Start the service
echo "Starting service..."
sudo systemctl start "${SERVICE_NAME}"

# Wait for service to be ready
echo "Waiting for Browser Worker to be ready..."
sleep 5

# Verify it's responding
MAX_WAIT=30
WAITED=0
while [[ ${WAITED} -lt ${MAX_WAIT} ]]; do
    if curl -s "http://127.0.0.1:${HEALTH_PORT}/health" > /dev/null 2>&1; then
        echo "AutoBot Browser Worker started successfully"
        exit 0
    fi
    sleep 1
    ((WAITED++))
done

echo "Warning: Browser Worker started but health check not responding"
echo "Check logs: sudo journalctl -u ${SERVICE_NAME} -n 50"
exit 1
