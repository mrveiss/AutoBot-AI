#!/bin/bash
# Fix VNC for WSL (no physical display)
# Run with: sudo bash fix-vnc-wsl.sh

set -e

echo "Setting up VNC for WSL environment..."

# Stop existing services
systemctl stop x11vnc.service novnc.service 2>/dev/null || true

# Create Xvfb service (virtual framebuffer)
cat > /etc/systemd/system/xvfb.service << 'EOF'
[Unit]
Description=X Virtual Framebuffer
After=network.target

[Service]
Type=simple
User=kali
Group=kali
ExecStart=/usr/bin/Xvfb :1 -screen 0 1920x1080x24
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

# Create x11vnc service that connects to Xvfb
cat > /etc/systemd/system/x11vnc.service << 'EOF'
[Unit]
Description=x11vnc VNC Server for Xvfb
After=xvfb.service
Requires=xvfb.service

[Service]
Type=simple
User=kali
Group=kali
Environment=DISPLAY=:1
ExecStart=/usr/bin/x11vnc -display :1 -forever -shared -rfbauth /home/kali/.vnc/passwd -rfbport 5900 -noxdamage -noxfixes
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

# Update noVNC service
cat > /etc/systemd/system/novnc.service << 'EOF'
[Unit]
Description=noVNC Web Interface
After=x11vnc.service
Requires=x11vnc.service

[Service]
Type=simple
User=kali
Group=kali
WorkingDirectory=/usr/share/novnc
ExecStart=/usr/bin/websockify --web /usr/share/novnc 6080 localhost:5900
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

# Ensure password file exists
mkdir -p /home/kali/.vnc
if [ ! -f /home/kali/.vnc/passwd ]; then
    x11vnc -storepasswd kali /home/kali/.vnc/passwd
fi
chown -R kali:kali /home/kali/.vnc

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
echo "VNC password: kali"
