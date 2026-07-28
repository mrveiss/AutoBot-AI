#!/bin/bash
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot Master Cache Management Script
# Comprehensive cache clearing across all system layers

set -e

echo "🧹 AutoBot Master Cache Clearing Started..."
echo "============================================"
echo "This script will clear ALL caches across the entire system"
echo "to prevent API configuration issues and ensure fresh state."
echo ""

# Check for options
FRONTEND_CACHE=true
BACKEND_CACHE=true
SYSTEM_CACHE=false
DOCKER_CACHE=false
REDIS_CACHE=false
FORCE_MODE=false

# Parse command line options
while [[ $# -gt 0 ]]; do
    case $1 in
        --frontend-only)
            FRONTEND_CACHE=true
            BACKEND_CACHE=false
            SYSTEM_CACHE=false
            shift
            ;;
        --backend-only)
            FRONTEND_CACHE=false
            BACKEND_CACHE=true
            SYSTEM_CACHE=false
            shift
            ;;
        --system)
            SYSTEM_CACHE=true
            shift
            ;;
        --docker)
            DOCKER_CACHE=true
            shift
            ;;
        --redis)
            REDIS_CACHE=true
            shift
            ;;
        --all)
            FRONTEND_CACHE=true
            BACKEND_CACHE=true
            SYSTEM_CACHE=true
            DOCKER_CACHE=true
            REDIS_CACHE=true
            shift
            ;;
        --force)
            FORCE_MODE=true
            shift
            ;;
        --help|-h)
            echo "AutoBot Master Cache Management"
            echo ""
            echo "Usage: $0 [OPTIONS]"
            echo ""
            echo "OPTIONS:"
            echo "  --frontend-only    Clear only frontend caches"
            echo "  --backend-only     Clear only backend caches"
            echo "  --system          Include system-level caches"
            echo "  --docker          Include Docker caches"
            echo "  --redis           Include Redis cache databases"
            echo "  --all             Clear all cache types (comprehensive)"
            echo "  --force           Skip confirmation prompts"
            echo "  --help, -h        Show this help message"
            echo ""
            echo "Default: Frontend + Backend caches only"
            echo ""
            echo "Examples:"
            echo "  $0                # Clear frontend and backend caches"
            echo "  $0 --all          # Clear everything (requires sudo for system)"
            echo "  $0 --frontend-only# Clear only frontend caches"
            echo "  $0 --system       # Include system caches (requires sudo)"
            echo ""
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            echo "Use --help for usage information"
            exit 1
            ;;
    esac
done

# Function to run script with error handling
run_cache_script() {
    local script="$1"
    local description="$2"
    local options="$3"

    echo "📋 $description"
    echo "----------------------------------------"

    if [ -f "$script" ]; then
        if chmod +x "$script" && bash "$script" $options; then
            echo "✅ $description - COMPLETED"
        else
            echo "⚠️  $description - FAILED (continuing...)"
        fi
    else
        echo "❌ $description - SCRIPT NOT FOUND: $script"
    fi

    echo ""
}

# Summary of what will be cleared
echo "📋 Cache clearing summary:"
echo "----------------------------------------"
[ "$FRONTEND_CACHE" = true ] && echo "✓ Frontend caches (npm, Vite, browser)"
[ "$BACKEND_CACHE" = true ] && echo "✓ Backend caches (Python, FastAPI)"
[ "$SYSTEM_CACHE" = true ] && echo "✓ System caches (DNS, memory, packages)"
[ "$DOCKER_CACHE" = true ] && echo "✓ Docker caches (build, images)"
[ "$REDIS_CACHE" = true ] && echo "✓ Redis cache databases"
echo ""

# Warning for comprehensive operations
if [ "$SYSTEM_CACHE" = true ] || [ "$DOCKER_CACHE" = true ] || [ "$REDIS_CACHE" = true ]; then
    echo "⚠️  WARNING: System-level operations detected"
    echo "   This may require sudo privileges and could affect other applications"
    echo "   Some network settings may need to be reconfigured"
    echo ""
fi

# Confirmation (unless --force is used)
if [ "$FORCE_MODE" = false ]; then
    read -p "🤔 Do you want to continue with cache clearing? (y/N): " -n 1 -r
    echo ""
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "❌ Cache clearing cancelled by user"
        exit 0
    fi
    echo ""
fi

echo "🚀 Starting cache clearing operations..."
echo ""

# Frontend cache clearing
if [ "$FRONTEND_CACHE" = true ]; then
    run_cache_script "./autobot-slm-frontend/clear-cache.sh" "Frontend Cache Clearing" ""
fi

# Backend cache clearing
if [ "$BACKEND_CACHE" = true ]; then
    local backend_options=""
    [ "$REDIS_CACHE" = true ] && backend_options="$backend_options --redis"
    [ "$DOCKER_CACHE" = true ] && backend_options="$backend_options --docker"

    if [ "$SYSTEM_CACHE" = true ] || [ "$REDIS_CACHE" = true ] || [ "$DOCKER_CACHE" = true ]; then
        backend_options="$backend_options --full"
    fi

    run_cache_script "./clear-backend-cache.sh" "Backend Cache Clearing" "$backend_options"
fi

# System cache clearing
if [ "$SYSTEM_CACHE" = true ]; then
    local system_options="--system"
    run_cache_script "./clear-system-cache.sh" "System Cache Clearing" "$system_options"
