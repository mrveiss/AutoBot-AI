#!/bin/bash
# Install AutoBot DNS Cache Service

set -e

echo "🚀 Installing AutoBot DNS Cache Service..."

# Make the Python script executable
chmod +x dns-cache-service.py

# Install systemd service
echo "📋 Installing systemd service..."
sudo cp autobot-dns-cache.service /etc/systemd/system/
sudo systemctl daemon-reload

# Enable and start the service
echo "🔄 Enabling and starting DNS cache service..."
sudo systemctl enable autobot-dns-cache.service
sudo systemctl start autobot-dns-cache.service

# Wait a moment for initial cache
echo "⏳ Waiting for initial DNS cache..."
sleep 3

# Show status
echo "📊 DNS Cache Service Status:"
sudo systemctl status autobot-dns-cache.service --no-pager -l

echo ""
echo "📋 Cached DNS entries:"
python3 dns-cache-service.py --status

echo ""
echo "🏠 /etc/hosts entries (add these manually if desired):"
python3 dns-cache-service.py --hosts

echo ""
echo "✅ DNS Cache Service installed successfully!"
echo ""
echo "Commands:"
echo "  sudo systemctl status autobot-dns-cache    # Check status"
echo "  sudo systemctl restart autobot-dns-cache   # Restart service"
echo "  sudo journalctl -u autobot-dns-cache -f    # View logs"
echo "  python3 dns-cache-service.py --status      # Check cache status"