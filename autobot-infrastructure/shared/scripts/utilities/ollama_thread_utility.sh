#!/bin/bash
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# Fix Ollama thread count to reduce CPU usage and GUI lag


# #13149: this defaulted to the deployed install, so running it from a checkout
# read or wrote the LIVE install instead of this tree. The shared helper resolves
# the root from this file's own location; AUTOBOT_PROJECT_ROOT still overrides.
# shellcheck source=scripts/lib/project_root.sh
source "$(dirname "${BASH_SOURCE[0]}")/../../../../scripts/lib/project_root.sh"
echo "🔧 Fixing Ollama thread count (11 → 6 threads)"
echo "================================================"
echo ""

# Check current status
echo "Current Ollama status:"
systemctl status ollama.service | head -15
echo ""

# Copy new service file
echo "📝 Updating Ollama systemd service file..."
sudo cp ${PROJECT_ROOT}/ollama.service.new /etc/systemd/system/ollama.service

if [ $? -eq 0 ]; then
    echo "✅ Service file updated"
else
    echo "❌ Failed to update service file"
    exit 1
fi

# Reload systemd
echo ""
echo "🔄 Reloading systemd daemon..."
sudo systemctl daemon-reload

if [ $? -eq 0 ]; then
    echo "✅ Systemd reloaded"
else
    echo "❌ Failed to reload systemd"
    exit 1
fi

# Restart Ollama
echo ""
echo "♻️  Restarting Ollama service..."
sudo systemctl restart ollama.service

if [ $? -eq 0 ]; then
    echo "✅ Ollama restarted"
else
    echo "❌ Failed to restart Ollama"
    exit 1
fi

# Wait for service to stabilize
echo ""
echo "⏳ Waiting for Ollama to stabilize (5 seconds)..."
sleep 5

# Verify new configuration
echo ""
echo "✅ New Ollama status:"
systemctl status ollama.service | head -15

echo ""
echo "📊 To verify thread count when model is running:"
echo "   ps aux | grep 'ollama runner' | grep -v grep"
echo ""
echo "✅ Done! Thread count will be 6 when next model loads."
