#!/bin/bash
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# Fix VNC for WSL (no physical display)
# Run with: sudo bash fix-vnc-wsl.sh

set -e

# #14036: resolve the VNC user ONCE, here, in the shell.
#
# The unit heredocs below are quoted (<< 'EOF'), which disables parameter
# expansion, so a ${...} written inside one lands in the unit file verbatim.
# systemd has no bash-style :- default syntax, so `User=${VNC_USER}`
# is not a valid directive value and the unit is broken on every run.
#
# $USER is not usable here either: this script is run with sudo, so $USER is
# root and the paths resolved to /home/root.
VNC_USER="${VNC_USER}"
VNC_HOME="/home/${VNC_USER}"

echo "Setting up VNC for WSL environment..."

# Stop existing services
systemctl stop x11vnc.service novnc.service 2>/dev/null || true

# Create Xvfb service (virtual framebuffer)
cat > /etc/systemd/system/xvfb.service << EOF
[Unit]
Description=X Virtual Framebuffer
After=network.target

[Service]
Type=simple
User=${VNC_USER}
Group=${VNC_USER}
ExecStart=/usr/bin/Xvfb :1 -screen 0 1920x1080x24
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

# Create x11vnc service that connects to Xvfb
cat > /etc/systemd/system/x11vnc.service << EOF
[Unit]
Description=x11vnc VNC Server for Xvfb
After=xvfb.service
Requires=xvfb.service

[Service]
Type=simple
User=${VNC_USER}
Group=${VNC_USER}
Environment=DISPLAY=:1
ExecStart=/usr/bin/x11vnc -display :1 -forever -shared -rfbauth ${VNC_HOME}/.vnc/passwd -rfbport 5900 -noxdamage -noxfixes
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

# Update noVNC service
# #13076: /opt/novnc, matching autobot-slm-backend/ansible/roles/vnc/defaults/
# main.yml novnc_path — NOT the distro /usr/share/novnc, which roles/vnc
# removes (#13069) and which otherwise serves a stale pre-VeNCrypt client
# (#13060). This script does not install noVNC itself; run the vnc role (or
# an equivalent pinned install) first so /opt/novnc exists.
cat > /etc/systemd/system/novnc.service << EOF
[Unit]
Description=noVNC Web Interface
After=x11vnc.service
Requires=x11vnc.service

[Service]
Type=simple
User=${VNC_USER}
Group=${VNC_USER}
WorkingDirectory=/opt/novnc
ExecStart=/usr/bin/websockify --web /opt/novnc \\
    --cert=/etc/autobot/certs/server-cert.pem \\
    --key=/etc/autobot/certs/server-key.pem \\
    --ssl-only \\
    localhost:6080 localhost:5900
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

# Ensure password file exists
mkdir -p ${VNC_HOME}/.vnc
if [ ! -f ${VNC_HOME}/.vnc/passwd ]; then
    VNC_PASS=$(openssl rand -base64 12 | tr -dc 'a-zA-Z0-9' | head -c 16)
    x11vnc -storepasswd "$VNC_PASS" ${VNC_HOME}/.vnc/passwd
    echo "Generated VNC password: $VNC_PASS"
fi
chown -R kali:kali ${VNC_HOME}/.vnc

echo "Reloading systemd..."
systemctl daemon-reload

echo "Enabling services..."
systemctl enable xvfb.service x11vnc.service novnc.service

echo "Starting services..."
systemctl start xvfb.service
sleep 2
systemctl start x11vnc.service
sleep 2
systemctl start novnc.service

echo ""
echo "Checking status..."
systemctl status xvfb.service --no-pager -l || true
echo "---"
systemctl status x11vnc.service --no-pager -l || true
echo "---"
systemctl status novnc.service --no-pager -l || true

echo ""
echo "Checking ports..."
ss -tlnp | grep -E "5900|6080" || echo "Ports not yet listening"

echo ""
echo "Done! noVNC should be at http://localhost:6080"
echo "VNC password was displayed during setup (search output above)"
