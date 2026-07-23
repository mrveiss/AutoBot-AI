#!/bin/bash
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
#
# Start VNC with complete isolation from local display (#1939)
# Uses VncAuth (password-protected). Requires ~/.vnc/passwd.

set -e

# Verify VNC password exists
if [ ! -f "$HOME/.vnc/passwd" ]; then
    echo "VNC password not set. Run 'vncpasswd' first."
    exit 1
fi

# Kill any existing VNC sessions on display :2
vncserver -kill :2 2>/dev/null || true

# Kill any XFCE processes that might be on wrong display
pkill -f xfce4-panel 2>/dev/null || true
pkill -f xfdesktop 2>/dev/null || true

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
    -SecurityTypes VncAuth,TLSVnc \
    -localhost no

echo "VNC server started on display :2 (password-protected)"
echo "Connect with a VNC client on port 5902"
