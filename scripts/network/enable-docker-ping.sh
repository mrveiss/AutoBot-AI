#!/bin/bash

# Enable Host-to-Container Ping for AutoBot Docker Network
# This script configures iptables to allow host ping to Docker containers

echo "🔧 AutoBot Docker Ping Configuration"
echo "===================================="
echo ""

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    echo "❌ This script needs to be run as root/sudo"
    echo "Usage: sudo ./enable-docker-ping.sh"
    exit 1
fi

echo "Current Docker networks:"
docker network ls | grep autobot

echo ""
echo "Configuring iptables rules..."

# Create DOCKER-USER chain if it doesn't exist
iptables -t filter -N DOCKER-USER 2>/dev/null || echo "DOCKER-USER chain already exists"

# Allow traffic from host to AutoBot containers
echo "1. Adding rule for AutoBot network (172.18.0.0/16)..."
iptables -I DOCKER-USER -s 172.18.0.0/16 -j ACCEPT
iptables -I DOCKER-USER -d 172.18.0.0/16 -j ACCEPT

# Allow ICMP (ping) specifically
echo "2. Adding ICMP (ping) rules..."
iptables -I DOCKER-USER -p icmp --icmp-type echo-request -s 172.18.0.0/16 -j ACCEPT
iptables -I DOCKER-USER -p icmp --icmp-type echo-reply -d 172.18.0.0/16 -j ACCEPT

# Allow host to ping containers
echo "3. Adding host-to-container ping rules..."
iptables -I DOCKER-USER -s 127.0.0.1 -d 172.18.0.0/16 -p icmp -j ACCEPT
iptables -I DOCKER-USER -s 172.18.0.0/16 -d 127.0.0.1 -p icmp -j ACCEPT

# Enable forwarding for the AutoBot subnet
echo "4. Enabling IP forwarding for AutoBot subnet..."
iptables -I FORWARD -s 172.18.0.0/16 -j ACCEPT
iptables -I FORWARD -d 172.18.0.0/16 -j ACCEPT

echo ""
echo "✅ Configuration complete!"
echo ""
echo "Testing connectivity..."

# Test Redis container if running
if docker ps --format '{{.Names}}' | grep -q autobot-redis; then
    REDIS_IP=$(docker inspect autobot-redis --format='{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}')
    echo "Testing ping to Redis container ($REDIS_IP):"
    if ping -c 1 -W 2 "$REDIS_IP" >/dev/null 2>&1; then
        echo "✅ Host can now ping Redis container!"
    else
        echo "❌ Ping still not working. May need Docker restart."
    fi
else
    echo "ℹ️  No Redis container running to test"
fi

echo ""
echo "Rules added:"
echo "- Allow traffic to/from 172.18.0.0/16 (AutoBot network)"
echo "- Allow ICMP (ping) packets"
echo "- Allow host-to-container communication"
echo ""
echo "⚠️  Note: These rules will be lost on reboot."
echo "    Add them to your firewall configuration for persistence."
echo ""
echo "To make persistent, add to /etc/iptables/rules.v4 or similar."

# Save current rules for reference
echo ""
echo "Current DOCKER-USER rules:"
iptables -L DOCKER-USER -n --line-numbers 2>/dev/null || echo "Could not list DOCKER-USER rules"