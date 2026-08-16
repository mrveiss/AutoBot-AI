#!/bin/bash
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# Fix VNC to show actual desktop environment
# Run with: sudo bash fix-vnc-desktop.sh

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
VNC_USER="${AUTOBOT_VNC_USER:-autobot}"
VNC_HOME="/home/${VNC_USER}"

echo "Setting up VNC with XFCE desktop..."

# Stop existing services
systemctl stop novnc.service x11vnc.service xvfb.service 2>/dev/null || true

# Kill any existing VNC servers
pkill -9 Xvfb 2>/dev/null || true
pkill -9 x11vnc 2>/dev/null || true
pkill -9 Xtigervnc 2>/dev/null || true

# Create proper xstartup for XFCE
mkdir -p ${VNC_HOME}/.vnc
cat > ${VNC_HOME}/.vnc/xstartup << 'EOF'
#!/bin/bash
unset SESSION_MANAGER
unset DBUS_SESSION_BUS_ADDRESS

# Start dbus
eval $(dbus-launch --sh-syntax)
export DBUS_SESSION_BUS_ADDRESS

# Set background
xsetroot -solid "#2E3440" &

# Start XFCE desktop
exec startxfce4
EOF
chmod +x ${VNC_HOME}/.vnc/xstartup
chown "${VNC_USER}:${VNC_USER}" ${VNC_HOME}/.vnc/xstartup

# Create VNC password (random, displayed once)
VNC_PASS=$(openssl rand -base64 12 | tr -dc 'a-zA-Z0-9' | head -c 16)
echo "$VNC_PASS" | vncpasswd -f > ${VNC_HOME}/.vnc/passwd
echo "Generated VNC password: $VNC_PASS"
chmod 600 ${VNC_HOME}/.vnc/passwd
chown "${VNC_USER}:${VNC_USER}" ${VNC_HOME}/.vnc/passwd

# Create TigerVNC service (runs its own X server with desktop)
cat > /etc/systemd/system/tigervnc.service << EOF
[Unit]
Description=TigerVNC Server with XFCE Desktop
After=network.target

[Service]
Type=simple
User=${VNC_USER}
Group=${VNC_USER}
Environment=HOME=/home/${VNC_USER}
WorkingDirectory=/home/${VNC_USER}
ExecStart=/usr/bin/tigervncserver -fg -geometry 1920x1080 -depth 24 -SecurityTypes VncAuth -passwd ${VNC_HOME}/.vnc/passwd -xstartup ${VNC_HOME}/.vnc/xstartup :1
ExecStop=/usr/bin/tigervncserver -kill :1
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

# Update noVNC to connect to TigerVNC (port 5901 for display :1)
# #13076: /opt/novnc, matching autobot-slm-backend/ansible/roles/vnc/defaults/
# main.yml novnc_path — NOT the distro /usr/share/novnc, which roles/vnc
# removes (#13069) and which otherwise serves a stale pre-VeNCrypt client
# (#13060). This script does not install noVNC itself; run the vnc role (or
# an equivalent pinned install) first so /opt/novnc exists.
cat > /etc/systemd/system/novnc.service << EOF
[Unit]
Description=noVNC Web Interface
After=tigervnc.service
Requires=tigervnc.service

[Service]
Type=simple
User=${VNC_USER}
Group=${VNC_USER}
WorkingDirectory=/opt/novnc
ExecStart=/usr/bin/websockify --web /opt/novnc \\
    --cert=/etc/autobot/certs/server-cert.pem \\
    --key=/etc/autobot/certs/server-key.pem \\
    --ssl-only \\
    localhost:6080 localhost:5901
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

# Disable old services
systemctl disable xvfb.service x11vnc.service 2>/dev/null || true

echo "Reloading systemd..."
systemctl daemon-reload

echo "Enabling services..."
systemctl enable tigervnc.service novnc.service

echo "Starting TigerVNC..."
systemctl start tigervnc.service
sleep 3

echo "Starting noVNC..."
systemctl start novnc.service
sleep 2

echo ""
echo "Checking status..."
systemctl status tigervnc.service --no-pager -l || true
echo "---"
systemctl status novnc.service --no-pager -l || true

echo ""
echo "Checking ports..."
ss -tlnp | grep -E "5901|6080" || echo "Waiting for ports..."

echo ""
echo "Done! Access noVNC at http://localhost:6080"
echo "VNC password was displayed during setup (search output above)"
