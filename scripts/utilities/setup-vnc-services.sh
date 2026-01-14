#!/bin/bash
# Setup VNC services for AutoBot noVNC access
# Run with: sudo bash setup-vnc-services.sh

set -e

echo "Setting up VNC services..."

# Create Xvfb service (virtual framebuffer)
cat > /etc/systemd/system/xvfb@.service << 'EOF'
[Unit]
Description=X Virtual Framebuffer %i
After=network.target

[Service]
Type=simple
User=kali
Group=kali
ExecStart=/usr/bin/Xvfb :%i -screen 0 1920x1080x24
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

# Create TigerVNC service
cat > /etc/systemd/system/vncserver@.service << 'EOF'
[Unit]
Description=TigerVNC Server %i
After=xvfb@%i.service
Requires=xvfb@%i.service

[Service]
Type=simple
User=kali
Group=kali
Environment=DISPLAY=:%i
Environment=HOME=/home/kali
WorkingDirectory=/home/kali
ExecStartPre=/bin/sh -c 'mkdir -p /home/kali/.vnc && echo "kali" | vncpasswd -f > /home/kali/.vnc/passwd && chmod 600 /home/kali/.vnc/passwd'
ExecStart=/usr/bin/tigervncserver -fg -xstartup /usr/bin/startxfce4 -geometry 1920x1080 -SecurityTypes VncAuth -passwd /home/kali/.vnc/passwd :%i
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

# Update noVNC service to not require vncserver (we'll use x11vnc instead for simpler setup)
cat > /etc/systemd/system/novnc.service << 'EOF'
[Unit]
Description=noVNC Web Interface
After=x11vnc.service
Wants=x11vnc.service
Wants=network.target

[Service]
Type=simple
User=kali
Group=kali
WorkingDirectory=/usr/share/novnc
ExecStart=/usr/bin/websockify --web /usr/share/novnc 6080 localhost:5900
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

# Create x11vnc service (shares existing X display - simpler approach)
cat > /etc/systemd/system/x11vnc.service << 'EOF'
[Unit]
Description=x11vnc VNC Server
After=display-manager.service
Wants=display-manager.service

[Service]
Type=simple
User=kali
Group=kali
Environment=DISPLAY=:0
ExecStart=/usr/bin/x11vnc -display :0 -forever -shared -rfbauth /home/kali/.vnc/passwd -rfbport 5900 -noxdamage
ExecStartPre=/bin/sh -c 'mkdir -p /home/kali/.vnc && echo "kali" | /usr/bin/x11vnc -storepasswd /home/kali/.vnc/passwd'
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

echo "Reloading systemd daemon..."
systemctl daemon-reload

echo "Enabling services..."
systemctl enable x11vnc.service novnc.service

echo "Starting services..."
systemctl start x11vnc.service
sleep 2
systemctl start novnc.service

echo "Checking status..."
systemctl status x11vnc.service --no-pager || true
systemctl status novnc.service --no-pager || true

echo ""
echo "VNC services setup complete!"
echo "noVNC should be accessible at http://localhost:6080"
