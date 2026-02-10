#!/bin/bash

# AutoBot MCP Tracker Installation Script
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
_PROJECT_ROOT="$SCRIPT_DIR"
while [ "$_PROJECT_ROOT" != "/" ] && [ ! -f "$_PROJECT_ROOT/.env" ]; do
    _PROJECT_ROOT="$(dirname "$_PROJECT_ROOT")"
done
source "$_PROJECT_ROOT/infrastructure/shared/scripts/lib/ssot-config.sh" 2>/dev/null || true

echo "Installing AutoBot MCP Tracker..."

# Check if we're in the AutoBot directory
if [[ ! -f "CLAUDE.md" ]]; then
    echo "❌ Error: Please run this script from the AutoBot root directory"
    exit 1
fi

# Ensure mcp-autobot-tracker directory exists
if [[ ! -d "mcp-autobot-tracker" ]]; then
    echo "❌ Error: mcp-autobot-tracker directory not found"
    exit 1
fi

cd mcp-autobot-tracker

# Install dependencies
echo "📦 Installing Node.js dependencies..."
npm install

# Build the TypeScript project
echo "🔨 Building TypeScript project..."
npm run build

# Create log directories if they don't exist
echo "📁 Creating log directories..."
mkdir -p ../data/logs
touch ../data/logs/backend.log
touch ../data/logs/frontend.log
touch ../data/logs/redis.log

# Create systemd service file
echo "⚙️ Creating systemd service file..."
SERVICE_FILE="/etc/systemd/system/autobot-mcp-tracker.service"
INSTALL_DIR="$(pwd)"

sudo tee "$SERVICE_FILE" > /dev/null << EOF
[Unit]
Description=AutoBot MCP Tracker Service
After=network.target
Wants=network.target

[Service]
Type=simple
User=$(whoami)
Group=$(id -gn)
WorkingDirectory=$INSTALL_DIR
ExecStart=$(which node) $INSTALL_DIR/dist/index.js
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal
SyslogIdentifier=autobot-mcp-tracker

# Environment variables
Environment=NODE_ENV=production
Environment=REDIS_HOST=${AUTOBOT_REDIS_HOST:-172.16.168.23}
Environment=REDIS_PORT=6379

[Install]
WantedBy=multi-user.target
EOF

# Reload systemd and enable service
echo "🔄 Enabling systemd service..."
sudo systemctl daemon-reload
sudo systemctl enable autobot-mcp-tracker.service

# Create Claude Desktop configuration
echo "🖥️ Configuring Claude Desktop MCP..."

# Determine OS and Claude config location
if [[ "$OSTYPE" == "darwin"* ]]; then
    # macOS
    CLAUDE_CONFIG_DIR="$HOME/Library/Application Support/Claude"
elif [[ "$OSTYPE" == "linux-gnu"* ]]; then
    # Linux
    CLAUDE_CONFIG_DIR="$HOME/.config/Claude"
else
    echo "⚠️ Warning: Unknown OS type, using Linux config path"
    CLAUDE_CONFIG_DIR="$HOME/.config/Claude"
fi

mkdir -p "$CLAUDE_CONFIG_DIR"

# Create or update claude_desktop_config.json
CONFIG_FILE="$CLAUDE_CONFIG_DIR/claude_desktop_config.json"

if [[ -f "$CONFIG_FILE" ]]; then
    echo "📝 Updating existing Claude Desktop config..."
    # Backup existing config
    cp "$CONFIG_FILE" "$CONFIG_FILE.backup"

    # Use jq to add our MCP server configuration
    if command -v jq &> /dev/null; then
        jq '. + {
            "mcpServers": ((.mcpServers // {}) + {
                "autobot-tracker": {
                    "command": "'"$(which node)"'",
                    "args": ["'"$INSTALL_DIR/dist/index.js"'"],
                    "env": {
                        "REDIS_HOST": "${AUTOBOT_REDIS_HOST:-172.16.168.23}",
                        "REDIS_PORT": "${AUTOBOT_REDIS_PORT:-6379}"
                    }
                }
            })
        }' "$CONFIG_FILE" > "$CONFIG_FILE.tmp" && mv "$CONFIG_FILE.tmp" "$CONFIG_FILE"
    else
        echo "⚠️ jq not found, creating basic configuration..."
        cat > "$CONFIG_FILE" << EOF
{
    "mcpServers": {
        "autobot-tracker": {
            "command": "$(which node)",
            "args": ["$INSTALL_DIR/dist/index.js"],
            "env": {
                "REDIS_HOST": "${AUTOBOT_REDIS_HOST:-172.16.168.23}",
                "REDIS_PORT": "${AUTOBOT_REDIS_PORT:-6379}"
            }
        }
    }
}
EOF
    fi
