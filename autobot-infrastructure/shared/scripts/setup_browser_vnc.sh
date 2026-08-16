#!/bin/bash
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
#
# Automated VNC setup for Browser VM — headed Playwright mode (#1939)
# Uses VncAuth (password-protected). Requires vncpasswd to be set.

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/lib/ssot-config.sh" 2>/dev/null || true

BROWSER_VM_IP="${AUTOBOT_BROWSER_SERVICE_HOST:-localhost}"
SSH_KEY="${AUTOBOT_SSH_KEY:-$HOME/.ssh/autobot_key}"
BROWSER_USER="${AUTOBOT_SSH_USER:-autobot}"

echo "========================================="
echo "AutoBot Browser VM VNC Setup (Secure)"
echo "========================================="
echo ""

run_on_browser_vm() {
    ssh -i "$SSH_KEY" "$BROWSER_USER@$BROWSER_VM_IP" "$@"
}

# Step 1: Check if VNC components are installed
echo "[1/7] Checking VNC installation..."
if run_on_browser_vm "dpkg -l | grep -q tigervnc-standalone-server"; then
    echo "  TigerVNC already installed"
else
    echo "  TigerVNC not found - please run installation first"
    exit 1
fi

# Step 2: Verify VNC password is set
echo "[2/7] Verifying VNC password..."
if run_on_browser_vm "test -f /home/autobot/.vnc/passwd"; then
    echo "  VNC password file exists"
else
    echo "  VNC password not set. Setting now..."
    echo "  (You will be prompted to enter a VNC password)"
    run_on_browser_vm "mkdir -p /home/autobot/.vnc && vncpasswd /home/autobot/.vnc/passwd"
fi

# Step 3: Kill any existing VNC servers
echo "[3/7] Cleaning up existing VNC sessions..."
run_on_browser_vm "vncserver -kill :1 2>/dev/null || true"
run_on_browser_vm "pkill -9 websockify 2>/dev/null || true"
echo "  Cleanup complete"

# Step 4: Start VNC server with password auth
echo "[4/7] Starting VNC server on display :1 (VncAuth)..."
run_on_browser_vm "/usr/bin/vncserver :1 \
    -localhost no \
    -SecurityTypes VncAuth,TLSVnc \
    -rfbport 5901 \
    -geometry 1920x1080 \
    -depth 24"
echo "  VNC server started on :1 (port 5901, password-protected)"

# Step 5: Start websockify for noVNC access
# #13076: web root is /opt/novnc, matching autobot-slm-backend/ansible/roles/
# vnc/defaults/main.yml novnc_path — NOT the distro /usr/share/novnc, which
# roles/vnc removes (#13069) and which otherwise serves a stale pre-VeNCrypt
# client (#13060). This script does not install noVNC itself; run the vnc role
# (or an equivalent pinned install) first so /opt/novnc exists.
echo "[5/7] Starting websockify for noVNC..."
run_on_browser_vm "nohup /usr/bin/websockify \
    --web ${AUTOBOT_NOVNC_PATH:-/opt/novnc} \
    --cert=/etc/autobot/certs/server-cert.pem \
    --key=/etc/autobot/certs/server-key.pem \
    --ssl-only \
    localhost:6080 \
    localhost:5901 \
    > /tmp/websockify.log 2>&1 &"
sleep 2
echo "  websockify started on port 6080"

# Step 6: Configure Playwright for headed mode
echo "[6/7] Configuring Playwright for headed mode..."
run_on_browser_vm "cd /home/autobot && cat > .env << 'ENVEOF'
# Playwright configuration - headed mode for VNC visibility
HEADLESS=false
DISPLAY=:1
ENVEOF"
echo "  Playwright configured for headed mode on DISPLAY :1"

# Step 7: Restart Playwright server
echo "[7/7] Restarting Playwright server..."
run_on_browser_vm "pkill -f playwright-server.js 2>/dev/null || true"
run_on_browser_vm "cd /home/autobot && mkdir -p logs && \
    nohup node playwright-server.js > logs/playwright.log 2>&1 &"
sleep 3
echo "  Playwright server restarted"

echo ""
echo "========================================="
echo "  Browser VM VNC Setup Complete!"
echo "========================================="
echo ""
echo "VNC Access (password-protected):"
echo "  - VNC Server: $BROWSER_VM_IP:5901"
echo "  - noVNC Web:  http://$BROWSER_VM_IP:6080/vnc.html"
echo ""
echo "Playwright:"
echo "  - API Server: http://$BROWSER_VM_IP:3000"
echo "  - Mode: Headed (visible browser on VNC)"
echo ""
