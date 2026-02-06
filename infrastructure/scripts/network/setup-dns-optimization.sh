#!/bin/bash
# AutoBot DNS Optimization Setup

set -e

echo "🚀 Setting up AutoBot DNS optimization..."

# Method 1: Host-level DNS Cache Service (systemd)
echo "📋 Option 1: Install host-level DNS cache service? (y/n)"
read -r install_host_dns

if [[ $install_host_dns =~ ^[Yy]$ ]]; then
    echo "🔧 Installing host-level DNS cache service..."
    chmod +x dns-cache-service.py install-dns-cache.sh
    ./install-dns-cache.sh
fi

# Method 2: Container-level /etc/hosts optimization
echo "🏠 Setting up container DNS optimization..."

# Test current DNS resolution speed
echo "🧪 Testing current DNS resolution speed..."
time_before=$(python3 -c "
import time, socket
start = time.time()
try:
    socket.gethostbyname('host.docker.internal')
    print(f'{(time.time() - start) * 1000:.1f}ms')
except:
    print('FAILED')
")

echo "Current DNS resolution time: $time_before"

# Create optimized /etc/hosts entries
echo "📝 Creating optimized DNS mappings..."

# Get host IP
host_ip=$(python3 -c "
import socket
try:
    print(socket.gethostbyname('host.docker.internal'))
except:
    import subprocess
    result = subprocess.run(['ip', 'route', 'show', 'default'],
                          capture_output=True, text=True)
    print(result.stdout.split()[2] if result.stdout else '172.17.0.1')
")

echo "Detected host IP: $host_ip"

# Create DNS entries file
cat > /tmp/autobot-dns-entries << EOF
# AutoBot DNS Optimization
$host_ip host.docker.internal
$host_ip backend.autobot
$host_ip api.autobot
127.0.0.1 localhost.autobot
EOF

echo "📋 Generated DNS entries:"
cat /tmp/autobot-dns-entries

# Option to add to system /etc/hosts
echo "🏠 Add entries to system /etc/hosts? (y/n)"
read -r add_system_hosts

if [[ $add_system_hosts =~ ^[Yy]$ ]]; then
    echo "🔧 Adding entries to /etc/hosts..."
    sudo sh -c 'cat /tmp/autobot-dns-entries >> /etc/hosts'
    echo "✅ Added to system /etc/hosts"
fi

# Method 3: Container startup optimization
echo "🐳 Setting up container DNS optimization..."

# Make DNS init script executable
chmod +x docker/dns-sidecar/dns-init.sh

# Create wrapper script for run_agent_unified.sh
cat > dns-optimized-run.sh << 'EOF'
#!/bin/bash
# DNS-Optimized AutoBot Runner

echo "🚀 Starting AutoBot with DNS optimization..."

# Pre-populate DNS cache
echo "📋 Pre-populating DNS cache..."
python3 dns-cache-service.py --once --cache-file /tmp/autobot-dns-cache.json 2>/dev/null || true

# Add DNS entries to /etc/hosts if not already there
if ! grep -q "AutoBot DNS Optimization" /etc/hosts 2>/dev/null; then
    if [ -f /tmp/autobot-dns-entries ]; then
        echo "📝 Adding DNS entries to /etc/hosts..."
        sudo sh -c 'cat /tmp/autobot-dns-entries >> /etc/hosts' 2>/dev/null || true
    fi
fi

# Run the normal startup
exec ./run_agent_unified.sh "$@"
EOF

chmod +x dns-optimized-run.sh

# Test DNS resolution after optimization
echo "🧪 Testing optimized DNS resolution..."
time_after=$(python3 -c "
import time, socket
start = time.time()
try:
    socket.gethostbyname('host.docker.internal')
    print(f'{(time.time() - start) * 1000:.1f}ms')
except:
    print('FAILED')
")

echo "Optimized DNS resolution time: $time_after"

echo ""
echo "✅ DNS optimization setup complete!"
echo ""
echo "🎯 Usage options:"
echo "  1. Use optimized runner:  ./dns-optimized-run.sh --dev"
echo "  2. Check DNS cache:       python3 dns-cache-service.py --status"
echo "  3. View host entries:     cat /etc/hosts | grep AutoBot"
echo "  4. Manual DNS resolve:    nslookup host.docker.internal"
echo ""
echo "📊 Performance improvement:"
echo "  Before: $time_before"
echo "  After:  $time_after"
