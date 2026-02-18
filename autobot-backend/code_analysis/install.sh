#!/bin/bash
# AutoBot Code Analysis Suite Installation Script

set -e

echo "🚀 Installing AutoBot Code Analysis Suite..."

# Check Python version
python_version=$(python3 -c 'import sys; print(".".join(map(str, sys.version_info[:2])))')
required_version="3.8"

if [ "$(printf '%s\n' "$required_version" "$python_version" | sort -V | head -n1)" != "$required_version" ]; then
    echo "❌ Python $required_version or higher is required. Found: $python_version"
    exit 1
fi

echo "✅ Python version: $python_version"

# Install system dependencies
echo "📦 Installing system dependencies..."

# Detect OS
if [[ "$OSTYPE" == "linux-gnu"* ]]; then
    # Linux
    if command -v apt-get &> /dev/null; then
        sudo apt-get update
        sudo apt-get install -y redis-server python3-pip python3-venv
    elif command -v yum &> /dev/null; then
        sudo yum install -y redis python3-pip python3-venv
    elif command -v dnf &> /dev/null; then
        sudo dnf install -y redis python3-pip python3-venv
    fi
elif [[ "$OSTYPE" == "darwin"* ]]; then
    # macOS
    if command -v brew &> /dev/null; then
        brew install redis python3
    else
        echo "❌ Homebrew not found. Please install Redis manually."
        exit 1
    fi
fi

# Start Redis
echo "🔄 Starting Redis server..."
if command -v systemctl &> /dev/null; then
    sudo systemctl start redis
    sudo systemctl enable redis
elif command -v brew &> /dev/null; then
    brew services start redis
else
    echo "⚠️  Please start Redis manually: redis-server"
fi

# Create virtual environment
echo "🐍 Creating Python virtual environment..."
python3 -m venv venv
source venv/bin/activate

# Install Python dependencies
echo "📚 Installing Python dependencies..."
pip install --upgrade pip
pip install -r requirements.txt

# Optional: Install development dependencies
if [ "$1" = "--dev" ]; then
    echo "🛠️ Installing development dependencies..."
    pip install pytest pytest-asyncio black flake8 isort mypy
fi

# Optional: Install NPU support
if [ "$1" = "--npu" ]; then
    echo "🧠 Installing NPU support..."
    pip install openvino onnxruntime
fi

# Create necessary directories
echo "📁 Creating directories..."
mkdir -p logs reports patches

# Set up configuration
echo "⚙️ Setting up configuration..."

# Check for existing AutoBot configuration or use defaults
REDIS_HOST="${AUTOBOT_REDIS_HOST:-localhost}"
REDIS_PORT="${AUTOBOT_REDIS_PORT:-6379}"
REDIS_DB="${AUTOBOT_REDIS_DB:-0}"

cat > .env << EOF
# AutoBot Code Analysis Suite Configuration
# Values can be overridden via AUTOBOT_* environment variables
REDIS_URL=redis://${REDIS_HOST}:${REDIS_PORT}/${REDIS_DB}
LOG_LEVEL=${AUTOBOT_LOG_LEVEL:-INFO}
CACHE_TTL=${AUTOBOT_CACHE_TTL:-3600}

# Analysis Configuration
SECURITY_ENABLED=${AUTOBOT_SECURITY_ENABLED:-true}
PERFORMANCE_ENABLED=${AUTOBOT_PERFORMANCE_ENABLED:-true}
ML_ENABLED=${AUTOBOT_ML_ENABLED:-true}

# Performance Tuning
MAX_WORKERS=${AUTOBOT_MAX_WORKERS:-4}
TIMEOUT=${AUTOBOT_TIMEOUT:-300}
MAX_FILE_SIZE=${AUTOBOT_MAX_FILE_SIZE:-10485760}
EOF

# Make scripts executable
echo "🔧 Making scripts executable..."
chmod +x scripts/*.py

# Test installation
echo "🧪 Testing installation..."
python3 -c "
import redis
import numpy
import sklearn
print('✅ All dependencies installed successfully')
"

# Test Redis connection - use environment-configured values
python3 -c "
import redis
import os
redis_host = os.getenv('AUTOBOT_REDIS_HOST', 'localhost')
redis_port = int(os.getenv('AUTOBOT_REDIS_PORT', '6379'))
redis_db = int(os.getenv('AUTOBOT_REDIS_DB', '0'))
r = redis.Redis(host=redis_host, port=redis_port, db=redis_db)
r.ping()
print('✅ Redis connection successful')
" 2>/dev/null || echo "⚠️  Redis connection failed. Please check Redis server."

echo ""
echo "🎉 Installation complete!"
echo ""
echo "📋 Quick Start:"
echo "1. Activate virtual environment: source venv/bin/activate"
echo "2. Run comprehensive analysis: python scripts/analyze_code_quality.py"
echo "3. View results in generated reports"
echo ""
echo "📚 Documentation: See README.md and docs/ directory"
echo "🆘 Support: Check docs/TROUBLESHOOTING.md for common issues"
