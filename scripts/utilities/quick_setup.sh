#!/bin/bash

echo "🚀 AutoBot Quick Setup (Browser dependencies optional)"
echo "=============================================="

# Check if we're in the right directory
if [ ! -f "setup_agent.sh" ]; then
    echo "❌ Please run this from the AutoBot directory"
    exit 1
fi

# 1. Set up Python virtual environment
echo "🐍 Setting up Python virtual environment..."
if [ ! -d "venv" ]; then
    python3 -m venv venv
fi
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
echo "✅ Python environment ready"

# 2. Install Node.js dependencies
echo "📦 Installing Node.js dependencies..."
cd autobot-vue
npm install
cd ..
echo "✅ Node.js dependencies installed"

# 3. Start Docker daemon if not running
echo "🐳 Checking Docker..."
if ! docker info >/dev/null 2>&1; then
    echo "Starting Docker daemon..."
    sudo dockerd > /dev/null 2>&1 &
    sleep 5
fi

# 4. Set up Redis container
echo "🔴 Setting up Redis..."
if ! docker ps | grep -q "autobot-redis"; then
    if docker ps -a | grep -q "autobot-redis"; then
        docker start autobot-redis
    else
        docker run -d --name autobot-redis -p 6379:6379 redis:alpine
    fi
fi
echo "✅ Redis container ready"

# 5. Create necessary directories
echo "📁 Creating directories..."
mkdir -p data logs
echo "✅ Directories created"

# 6. Skip browser dependencies (GUI testing can be done manually)
echo "⚠️ Skipping browser dependencies to avoid package conflicts"
echo "   Basic functionality will work fine without them"

echo ""
echo "🎉 Quick setup complete!"
echo ""
echo "To start the application:"
echo "  ./run_agent.sh"
echo ""
echo "To run with frontend development server:"
echo "  ./run_agent.sh --dev"
echo ""