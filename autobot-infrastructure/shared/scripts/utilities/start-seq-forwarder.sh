#!/bin/bash
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# Start Seq Log Forwarder for AutoBot

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "🚀 Starting Seq Log Forwarder..."

# Check if Seq is running
if ! curl -s http://localhost:5341/api > /dev/null; then
    echo "❌ Error: Seq is not running at http://localhost:5341"
    echo "   Please start Seq first with: docker-compose up -d seq"
    exit 1
fi

# Install aiohttp if needed
if ! python3 -c "import aiohttp" 2>/dev/null; then
    echo "📦 Installing aiohttp..."
    pip install aiohttp
fi

# Start the forwarder
echo "✅ Starting log forwarder..."
echo "   Forwarding logs from: $SCRIPT_DIR/logs/"
echo "   To Seq at: http://localhost:5341"
echo ""

# Run the forwarder
python3 scripts/seq_log_forwarder.py --tail-and-forward
