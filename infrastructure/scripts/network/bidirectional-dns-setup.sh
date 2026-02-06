#!/bin/bash
# Bidirectional DNS Setup for AutoBot
# Provides both host→container and container→host name resolution

set -e

echo "🔄 Setting up bidirectional DNS resolution..."

# Step 1: Test current resolution
echo "🧪 Testing current DNS resolution..."

echo "Host → Container:"
if timeout 2 bash -c "echo >/dev/tcp/autobot-redis/6379" 2>/dev/null; then
    echo "  ✅ autobot-redis:6379 reachable"
else
    echo "  ❌ autobot-redis:6379 NOT reachable"
fi

echo "Container → Host:"
docker exec autobot-frontend sh -c "timeout 2 nc -z host.docker.internal 8001" 2>/dev/null && {
    echo "  ✅ host.docker.internal:8001 reachable from container"
} || {
    echo "  ❌ host.docker.internal:8001 NOT reachable from container"
}

# Step 2: Get container IPs from Docker network
echo ""
echo "📋 Getting container IP addresses..."

get_container_ip() {
    docker inspect "$1" --format='{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}' 2>/dev/null
}

# Map container IPs
declare -A CONTAINERS
CONTAINERS[autobot-redis]=$(get_container_ip autobot-redis)
CONTAINERS[autobot-frontend]=$(get_container_ip autobot-frontend)
CONTAINERS[autobot-ai-stack]=$(get_container_ip autobot-ai-stack)
CONTAINERS[autobot-npu-worker]=$(get_container_ip autobot-npu-worker)
CONTAINERS[autobot-browser]=$(get_container_ip autobot-browser)
CONTAINERS[autobot-seq]=$(get_container_ip autobot-seq)

echo "Container IP mappings:"
for container in "${!CONTAINERS[@]}"; do
    ip="${CONTAINERS[$container]}"
    if [ -n "$ip" ]; then
        printf "  %-20s → %s\n" "$container" "$ip"
    else
        printf "  %-20s → %s\n" "$container" "NOT RUNNING"
    fi
done

# Step 3: Update host /etc/hosts for host→container resolution
echo ""
echo "🏠 Updating host /etc/hosts..."

# Remove old AutoBot entries
sudo sed -i '/# AutoBot DNS - Start/,/# AutoBot DNS - End/d' /etc/hosts

# Add new entries
{
    echo ""
    echo "# AutoBot DNS - Start"
    echo "# Generated: $(date)"
    echo ""

    for container in "${!CONTAINERS[@]}"; do
        ip="${CONTAINERS[$container]}"
        if [ -n "$ip" ] && [ "$ip" != "NOT RUNNING" ]; then
            # Add multiple aliases for convenience
            short_name=$(echo "$container" | sed 's/autobot-//')
            echo "$ip    $container $container.autobot $short_name.autobot"
        fi
    done

    echo ""
    echo "# AutoBot DNS - End"
    echo ""
} | sudo tee -a /etc/hosts > /dev/null

echo "✅ Updated /etc/hosts with container mappings"

# Step 4: Update Docker Compose for container→host resolution
echo ""
echo "🐳 Updating Docker Compose for bidirectional DNS..."

# Add extra_hosts to all services for consistent container→host resolution
python3 << 'PYTHON_SCRIPT'
import yaml
import sys

compose_file = "docker-compose.yml"

try:
    with open(compose_file, 'r') as f:
        compose = yaml.safe_load(f)

    # Get host IP for host.docker.internal mapping
    import subprocess
    import socket

    try:
        host_ip = socket.gethostbyname("host.docker.internal")
    except:
        # Fallback to default gateway
        result = subprocess.run(['ip', 'route', 'show', 'default'],
                              capture_output=True, text=True)
        host_ip = result.stdout.split()[2] if result.stdout else "172.17.0.1"

    # Standard extra_hosts for all containers
    standard_extra_hosts = [
        "host.docker.internal:host-gateway",
        f"backend.autobot:{host_ip}",
        f"api.autobot:{host_ip}",
        "autobot-redis:redis",
        "redis.autobot:redis"
    ]

    # Update each service
    services_updated = 0
    for service_name, service_config in compose.get('services', {}).items():
        if service_name != 'dns-cache':  # Skip our DNS cache service
            if 'extra_hosts' not in service_config:
                service_config['extra_hosts'] = []

            # Merge with existing extra_hosts
            existing = service_config['extra_hosts']
            for host_entry in standard_extra_hosts:
                if host_entry not in existing:
                    existing.append(host_entry)

            services_updated += 1

    # Write back
    with open(compose_file, 'w') as f:
        yaml.dump(compose, f, default_flow_style=False, sort_keys=False)

    print(f"✅ Updated {services_updated} services in docker-compose.yml")

