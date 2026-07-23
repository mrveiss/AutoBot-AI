#!/bin/bash
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# Quick test script for desktop access setup

echo "🧪 Testing desktop access setup requirements..."

echo -n "VNC Server: "
if command -v vncserver >/dev/null 2>&1; then
    echo "✅ Found"
else
    echo "❌ Missing (install with: sudo apt install tigervnc-standalone-server)"
fi

echo -n "Python3: "
if command -v python3 >/dev/null 2>&1; then
    echo "✅ Found"
else
    echo "❌ Missing"
fi

echo -n "Git: "
if command -v git >/dev/null 2>&1; then
    echo "✅ Found"
else
    echo "❌ Missing"
fi

echo -n "XFCE4: "
if command -v xfce4-session >/dev/null 2>&1; then
    echo "✅ Found"
else
    echo "❌ Missing (install with: sudo apt install xfce4)"
fi

echo -n "Websockify: "
if python3 -c "import websockify" 2>/dev/null; then
    echo "✅ Found"
else
    echo "⚠️  Will be installed automatically"
fi

echo -n "noVNC: "
if [ -d ~/.novnc ]; then
    echo "✅ Found"
else
    echo "⚠️  Will be downloaded automatically"
fi

echo
echo "🚀 Ready to test! Try running:"
echo "   ./run_agent_unified.sh --dev --desktop"
echo
echo "This will:"
echo "   1. Start AutoBot frontend on http://localhost:5173"
echo "   2. Start VNC server with XFCE4 desktop"
echo "   3. Start noVNC web client on http://localhost:6080"
echo "   4. Auto-open both in browser tabs"
echo "   5. Use password 'autobot' for VNC connection"
