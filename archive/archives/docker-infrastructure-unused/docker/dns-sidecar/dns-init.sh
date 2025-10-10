#!/bin/bash
# DNS Resolver Sidecar Init Script
# Injects local DNS resolution into any container

set -e

echo "🔧 Initializing AutoBot DNS resolver..."

# Create DNS resolver directory
mkdir -p /opt/autobot-dns
cd /opt/autobot-dns

# Download DNS resolver if not present
if [ ! -f "local-dns-resolver.py" ]; then
    echo "📥 Installing local DNS resolver..."
    
    # Create the resolver script inline (embedded)
    cat > local-dns-resolver.py << 'RESOLVER_SCRIPT'
#!/usr/bin/env python3
import socket
import time
import json
import threading
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - DNS - %(message)s')
logger = logging.getLogger(__name__)

# Quick DNS mappings for AutoBot
DNS_MAP = {
    "host.docker.internal": "HOST_IP",
    "backend.autobot": "HOST_IP", 
    "api.autobot": "HOST_IP",
    "redis.autobot": "redis",
    "localhost": "127.0.0.1"
}

def get_host_ip():
    """Get Docker host IP"""
    try:
        return socket.gethostbyname("host.docker.internal")
    except:
        # Fallback to default gateway
        try:
            import subprocess
            result = subprocess.run(['ip', 'route', 'show', 'default'], 
                                  capture_output=True, text=True, timeout=5)
            return result.stdout.split()[2]
        except:
            return "172.17.0.1"

def update_hosts():
    """Update /etc/hosts with fast mappings"""
    try:
        host_ip = get_host_ip()
        entries = ["# AutoBot Fast DNS"]
        
        for hostname, target in DNS_MAP.items():
            if target == "HOST_IP":
                entries.append(f"{host_ip}\t{hostname}")
            else:
                try:
                    ip = socket.gethostbyname(target) if target != "127.0.0.1" else target
                    entries.append(f"{ip}\t{hostname}")
                except:
                    pass
        
        # Append to /etc/hosts
        with open("/etc/hosts", "a") as f:
            f.write("\n" + "\n".join(entries) + "\n")
        
        logger.info(f"✅ Added {len(entries)-1} DNS entries to /etc/hosts")
    except Exception as e:
        logger.warning(f"Could not update /etc/hosts: {e}")

def dns_daemon():
    """Background DNS refresh daemon"""
    while True:
        try:
            update_hosts()
            time.sleep(60)  # Refresh every minute
        except Exception as e:
            logger.error(f"DNS daemon error: {e}")
            time.sleep(10)

if __name__ == "__main__":
    logger.info("🚀 Starting AutoBot DNS resolver")
    update_hosts()  # Initial update
    
    # Start background daemon
    daemon_thread = threading.Thread(target=dns_daemon, daemon=True)
    daemon_thread.start()
    
    # Keep alive
    try:
        while True:
            time.sleep(30)
    except KeyboardInterrupt:
        logger.info("DNS resolver stopped")
RESOLVER_SCRIPT
    
    chmod +x local-dns-resolver.py
fi

# Start DNS resolver in background
echo "🚀 Starting DNS resolver daemon..."
python3 local-dns-resolver.py &
DNS_PID=$!

# Save PID for cleanup
echo $DNS_PID > /tmp/dns-resolver.pid

echo "✅ AutoBot DNS resolver running (PID: $DNS_PID)"

# If this script is called with arguments, execute them
if [ $# -gt 0 ]; then
    echo "🎯 Executing: $@"
    exec "$@"
else
    # Keep the script running
    wait $DNS_PID
fi