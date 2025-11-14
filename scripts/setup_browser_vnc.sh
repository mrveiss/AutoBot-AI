#!/bin/bash
# Automated VNC setup for Browser VM (172.16.168.25)
# Provides visual browser viewing for collaborative user/agent interaction

set -e

BROWSER_VM_IP="172.16.168.25"
SSH_KEY="$HOME/.ssh/autobot_key"
BROWSER_USER="autobot"

echo "========================================="
echo "AutoBot Browser VM VNC Setup"
echo "========================================="
echo ""

# Function to run command on Browser VM
run_on_browser_vm() {
    ssh -i "$SSH_KEY" "$BROWSER_USER@$BROWSER_VM_IP" "$@"
}

# Step 1: Check if VNC components are installed
echo "[1/6] Checking VNC installation..."
if run_on_browser_vm "dpkg -l | grep -q tigervnc-standalone-server"; then
    echo "✓ TigerVNC already installed"
else
    echo "✗ TigerVNC not found - please run installation first"
    exit 1
fi

# Step 2: Kill any existing VNC servers
echo "[2/6] Cleaning up existing VNC sessions..."
run_on_browser_vm "vncserver -kill :1 2>/dev/null || true"
run_on_browser_vm "pkill -9 websockify 2>/dev/null || true"
echo "✓ Cleanup complete"

# Step 3: Start VNC server (matches main machine setup)
echo "[3/6] Starting VNC server on display :1..."
run_on_browser_vm "/usr/bin/vncserver :1 \
    -localhost no \
    -SecurityTypes None \
    -rfbport 5901 \
    --I-KNOW-THIS-IS-INSECURE \
    -geometry 1920x1080 \
    -depth 24"
echo "✓ VNC server started on :1 (port 5901)"

# Step 4: Start websockify for noVNC access
echo "[4/6] Starting websockify for noVNC..."
run_on_browser_vm "nohup /usr/bin/websockify \
    --web /usr/share/novnc \
    0.0.0.0:6080 \
    localhost:5901 \
    > /tmp/websockify.log 2>&1 &"
sleep 2
echo "✓ websockify started on port 6080"

# Step 5: Configure Playwright for headed mode
echo "[5/6] Configuring Playwright for headed mode..."
run_on_browser_vm "cd /home/autobot && cat > .env << 'EOF'
# Playwright configuration - headed mode for VNC visibility
HEADLESS=false
DISPLAY=:1
EOF"
echo "✓ Playwright configured for headed mode on DISPLAY :1"

# Step 6: Restart Playwright server
echo "[6/6] Restarting Playwright server..."
run_on_browser_vm "pkill -f playwright-server.js 2>/dev/null || true"
run_on_browser_vm "cd /home/autobot && mkdir -p logs && nohup node playwright-server.js > logs/playwright.log 2>&1 &"
sleep 3
echo "✓ Playwright server restarted"

echo ""
echo "========================================="
echo "✓ Browser VM VNC Setup Complete!"
echo "========================================="
echo ""
echo "VNC Access:"
echo "  - VNC Server: $BROWSER_VM_IP:5901"
echo "  - noVNC Web:  http://$BROWSER_VM_IP:6080/vnc.html"
echo ""
echo "Playwright:"
echo "  - API Server: http://$BROWSER_VM_IP:3000"
echo "  - Mode: Headed (visible browser on VNC)"
echo ""
echo "Next steps:"
echo "  1. Test VNC connection: http://$BROWSER_VM_IP:6080/vnc.html"
echo "  2. Update frontend VNC URL configuration"
echo "  3. Test collaborative browser viewing"
echo ""
