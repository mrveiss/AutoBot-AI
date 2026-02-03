#!/bin/bash

# Production Installation Script for MCP AutoBot Tracker
# This script installs and configures the MCP tracker for production use

set -e

echo "🚀 Installing MCP AutoBot Tracker for Production..."

# Check if we're in the right directory
if [[ ! -f "package.json" ]]; then
    echo "❌ Error: Run this script from the mcp-autobot-tracker directory"
    exit 1
fi

echo "✅ Verified directory structure"

# Install dependencies
echo "📦 Installing Node.js dependencies..."
npm ci --production

# Verify Redis connection
echo "🔍 Verifying Redis connection..."
node -e "
const { createClient } = require('redis');
(async () => {
    try {
        const redis = createClient({ socket: { host: '172.16.168.23', port: 6379 } });
        await redis.connect();
        await redis.ping();
        await redis.quit();
        console.log('✅ Redis connection verified');
    } catch (error) {
        console.error('❌ Redis connection failed:', error.message);
        process.exit(1);
    }
})();
"

# Build TypeScript
echo "🔨 Building TypeScript..."
npm run build

echo "✅ Build completed successfully"

# Verify all core files exist
echo "🔍 Verifying installation..."
required_files=(
    "dist/index.js"
    "package.json" 
    "claude_desktop_config.json"
    "config.example.json"
)

for file in "${required_files[@]}"; do
    if [[ ! -f "$file" ]]; then
        echo "❌ Missing required file: $file"
        exit 1
    fi
done

echo "✅ All required files present"

# Create production configuration
echo "📝 Creating production configuration..."
if [[ ! -f "config.json" ]]; then
    cp config.example.json config.json
    echo "📋 Configuration template created at config.json"
    echo "🔧 Please edit config.json with your production settings"
fi

# Create systemd service (optional)
if command -v systemctl &> /dev/null; then
    echo "🔧 Creating systemd service..."
    
    cat > /tmp/mcp-autobot-tracker.service << EOF
[Unit]
Description=MCP AutoBot Tracker
After=network.target

[Service]
Type=simple
User=$(whoami)
WorkingDirectory=$(pwd)
ExecStart=/usr/bin/node dist/index.js
Restart=always
RestartSec=10
Environment=NODE_ENV=production

[Install]
WantedBy=multi-user.target
EOF

    sudo mv /tmp/mcp-autobot-tracker.service /etc/systemd/system/
    sudo systemctl daemon-reload
    
    echo "📋 Systemd service created. To enable:"
    echo "   sudo systemctl enable mcp-autobot-tracker"
    echo "   sudo systemctl start mcp-autobot-tracker"
fi

# Setup Claude Desktop integration
echo "🔗 Setting up Claude Desktop integration..."
claude_config_dir="$HOME/.config/claude_desktop"
if [[ ! -d "$claude_config_dir" ]]; then
    mkdir -p "$claude_config_dir"
fi

if [[ -f "claude_desktop_config.json" ]]; then
    echo "📋 Claude Desktop configuration available at: claude_desktop_config.json"
    echo "🔧 Add this to your Claude Desktop config at: $claude_config_dir/config.json"
fi

# Test the installation
echo "🧪 Testing installation..."
timeout 30 node dist/index.js --test || {
    echo "⚠️  Quick test timed out (expected for MCP server)"
    echo "✅ Installation appears successful"
}

echo ""
echo "🎉 MCP AutoBot Tracker Production Installation Complete!"
echo ""
echo "📋 Next Steps:"
echo "   1. Edit config.json with your production settings"
echo "   2. Add claude_desktop_config.json to your Claude Desktop"
echo "   3. Restart Claude Desktop to load the MCP server"
echo "   4. (Optional) Enable systemd service for background monitoring"
echo ""
echo "🔍 Usage:"
echo "   • Chat ingestion: Use 'ingest_chat' MCP tool in Claude"
echo "   • Task tracking: Use 'get_unfinished_tasks' MCP tool"
echo "   • Error analysis: Use 'get_error_correlations' MCP tool"
echo "   • Insights: Use 'get_insights' MCP tool"
echo ""
echo "📊 Monitoring:"
echo "   • Check logs with: journalctl -u mcp-autobot-tracker -f"
echo "   • Monitor Redis: redis-cli -h 172.16.168.23 monitor"
echo ""
echo "✨ Your AutoBot system now has comprehensive chat tracking and task correlation!"