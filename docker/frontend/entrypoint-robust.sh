#!/bin/bash
set -e

echo "🔧 AutoBot Frontend - Robust Startup ($(date))"

# Configuration
MAX_INSTALL_ATTEMPTS=2
INSTALL_TIMEOUT=300  # 5 minutes max for npm install
NPM_CACHE_DIR="/tmp/.npm"

# Function to run npm install with timeout protection
run_npm_install_with_timeout() {
    local attempt=$1
    echo "📦 Running npm install (attempt $attempt/$MAX_INSTALL_ATTEMPTS) with ${INSTALL_TIMEOUT}s timeout..."
    
    # Set npm cache to prevent permission issues
    export NPM_CONFIG_CACHE="$NPM_CACHE_DIR"
    mkdir -p "$NPM_CONFIG_CACHE"
    
    # Run npm install with timeout
    if timeout ${INSTALL_TIMEOUT} npm install --no-audit --no-fund --prefer-offline; then
        echo "✅ npm install completed successfully"
        return 0
    else
        echo "❌ npm install failed or timed out"
        return 1
    fi
}

# Function to safely check if package is available
check_package_safely() {
    local package_name=$1
    echo "Checking $package_name..."
    
    # Check if package directory exists and is readable
    if [ -d "node_modules/$package_name" ] && [ -r "node_modules/$package_name/package.json" ]; then
        echo "✅ $package_name found in volume"
        return 0
    else
        echo "⚠️ $package_name missing or not accessible"
        return 1
    fi
}

# Function to test imports without hanging
test_imports_safely() {
    echo "🧪 Testing dependency imports with timeout..."
    
    # Test with 10 second timeout
    if timeout 10 node -e "
        try {
            require('@heroicons/vue/24/outline/XMarkIcon');
            console.log('✅ @heroicons/vue import test passed');
        } catch (e) {
            console.log('❌ @heroicons/vue import test failed:', e.message);
            process.exit(1);
        }
    " 2>/dev/null; then
        return 0
    else
        echo "❌ Import test failed or timed out"
        return 1
    fi
}

# Main dependency management logic
manage_dependencies() {
    echo "🔍 Analyzing node_modules state..."
    
    # Check if node_modules exists and has content
    if [ ! -d "node_modules" ] || [ -z "$(ls -A node_modules 2>/dev/null)" ]; then
        echo "📦 Empty or missing node_modules detected"
        
        # Try to install dependencies with retry logic
        for attempt in $(seq 1 $MAX_INSTALL_ATTEMPTS); do
            if run_npm_install_with_timeout $attempt; then
                break
            elif [ $attempt -eq $MAX_INSTALL_ATTEMPTS ]; then
                echo "❌ CRITICAL: Failed to install dependencies after $MAX_INSTALL_ATTEMPTS attempts"
                echo "🔧 Starting with existing state - some features may not work"
                return 1
            fi
            echo "🔄 Retrying in 5 seconds..."
            sleep 5
        done
    fi
    
    # Check critical packages
    local missing_packages=false
    
    for package in "@heroicons/vue" "@xterm/xterm" "@xterm/addon-fit" "@xterm/addon-web-links" "vue" "pinia"; do
        if ! check_package_safely "$package"; then
            missing_packages=true
            break
        fi
    done
    
    # If packages are missing, try ONE install attempt
    if [ "$missing_packages" = "true" ]; then
        echo "⚠️ Some packages are missing, attempting single install..."
        
        if run_npm_install_with_timeout 1; then
            echo "✅ Dependency installation completed"
        else
            echo "❌ Dependency installation failed - continuing with degraded functionality"
        fi
    fi
    
    # Test imports (but don't fail if it doesn't work)
    if ! test_imports_safely; then
        echo "⚠️ Import tests failed - but continuing startup"
    fi
}

# Prevent infinite loops by checking if we're already in an install process
if [ -f "/tmp/.npm-install-running" ]; then
    echo "⚠️ npm install appears to be already running - skipping dependency checks"
else
    touch "/tmp/.npm-install-running"
    manage_dependencies
    rm -f "/tmp/.npm-install-running"
fi

echo "🚀 Dependencies checked, starting development server..."
echo "Starting in mode: ${NODE_ENV:-development}"

# Start the application
exec "$@"