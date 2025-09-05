#!/bin/bash
# AutoBot Backend Cache Clearing Script
# Comprehensive backend cache clearing for API configuration fixes

set -e

echo "🧹 AutoBot Backend Cache Clearing Started..."
echo "============================================"

# Function to run command with error handling
run_command() {
    local cmd="$1"
    local description="$2"
    echo "📋 $description"
    if eval "$cmd"; then
        echo "✅ $description - SUCCESS"
    else
        echo "⚠️  $description - FAILED (continuing...)"
    fi
    echo ""
}

# Python cache clearing
echo "🐍 Clearing Python caches..."

# Clear __pycache__ directories
run_command "find . -type d -name '__pycache__' -exec rm -rf {} + 2>/dev/null || true" "Removing Python __pycache__ directories"

# Clear .pyc files
run_command "find . -name '*.pyc' -delete 2>/dev/null || true" "Removing Python .pyc files"

# Clear .pyo files
run_command "find . -name '*.pyo' -delete 2>/dev/null || true" "Removing Python .pyo files"

# Clear pytest cache
run_command "rm -rf .pytest_cache" "Removing pytest cache"

# Clear coverage cache
run_command "rm -rf .coverage htmlcov" "Removing coverage cache"

# Clear mypy cache
run_command "rm -rf .mypy_cache" "Removing mypy cache"

# Clear pip cache (if needed)
if [ "$1" = "--full" ]; then
    run_command "python3 -m pip cache purge" "Purging pip cache"
fi

echo "🚀 FastAPI and application cache clearing..."

# Clear FastAPI route registration cache
run_command "rm -rf backend/__pycache__" "Removing backend cache"
run_command "rm -rf src/__pycache__" "Removing src cache"

# Clear Python module import cache if Python is running
echo "📝 Checking for running Python processes..."
PYTHON_PIDS=$(pgrep -f "python.*autobot" || true)
if [ ! -z "$PYTHON_PIDS" ]; then
    echo "⚠️  Found running Python processes: $PYTHON_PIDS"
    echo "💡 Consider stopping backend before cache clear for full effect"
else
    echo "✅ No running Python processes found"
fi

# Clear Redis cache if requested
if [ "$1" = "--redis" ] || [ "$1" = "--full" ]; then
    echo "🗄️  Clearing Redis caches..."
    
    # Check if Redis is running
    if command -v redis-cli >/dev/null 2>&1; then
        # Clear specific Redis databases used for caching
        run_command "redis-cli -n 2 FLUSHDB" "Clearing Redis database 2 (cache)"
        run_command "redis-cli -n 4 FLUSHDB" "Clearing Redis database 4 (sessions)"
        run_command "redis-cli -n 5 FLUSHDB" "Clearing Redis database 5 (temporary)"
    else
        echo "⚠️  Redis CLI not available - skipping Redis cache clear"
    fi
fi

# Clear log files if requested
if [ "$1" = "--logs" ] || [ "$1" = "--full" ]; then
    echo "📄 Clearing log files..."
    run_command "find . -name '*.log' -type f -delete 2>/dev/null || true" "Removing log files"
    run_command "find . -name '*.log.*' -type f -delete 2>/dev/null || true" "Removing rotated log files"
fi

# Clear temporary files
echo "🗂️  Clearing temporary files..."
run_command "rm -rf /tmp/autobot_*" "Removing AutoBot temp files"
run_command "rm -rf /tmp/fastapi_*" "Removing FastAPI temp files"

# Clear uvicorn cache
run_command "rm -rf ~/.cache/uvicorn" "Removing uvicorn cache"

# Clear any virtual environment cache
if [ -d "venv" ]; then
    run_command "find venv -name '*.pyc' -delete 2>/dev/null || true" "Clearing venv cache files"
fi

if [ -d ".venv" ]; then
    run_command "find .venv -name '*.pyc' -delete 2>/dev/null || true" "Clearing .venv cache files"
fi

# Docker cache clearing if requested
if [ "$1" = "--docker" ] || [ "$1" = "--full" ]; then
    echo "🐳 Clearing Docker caches..."
    
    # Clear Docker build cache
    run_command "docker builder prune -f" "Clearing Docker build cache"
    
    # Clear unused Docker images
    run_command "docker image prune -f" "Removing unused Docker images"
    
    # Clear Docker container cache
    run_command "docker container prune -f" "Removing stopped containers"
fi

echo ""
echo "============================================"
echo "✅ AutoBot Backend Cache Clearing COMPLETED!"
echo ""
echo "📋 What was cleared:"
echo "   • Python bytecode and cache files"
echo "   • FastAPI and uvicorn caches"
echo "   • Application temporary files"

if [ "$1" = "--redis" ] || [ "$1" = "--full" ]; then
    echo "   • Redis cache databases"
fi

if [ "$1" = "--logs" ] || [ "$1" = "--full" ]; then
    echo "   • Application log files"
fi

if [ "$1" = "--docker" ] || [ "$1" = "--full" ]; then
    echo "   • Docker build and image caches"
fi

echo ""
echo "🚀 Next steps:"
echo "   • Restart backend service for full effect"
echo "   • Check API endpoints for configuration loading"
echo "   • Monitor logs for any cache-related issues"
echo ""
echo "💡 Usage:"
echo "   ./clear-backend-cache.sh          # Basic cache clear"
echo "   ./clear-backend-cache.sh --redis  # Include Redis cache"
echo "   ./clear-backend-cache.sh --logs   # Include log files"
echo "   ./clear-backend-cache.sh --docker # Include Docker cache"
echo "   ./clear-backend-cache.sh --full   # Clear everything"
echo ""