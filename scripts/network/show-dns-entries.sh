#!/bin/bash
# Show DNS entries needed for bidirectional resolution

echo "🔍 AutoBot Container IP Addresses:"
echo "=================================="

get_container_ip() {
    docker inspect "$1" --format='{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}' 2>/dev/null
}

declare -A CONTAINERS
CONTAINERS[autobot-redis]=$(get_container_ip autobot-redis)
CONTAINERS[autobot-frontend]=$(get_container_ip autobot-frontend)  
CONTAINERS[autobot-ai-stack]=$(get_container_ip autobot-ai-stack)
CONTAINERS[autobot-npu-worker]=$(get_container_ip autobot-npu-worker)
CONTAINERS[autobot-browser]=$(get_container_ip autobot-browser)
CONTAINERS[autobot-seq]=$(get_container_ip autobot-seq)

echo "Current container IPs:"
for container in "${!CONTAINERS[@]}"; do
    ip="${CONTAINERS[$container]}"
    if [ -n "$ip" ]; then
        printf "  %-20s → %s\n" "$container" "$ip"
    fi
done

echo ""
echo "📝 Add these entries to /etc/hosts for Host→Container resolution:"
echo "================================================================="
echo ""
echo "# AutoBot DNS - Start"
echo "# Generated: $(date)"

for container in "${!CONTAINERS[@]}"; do
    ip="${CONTAINERS[$container]}"
    if [ -n "$ip" ]; then
        short_name=$(echo "$container" | sed 's/autobot-//')
        echo "$ip    $container $container.autobot $short_name.autobot"
    fi
done

echo "# AutoBot DNS - End"

echo ""
echo "🚀 To apply these changes, run:"
echo "sudo bash -c 'cat >> /etc/hosts << EOF"
echo ""
echo "# AutoBot DNS - Start"
for container in "${!CONTAINERS[@]}"; do
    ip="${CONTAINERS[$container]}"
    if [ -n "$ip" ]; then
        short_name=$(echo "$container" | sed 's/autobot-//')
        echo "$ip    $container $container.autobot $short_name.autobot"
    fi
done
echo "# AutoBot DNS - End"
echo "EOF'"

echo ""
echo "🧪 After adding entries, test with:"
echo "  curl http://redis.autobot:8002/          # Redis Insight"
echo "  curl http://frontend.autobot:5173/       # Frontend"
echo "  ping autobot-redis                       # Test resolution"