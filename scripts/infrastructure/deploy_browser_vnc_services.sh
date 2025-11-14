#!/bin/bash
# Infrastructure as Code: Deploy Browser VM VNC Services
# Uses systemd for proper service management and auto-restart

set -e

BROWSER_VM_IP="172.16.168.25"
SSH_KEY="$HOME/.ssh/autobot_key"
BROWSER_USER="autobot"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "================================================="
echo "AutoBot Browser VM - IaC Service Deployment"
echo "================================================="
echo ""

# Function to run command on Browser VM
run_on_browser_vm() {
    ssh -i "$SSH_KEY" "$BROWSER_USER@$BROWSER_VM_IP" "$@"
}

# Function to copy file to Browser VM
copy_to_browser_vm() {
    scp -i "$SSH_KEY" "$1" "$BROWSER_USER@$BROWSER_VM_IP:$2"
}

# Step 1: Copy systemd service files
echo "[1/5] Copying systemd service files..."
copy_to_browser_vm "$SCRIPT_DIR/browser-vnc.service" "/tmp/browser-vnc.service"
copy_to_browser_vm "$SCRIPT_DIR/browser-vnc-websockify.service" "/tmp/browser-vnc-websockify.service"
copy_to_browser_vm "$SCRIPT_DIR/browser-playwright.service" "/tmp/browser-playwright.service"
echo "✓ Service files copied"

# Step 2: Install services to systemd
echo "[2/5] Installing systemd services..."
run_on_browser_vm "sudo mv /tmp/browser-vnc.service /etc/systemd/system/"
run_on_browser_vm "sudo mv /tmp/browser-vnc-websockify.service /etc/systemd/system/"
run_on_browser_vm "sudo mv /tmp/browser-playwright.service /etc/systemd/system/"
run_on_browser_vm "sudo chmod 644 /etc/systemd/system/browser-*.service"
echo "✓ Services installed"

# Step 3: Reload systemd and enable services
echo "[3/5] Enabling services for auto-start..."
run_on_browser_vm "sudo systemctl daemon-reload"
run_on_browser_vm "sudo systemctl enable browser-vnc.service"
run_on_browser_vm "sudo systemctl enable browser-vnc-websockify.service"
run_on_browser_vm "sudo systemctl enable browser-playwright.service"
echo "✓ Services enabled"

# Step 4: Stop any manual processes
echo "[4/5] Stopping manual processes..."
run_on_browser_vm "pkill -f 'vncserver :1' 2>/dev/null || true"
run_on_browser_vm "pkill -f websockify 2>/dev/null || true"
run_on_browser_vm "pkill -f playwright-server.js 2>/dev/null || true"
sleep 2
echo "✓ Manual processes stopped"

# Step 5: Start services
echo "[5/5] Starting services..."
run_on_browser_vm "sudo systemctl start browser-vnc.service"
sleep 2
run_on_browser_vm "sudo systemctl start browser-vnc-websockify.service"
run_on_browser_vm "sudo systemctl start browser-playwright.service"
sleep 3
echo "✓ Services started"

echo ""
echo "================================================="
echo "✓ Infrastructure Deployment Complete!"
echo "================================================="
echo ""
echo "Service Status:"
run_on_browser_vm "sudo systemctl status browser-vnc.service browser-vnc-websockify.service browser-playwright.service --no-pager -l" || true
echo ""
echo "Access Points:"
echo "  - VNC Server: $BROWSER_VM_IP:5901"
echo "  - noVNC Web:  http://$BROWSER_VM_IP:6080/vnc.html"
echo "  - Playwright: http://$BROWSER_VM_IP:3000 (headed mode on DISPLAY :1)"
echo ""
echo "Service Management:"
echo "  - View logs:    ssh autobot@$BROWSER_VM_IP 'sudo journalctl -u browser-playwright.service -f'"
echo "  - Restart all:  ssh autobot@$BROWSER_VM_IP 'sudo systemctl restart browser-*.service'"
echo "  - Stop all:     ssh autobot@$BROWSER_VM_IP 'sudo systemctl stop browser-*.service'"
echo ""
