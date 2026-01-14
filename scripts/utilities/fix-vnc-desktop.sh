#!/bin/bash
# Fix VNC to show actual desktop environment
# Run with: sudo bash fix-vnc-desktop.sh

set -e

echo "Setting up VNC with XFCE desktop..."

# Stop existing services
systemctl stop novnc.service x11vnc.service xvfb.service 2>/dev/null || true

# Kill any existing VNC servers
pkill -9 Xvfb 2>/dev/null || true
pkill -9 x11vnc 2>/dev/null || true
pkill -9 Xtigervnc 2>/dev/null || true

# Create proper xstartup for XFCE
mkdir -p /home/kali/.vnc
cat > /home/kali/.vnc/xstartup << 'EOF'
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
chmod +x /home/kali/.vnc/xstartup
chown kali:kali /home/kali/.vnc/xstartup

# Create VNC password
echo "kali" | vncpasswd -f > /home/kali/.vnc/passwd
chmod 600 /home/kali/.vnc/passwd
chown kali:kali /home/kali/.vnc/passwd

# Create TigerVNC service (runs its own X server with desktop)
cat > /etc/systemd/system/tigervnc.service << 'EOF'
[Unit]
Description=TigerVNC Server with XFCE Desktop
After=network.target

[Service]
Type=simple
User=kali
Group=kali
Environment=HOME=/home/kali
WorkingDirectory=/home/kali
ExecStart=/usr/bin/tigervncserver -fg -geometry 1920x1080 -depth 24 -SecurityTypes VncAuth -passwd /home/kali/.vnc/passwd -xstartup /home/kali/.vnc/xstartup :1
ExecStop=/usr/bin/tigervncserver -kill :1
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

# Update noVNC to connect to TigerVNC (port 5901 for display :1)
cat > /etc/systemd/system/novnc.service << 'EOF'
[Unit]
Description=noVNC Web Interface
After=tigervnc.service
Requires=tigervnc.service

[Service]
Type=simple
User=kali
Group=kali
WorkingDirectory=/usr/share/novnc
ExecStart=/usr/bin/websockify --web /usr/share/novnc 6080 localhost:5901
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
echo "VNC password: kali"