fi

# Additional Docker operations
if [ "$DOCKER_CACHE" = true ] && [ "$BACKEND_CACHE" = false ]; then
    echo "📦 Additional Docker cache operations..."
    echo "----------------------------------------"

    if command -v docker >/dev/null 2>&1; then
        echo "🐳 Clearing Docker system cache..."
        docker system prune -f || echo "⚠️  Docker system prune failed"

        echo "🏗️  Clearing Docker build cache..."
        docker builder prune -f || echo "⚠️  Docker builder prune failed"

        echo "💾 Clearing unused Docker volumes..."
        docker volume prune -f || echo "⚠️  Docker volume prune failed"
    else
        echo "❌ Docker not available - skipping Docker cache operations"
    fi
    echo ""
fi

# Additional Redis operations
if [ "$REDIS_CACHE" = true ] && [ "$BACKEND_CACHE" = false ]; then
    echo "🗄️  Additional Redis cache operations..."
    echo "----------------------------------------"

    if command -v redis-cli >/dev/null 2>&1; then
        echo "Clearing Redis cache databases..."
        redis-cli -n 2 FLUSHDB || echo "⚠️  Redis DB 2 flush failed"
        redis-cli -n 4 FLUSHDB || echo "⚠️  Redis DB 4 flush failed"
        redis-cli -n 5 FLUSHDB || echo "⚠️  Redis DB 5 flush failed"
        echo "✅ Redis cache databases cleared"
    else
        echo "❌ Redis CLI not available - skipping Redis cache operations"
    fi
    echo ""
fi

# Browser cache recommendations
echo "🌍 Browser Cache Recommendations:"
echo "----------------------------------------"
echo "For complete cache invalidation, also perform these manual steps:"
echo ""
echo "Chrome/Chromium:"
echo "  • Press Ctrl+Shift+R (hard refresh)"
echo "  • Open DevTools (F12) → Application → Storage → Clear site data"
echo "  • chrome://settings/clearBrowserData → Advanced → All time"
echo ""
echo "Firefox:"
echo "  • Press Ctrl+Shift+R (hard refresh)"
echo "  • Press Ctrl+Shift+Delete → Everything → Clear Now"
echo "  • about:preferences#privacy → Clear Data"
echo ""
echo "All browsers:"
echo "  • Disable browser cache in DevTools during development"
echo "  • Consider using private/incognito mode for testing"
echo ""

# Service restart recommendations
echo "🔄 Service Restart Recommendations:"
echo "----------------------------------------"
echo "For maximum effectiveness, consider restarting these services:"
echo ""
echo "Frontend:"
echo "  • Stop and restart Vite dev server (if running)"
echo "  • Rebuild frontend container: docker-compose build autobot-frontend"
echo ""
echo "Backend:"
echo "  • Restart FastAPI/Uvicorn backend service"
echo "  • Rebuild backend container: docker-compose build autobot-backend"
echo ""
echo "System:"
[ "$SYSTEM_CACHE" = true ] && echo "  • DNS: sudo systemctl restart systemd-resolved"
[ "$DOCKER_CACHE" = true ] && echo "  • Docker: sudo systemctl restart docker"
[ "$REDIS_CACHE" = true ] && echo "  • Redis: docker-compose restart autobot-redis"
echo ""

# Final summary
echo "============================================"
echo "✅ AutoBot Master Cache Clearing COMPLETED!"
echo ""

# Show cache clearing statistics
CLEARED_ITEMS=()
[ "$FRONTEND_CACHE" = true ] && CLEARED_ITEMS+=("Frontend caches")
[ "$BACKEND_CACHE" = true ] && CLEARED_ITEMS+=("Backend caches")
[ "$SYSTEM_CACHE" = true ] && CLEARED_ITEMS+=("System caches")
[ "$DOCKER_CACHE" = true ] && CLEARED_ITEMS+=("Docker caches")
[ "$REDIS_CACHE" = true ] && CLEARED_ITEMS+=("Redis caches")

echo "📊 Cleared cache types:"
for item in "${CLEARED_ITEMS[@]}"; do
    echo "   ✓ $item"
done
echo ""

echo "🎯 Expected benefits:"
echo "   • Fresh API configuration loading"
echo "   • Resolved proxy and routing issues"
echo "   • Eliminated stale configuration caches"
echo "   • Faster development rebuild times"
echo "   • Consistent cross-browser behavior"
echo ""

echo "🚀 Next steps:"
echo "   1. Restart development services (frontend/backend)"
echo "   2. Perform hard browser refresh (Ctrl+Shift+R)"
echo "   3. Test API connectivity and configuration loading"
echo "   4. Monitor for any remaining cache-related issues"
echo ""

echo "💡 Prevention tips:"
echo "   • Use 'Clear Cache' button in AutoBot UI for quick clearing"
echo "   • Run 'npm run dev:clean' for clean frontend restart"
echo "   • Set VITE_DISABLE_CACHE=true to disable caching during development"
echo "   • Use browser DevTools 'Disable cache' during development"
echo ""

echo "🔧 Troubleshooting:"
echo "   • If issues persist, try: $0 --all --force"
echo "   • Check browser DevTools Console for cache errors"
echo "   • Verify API endpoints are responding correctly"
echo "   • Consider running individual cache scripts for targeted clearing"
echo ""

echo "============================================"
echo "Cache clearing operation completed successfully! 🎉"
echo ""