except Exception as e:
    print(f"❌ Could not update docker-compose.yml: {e}")
    sys.exit(1)
PYTHON_SCRIPT

# Step 5: Create DNS monitoring script
echo ""
echo "📋 Creating DNS monitoring script..."

cat > dns-monitor.sh << 'EOF'
#!/bin/bash
# DNS Resolution Monitor

echo "🔍 AutoBot DNS Resolution Status"
echo "==============================="
echo ""

# Test host→container
echo "Host → Container:"
containers=("autobot-redis:6379" "autobot-frontend:5173" "autobot-ai-stack:8080")
for container_port in "${containers[@]}"; do
    IFS=: read container port <<< "$container_port"
    if timeout 2 bash -c "echo >/dev/tcp/$container/$port" 2>/dev/null; then
        echo "  ✅ $container:$port"
    else
        echo "  ❌ $container:$port"
    fi
done

echo ""

# Test container→host
echo "Container → Host:"
if docker exec autobot-frontend sh -c "timeout 2 nc -z host.docker.internal 8001" 2>/dev/null; then
    echo "  ✅ host.docker.internal:8001 (from frontend)"
else
    echo "  ❌ host.docker.internal:8001 (from frontend)"
fi

if docker exec autobot-frontend sh -c "timeout 2 nc -z backend.autobot 8001" 2>/dev/null; then
    echo "  ✅ backend.autobot:8001 (from frontend)"
else
    echo "  ❌ backend.autobot:8001 (from frontend)"
fi

echo ""

# Show current mappings
echo "Current /etc/hosts AutoBot entries:"
grep -A 10 "# AutoBot DNS - Start" /etc/hosts | grep -B 10 "# AutoBot DNS - End" | grep -v "^#" | grep -v "^$" || echo "  No AutoBot entries found"
EOF

chmod +x dns-monitor.sh

# Step 6: Create automatic DNS updater service
echo ""
echo "⚙️ Creating DNS update service..."

cat > update-dns.py << 'PYTHON_SCRIPT'
#!/usr/bin/env python3
import subprocess, json, time

def update_container_dns():
    try:
        # Get container IPs
        result = subprocess.run(['docker', 'network', 'inspect', 'autobot-network'],
                              capture_output=True, text=True, check=True)
        network = json.loads(result.stdout)[0]

        entries = ["# AutoBot DNS - Start", f"# Updated: {time.strftime('%Y-%m-%d %H:%M:%S')}"]

        for container_info in network.get('Containers', {}).values():
            name = container_info.get('Name')
            ip = container_info.get('IPv4Address', '').split('/')[0]
            if name and ip:
                short = name.replace('autobot-', '')
                entries.append(f"{ip}    {name} {name}.autobot {short}.autobot")

        entries.extend(["# AutoBot DNS - End", ""])

        # Update /etc/hosts
        subprocess.run(['sudo', 'sed', '-i', '/# AutoBot DNS - Start/,/# AutoBot DNS - End/d', '/etc/hosts'])

        with open('/tmp/autobot-dns-entries', 'w') as f:
            f.write('\n'.join(entries))

        subprocess.run(['sudo', 'sh', '-c', 'cat /tmp/autobot-dns-entries >> /etc/hosts'])
        print(f"✅ Updated DNS entries: {len(entries)-3} containers")

    except Exception as e:
        print(f"❌ DNS update failed: {e}")

if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "--daemon":
        while True:
            update_container_dns()
            time.sleep(60)
    else:
        update_container_dns()
PYTHON_SCRIPT

chmod +x update-dns.py

# Step 7: Test the setup
echo ""
echo "🧪 Testing bidirectional DNS setup..."
./dns-monitor.sh

echo ""
echo "✅ Bidirectional DNS setup complete!"
echo ""
echo "📋 Available commands:"
echo "  ./dns-monitor.sh           - Check DNS resolution status"
echo "  ./update-dns.py            - Update container DNS mappings"
echo "  ./update-dns.py --daemon   - Run DNS updater as daemon"
echo ""
echo "🎯 Test connectivity:"
echo "  curl http://autobot-frontend:5173/   # Host → Container"
echo "  docker exec autobot-frontend curl host.docker.internal:8001/api/health   # Container → Host"
echo ""
echo "🔄 To apply container→host changes, restart containers:"
echo "  docker compose down && docker compose up -d"
