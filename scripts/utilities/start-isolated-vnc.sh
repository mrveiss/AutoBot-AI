#!/bin/bash
# Start VNC with complete isolation from local display

# Kill any existing VNC sessions
vncserver -kill :2 2>/dev/null

# Kill any XFCE processes that might be on wrong display
pkill -f xfce4-panel 2>/dev/null
pkill -f xfdesktop 2>/dev/null

# Start VNC in completely clean environment - no local display access
env -i \
    HOME="$HOME" \
    USER="$USER" \
    SHELL="$SHELL" \
    PATH="/usr/local/bin:/usr/bin:/bin" \
    LANG="$LANG" \
    vncserver :2 \
    -geometry 1920x1080 \
    -depth 24 \
    -SecurityTypes None \
    -localhost no \
    --I-KNOW-THIS-IS-INSECURE

echo "VNC server started on display :2"
echo "Access via: http://192.168.168.17:6080/vnc.html"