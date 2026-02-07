#!/bin/bash
# AutoBot - Start Redis Service on VM
# Starts only the Redis service on 172.16.168.23

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

SSH_KEY="$HOME/.ssh/autobot_key"
SSH_USER="autobot"
REDIS_IP="172.16.168.23"

log() {
    echo -e "${BLUE}[$(date +'%Y-%m-%d %H:%M:%S')]${NC} $1"
}

error() {
    echo -e "${RED}[ERROR]${NC} $1" >&2
}

success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

main() {
    echo -e "${GREEN}🗄️  Starting Redis Service${NC}"
    echo -e "${BLUE}VM: $REDIS_IP${NC}"
    echo ""

    if [ ! -f "$SSH_KEY" ]; then
        error "SSH key not found: $SSH_KEY"
        echo "Run: bash setup.sh ssh-keys"
        exit 1
    fi

    log "Connecting to Redis VM..."

    ssh -i "$SSH_KEY" "$SSH_USER@$REDIS_IP" << 'EOF'
        echo "Installing Redis Stack if not already installed..."
        if ! command -v redis-server >/dev/null 2>&1; then
            echo "Installing Redis Stack..."
            curl -fsSL https://packages.redis.io/gpg | sudo gpg --dearmor -o /usr/share/keyrings/redis-archive-keyring.gpg
            echo "deb [signed-by=/usr/share/keyrings/redis-archive-keyring.gpg] https://packages.redis.io/deb $(lsb_release -cs) main" | sudo tee /etc/apt/sources.list.d/redis.list
            sudo apt-get update
            sudo apt-get install -y redis-stack-server netcat-openbsd
        fi

        echo "Stopping existing Redis services..."
        sudo systemctl stop redis-stack-server 2>/dev/null || true
        sudo pkill redis-server 2>/dev/null || true

        echo "Configuring Redis Stack..."
        sudo mkdir -p /etc/redis-stack
        sudo tee /etc/redis-stack/redis-stack.conf > /dev/null << 'REDIS_CONFIG'
# Redis Stack Configuration for AutoBot
port 6379
bind 0.0.0.0
protected-mode no
save 900 1
save 300 10
save 60 10000
dir /var/lib/redis-stack
logfile /var/log/redis-stack/redis-stack.log
loglevel notice

# RedisInsight on port 8002 (avoiding conflict with backend port 8001)
loadmodule /opt/redis-stack/lib/redisinsight.so port=8002
REDIS_CONFIG

        echo "Creating Redis data directory..."
        sudo mkdir -p /var/lib/redis-stack /var/log/redis-stack
        sudo chown -R autobot:autobot /var/lib/redis-stack /var/log/redis-stack

        echo "Starting Redis Stack service..."
        sudo systemctl enable redis-stack-server
        sudo systemctl start redis-stack-server

        echo "Waiting for Redis to be ready..."
        for i in {1..30}; do
            if timeout 2 bash -c "</dev/tcp/localhost/6379" 2>/dev/null; then
                echo "Redis is ready!"

                # Test Redis connection
                if redis-cli ping | grep -q "PONG"; then
                    echo "Redis connection test successful"
                fi

                exit 0
            fi
            sleep 1
            echo -n "."
        done

        echo ""
        echo "Warning: Redis may need more time to start"
        echo "Check service status: sudo systemctl status redis-stack-server"
        echo "Check logs: sudo journalctl -u redis-stack-server -f"
EOF

    if [ $? -eq 0 ]; then
        success "Redis service started on $REDIS_IP:6379"
        echo ""
        echo -e "${CYAN}Redis URL: redis://$REDIS_IP:6379${NC}"
        echo -e "${CYAN}RedisInsight: http://$REDIS_IP:8002${NC}"
        echo -e "${BLUE}Test connection: redis-cli -h $REDIS_IP ping${NC}"
        echo -e "${BLUE}Check logs: ssh $SSH_USER@$REDIS_IP 'sudo journalctl -u redis-stack-server -f'${NC}"
    else
        error "Failed to start Redis service"
        exit 1
    fi
}

main
