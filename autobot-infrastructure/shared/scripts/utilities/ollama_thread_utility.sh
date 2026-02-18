#!/bin/bash
# Fix Ollama thread count to reduce CPU usage and GUI lag

echo "🔧 Fixing Ollama thread count (11 → 6 threads)"
echo "================================================"
echo ""

# Check current status
echo "Current Ollama status:"
systemctl status ollama.service | head -15
echo ""

# Copy new service file
echo "📝 Updating Ollama systemd service file..."
sudo cp /home/kali/Desktop/AutoBot/ollama.service.new /etc/systemd/system/ollama.service

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
