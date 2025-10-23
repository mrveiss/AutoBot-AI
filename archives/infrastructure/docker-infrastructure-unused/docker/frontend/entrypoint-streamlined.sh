#!/bin/bash
set -e

echo "🚀 AutoBot Frontend - Streamlined Startup"
echo "   Mode: $([ -f "/app/src/App.vue" ] && echo "Development (Source Mounted)" || echo "Production (Built Image)")"

# Quick dependency verification (no reinstalls unless actually missing)
check_critical_deps() {
    local missing_deps=()
    
    # Check only if directories exist - no functionality testing to avoid loops
    [ ! -d "node_modules/@heroicons/vue" ] && missing_deps+=("@heroicons/vue")
    [ ! -d "node_modules/@xterm/xterm" ] && missing_deps+=("@xterm/xterm")
    [ ! -d "node_modules/@xterm/addon-fit" ] && missing_deps+=("@xterm/addon-fit")
    [ ! -d "node_modules/@xterm/addon-web-links" ] && missing_deps+=("@xterm/addon-web-links")
    
    if [ ${#missing_deps[@]} -gt 0 ]; then
        echo "⚠️ Missing dependencies: ${missing_deps[*]}"
        echo "🔧 Installing missing dependencies only..."
        npm install "${missing_deps[@]}" --no-optional --prefer-offline
    else
        echo "✅ All critical dependencies present"
    fi
}

# Handle development mode package.json changes
handle_dev_changes() {
    if [ -f "/app/src/App.vue" ] && [ -f "package.json" ]; then
        echo "📁 Development mode detected"
        
        # Only reinstall if node_modules is completely missing
        if [ ! -d "node_modules" ]; then
            echo "🔧 node_modules missing, installing from package.json..."
            npm install --no-optional
            return
        fi
        
        # Check if package.json changed since last install
        local pkg_hash=""
        local stored_hash=""
        
        if command -v sha256sum >/dev/null 2>&1; then
            pkg_hash=$(sha256sum package.json 2>/dev/null | cut -d' ' -f1)
        else
            # Fallback for systems without sha256sum
            pkg_hash=$(stat -c %Y package.json 2>/dev/null || echo "unknown")
        fi
        
        if [ -f "node_modules/.package-hash" ]; then
            stored_hash=$(cat node_modules/.package-hash 2>/dev/null || echo "")
        fi
        
        if [ "$pkg_hash" != "$stored_hash" ] && [ "$pkg_hash" != "unknown" ]; then
            echo "📦 package.json changed, updating dependencies..."
            npm install --no-optional
            echo "$pkg_hash" > node_modules/.package-hash
        fi
    fi
}

# Main execution
echo "🔍 Starting dependency check..."

cd /app

# Handle development mode changes first
handle_dev_changes

# Quick critical dependency check (no functionality testing)
check_critical_deps

# Final status report
echo "📋 Dependency Status:"
echo "   @heroicons/vue: $([ -d 'node_modules/@heroicons/vue' ] && echo '✅ Present' || echo '❌ Missing')"
echo "   @xterm/xterm: $([ -d 'node_modules/@xterm/xterm' ] && echo '✅ Present' || echo '❌ Missing')"
echo "   @xterm/addon-fit: $([ -d 'node_modules/@xterm/addon-fit' ] && echo '✅ Present' || echo '❌ Missing')"

echo ""
echo "🚀 Starting Vite dev server..."
exec "$@"