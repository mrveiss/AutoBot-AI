#!/bin/bash
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
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
    # Redis is deliberately absent from these lists (#16071). This tool talks
    # to AutoBot's Redis through autobot_shared.redis_client -- it does not want
    # a second local instance, and the apt/yum/dnf packages are plain Redis with
    # none of the modules the platform uses.
    if command -v apt-get &> /dev/null; then
        sudo apt-get update
        sudo apt-get install -y python3-pip python3-venv
    elif command -v yum &> /dev/null; then
        sudo yum install -y python3-pip python3-venv
    elif command -v dnf &> /dev/null; then
        sudo dnf install -y python3-pip python3-venv
    fi
elif [[ "$OSTYPE" == "darwin"* ]]; then
    # macOS
    if command -v brew &> /dev/null; then
        brew install python3
    else
        echo "❌ Homebrew not found. Please install Python 3 manually."
        exit 1
    fi
fi

# Redis is provisioned by roles/redis, not by this script (#16071). It owns the
# Redis Stack repository, the suite pin (#7178) and the package, and a second
# copy of that logic here would drift out of step invisibly. Report whether the
# service this tool needs is reachable; do not try to create it.
echo "🔄 Checking Redis Stack..."
if command -v systemctl &> /dev/null && systemctl is-active --quiet redis-stack-server; then
    echo "✅ redis-stack-server is running"
else
    echo "⚠️  redis-stack-server is not running here."
    echo "    This tool connects through autobot_shared.redis_client, so it needs"
    echo "    AutoBot's Redis Stack -- provision it with roles/redis, or point the"
    echo "    client at an existing instance. Plain Redis from apt/brew will not do:"
    echo "    it has no RediSearch, RedisJSON or RedisTimeSeries."
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
    # #15408: floor no longer restated here -- constraints/shared.txt is the single
    # source of truth (openvino floor, and numpy so no dependency can drag it below
    # its pinned floor). A bare package name plus -c lets pip resolve both from it.
    pip install -c ../../constraints/shared.txt openvino onnxruntime
fi

# Create necessary directories
echo "📁 Creating directories..."
mkdir -p logs reports patches

# Set up configuration
echo "⚙️ Setting up configuration..."

# Redis: no URL, host or DB number here (#19232). The suite connects through
# autobot_shared.redis_client (database "main", the get_async_redis_client()
# default its call sites use), which resolves host, port, credentials and the
# number -- redis-databases.yaml plus AUTOBOT_REDIS_DB_MAIN -- in one place.
# The REDIS_URL this file used to write had no reader.
_INSTALL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
_REPO_ROOT="$(cd "${_INSTALL_DIR}/../.." && pwd)"

cat > .env << EOF
# AutoBot Code Analysis Suite Configuration
# Values can be overridden via AUTOBOT_* environment variables
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

# Test Redis connection through the canonical client -- the endpoint and the "main"
# database (redis-databases.yaml, AUTOBOT_REDIS_DB_MAIN) the suite itself will use.
if ! PYTHONPATH="${_REPO_ROOT}" python3 -c "import autobot_shared.redis_client"; then
    echo "⚠️  Could not import autobot_shared.redis_client (see the error above)."
elif PYTHONPATH="${_REPO_ROOT}" python3 -c "
from autobot_shared.redis_client import require_redis_client
require_redis_client(database='main').ping()
print('✅ Redis connection successful')
" 2>/dev/null; then
    :
else
    echo "⚠️  Redis connection failed. Please check Redis server."
fi

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
