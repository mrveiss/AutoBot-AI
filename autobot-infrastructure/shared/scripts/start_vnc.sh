#!/bin/bash
# Start VNC server for AutoBot desktop access

# Kill any existing VNC servers
vncserver -kill :1 2>/dev/null || true

# Start new VNC server
vncserver :1 -geometry 1920x1080 -depth 24

echo "VNC server started on :1 (port 5901)"
echo "Connect using VNC viewer to: localhost:5901"