else
    echo "📝 Creating new Claude Desktop config..."
    cat > "$CONFIG_FILE" << EOF
{
    "mcpServers": {
        "autobot-tracker": {
            "command": "$(which node)",
            "args": ["$INSTALL_DIR/dist/index.js"],
            "env": {
                "REDIS_HOST": "${AUTOBOT_REDIS_HOST:-172.16.168.23}",
                "REDIS_PORT": "${AUTOBOT_REDIS_PORT:-6379}"
            }
        }
    }
}
EOF
fi

# Create management scripts
echo "🛠️ Creating management scripts..."

# Start script
cat > start-mcp-tracker.sh << 'EOF'
#!/bin/bash
echo "🚀 Starting AutoBot MCP Tracker..."
sudo systemctl start autobot-mcp-tracker.service
sleep 2
sudo systemctl status autobot-mcp-tracker.service --no-pager
EOF

# Stop script
cat > stop-mcp-tracker.sh << 'EOF'
#!/bin/bash
echo "🛑 Stopping AutoBot MCP Tracker..."
sudo systemctl stop autobot-mcp-tracker.service
sudo systemctl status autobot-mcp-tracker.service --no-pager
EOF

# Status script
cat > status-mcp-tracker.sh << 'EOF'
#!/bin/bash
echo "📊 AutoBot MCP Tracker Status:"
echo "================================"
sudo systemctl status autobot-mcp-tracker.service --no-pager
echo ""
echo "📝 Recent logs:"
echo "================================"
journalctl -u autobot-mcp-tracker.service --no-pager -n 20
EOF

# Logs script
cat > logs-mcp-tracker.sh << 'EOF'
#!/bin/bash
echo "📖 Following AutoBot MCP Tracker logs..."
journalctl -u autobot-mcp-tracker.service -f
EOF

# Test script
cat > test-mcp-tracker.sh << 'EOF'
#!/bin/bash
echo "🧪 Testing AutoBot MCP Tracker..."

# Test Redis connection
echo "Testing Redis connection..."
if redis-cli -h ${AUTOBOT_REDIS_HOST:-172.16.168.23} -p ${AUTOBOT_REDIS_PORT:-6379} ping | grep -q PONG; then
    echo "✅ Redis connection successful"
else
    echo "❌ Redis connection failed"
    exit 1
fi

# Test service status
echo "Testing service status..."
if sudo systemctl is-active --quiet autobot-mcp-tracker.service; then
    echo "✅ Service is running"
else
    echo "❌ Service is not running"
    echo "Starting service..."
    sudo systemctl start autobot-mcp-tracker.service
    sleep 3
    if sudo systemctl is-active --quiet autobot-mcp-tracker.service; then
        echo "✅ Service started successfully"
    else
        echo "❌ Failed to start service"
        exit 1
    fi
fi

echo "🎉 All tests passed!"
EOF

# Make scripts executable
chmod +x *.sh

# Create development runner
cat > dev-run.sh << 'EOF'
#!/bin/bash
echo "🚀 Running AutoBot MCP Tracker in development mode..."
export NODE_ENV=development
export REDIS_HOST=${AUTOBOT_REDIS_HOST:-172.16.168.23}
export REDIS_PORT=${AUTOBOT_REDIS_PORT:-6379}
npm run dev
EOF

chmod +x dev-run.sh

echo "✅ Installation complete!"
echo ""
echo "📋 Next steps:"
echo "1. Start the service: ./start-mcp-tracker.sh"
echo "2. Check status: ./status-mcp-tracker.sh"
echo "3. Test functionality: ./test-mcp-tracker.sh"
echo "4. Restart Claude Desktop to load the new MCP server"
echo ""
echo "🔧 Management commands:"
echo "  - Start: ./start-mcp-tracker.sh"
echo "  - Stop: ./stop-mcp-tracker.sh"
echo "  - Status: ./status-mcp-tracker.sh"
echo "  - Logs: ./logs-mcp-tracker.sh"
echo "  - Test: ./test-mcp-tracker.sh"
echo "  - Dev mode: ./dev-run.sh"
echo ""
echo "📖 Claude Desktop config located at: $CONFIG_FILE"
echo "🔧 Service file located at: $SERVICE_FILE"
echo ""
echo "🚀 Ready to track your AutoBot conversations and correlate errors!"
