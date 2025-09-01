#!/bin/bash
# Docker Network DNS Helper
# Provides host-to-container DNS resolution

set -e

# Get AutoBot network containers
get_container_ips() {
    echo "🔍 AutoBot Container Network Map:"
    echo "=================================="
    
    docker network inspect autobot-network 2>/dev/null | jq -r '
        .[0].Containers // {} | 
        to_entries[] | 
        "\(.value.Name):\(.value.IPv4Address | split("/")[0])"
    ' | while IFS=: read container_name ip_address; do
        if [ -n "$container_name" ] && [ -n "$ip_address" ]; then
            printf "%-25s → %s\n" "$container_name" "$ip_address"
        fi
    done
}

# Generate /etc/hosts entries
generate_hosts_entries() {
    echo ""
    echo "🏠 /etc/hosts entries for host system:"
    echo "======================================"
    echo "# AutoBot Container DNS - $(date)"
    
    docker network inspect autobot-network 2>/dev/null | jq -r '
        .[0].Containers // {} | 
        to_entries[] | 
        "\(.value.IPv4Address | split("/")[0])\t\(.value.Name)\t\(.value.Name).autobot"
    ' | grep -v '^$'
}

# Add entries to /etc/hosts
add_to_hosts() {
    echo ""
    echo "🔧 Adding container entries to /etc/hosts..."
    
    # Remove old AutoBot entries
    sudo sed -i '/# AutoBot Container DNS/,/^$/d' /etc/hosts
    
    # Add new entries
    {
        echo ""
        generate_hosts_entries
        echo ""
    } | sudo tee -a /etc/hosts > /dev/null
    
    echo "✅ Container DNS entries added to /etc/hosts"
}

# Create container aliases
create_aliases() {
    cat > ~/.autobot_container_aliases << 'EOF'
# AutoBot Container Aliases
alias redis-cli-autobot='redis-cli -h autobot-redis'
alias curl-frontend='curl http://autobot-frontend:5173'
alias curl-ai-stack='curl http://autobot-ai-stack:8080'
alias curl-npu-worker='curl http://autobot-npu-worker:8081'
alias curl-browser='curl http://autobot-browser:3000'
alias logs-redis='docker logs -f autobot-redis'
alias logs-frontend='docker logs -f autobot-frontend'
alias logs-ai='docker logs -f autobot-ai-stack'
alias exec-redis='docker exec -it autobot-redis bash'
alias exec-frontend='docker exec -it autobot-frontend sh'
EOF
    
    echo "📋 Container aliases created in ~/.autobot_container_aliases"
    echo "   Add to ~/.bashrc: source ~/.autobot_container_aliases"
}

# Test connections
test_connections() {
    echo ""
    echo "🧪 Testing container connections from host:"
    echo "==========================================="
    
    containers=(
        "autobot-redis:6379"
        "autobot-frontend:5173"
        "autobot-ai-stack:8080"
        "autobot-npu-worker:8081"
        "autobot-browser:3000"
    )
    
    for container_port in "${containers[@]}"; do
        IFS=: read container port <<< "$container_port"
        
        if timeout 2 bash -c "echo >/dev/tcp/$container/$port" 2>/dev/null; then
            echo "✅ $container:$port - reachable"
        else
            echo "❌ $container:$port - not reachable"
        fi
    done
}

# Main menu
case "$1" in
    "list"|"")
        get_container_ips
        ;;
    "hosts")
        generate_hosts_entries
        ;;
    "install")
        get_container_ips
        add_to_hosts
        create_aliases
        test_connections
        ;;
    "test")
        test_connections
        ;;
    "aliases")
        create_aliases
        ;;
    *)
        echo "Usage: $0 [list|hosts|install|test|aliases]"
        echo ""
        echo "Commands:"
        echo "  list     - Show container IP mappings (default)"
        echo "  hosts    - Generate /etc/hosts entries"  
        echo "  install  - Add entries to /etc/hosts and create aliases"
        echo "  test     - Test container connectivity"
        echo "  aliases  - Create container command aliases"
        exit 1
        ;;
esac