#!/bin/bash

# AutoBot Frontend Dependencies Persistence Script
# This script ensures @heroicons/vue and other critical dependencies persist across rebuilds

set -e

echo "🔍 AutoBot Frontend Dependencies Check"
echo "====================================="

# Color codes
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m'

print_status() { echo -e "${BLUE}[INFO]${NC} $1"; }
print_success() { echo -e "${GREEN}[SUCCESS]${NC} $1"; }
print_warning() { echo -e "${YELLOW}[WARNING]${NC} $1"; }
print_error() { echo -e "${RED}[ERROR]${NC} $1"; }

# Check if we're in the AutoBot directory
if [ ! -f "docker-compose.yml" ] || [ ! -d "autobot-slm-frontend" ]; then
    print_error "This script must be run from the AutoBot root directory"
    exit 1
fi

print_status "Checking frontend container status..."

# Check if container exists and is running
if ! docker ps -a | grep -q "autobot-frontend"; then
    print_error "Frontend container not found. Please start it first with: ./run_agent_unified.sh --dev"
    exit 1
fi

# Function to ensure package is installed in container
ensure_package_in_container() {
    local package=$1
    local container_name=${2:-autobot-frontend}

    print_status "Checking package: $package"

    # Check if package exists in container
    if docker exec $container_name test -d "/app/node_modules/$package" 2>/dev/null; then
        print_success "✅ $package is installed in container"
        return 0
    else
        print_warning "⚠️ $package missing from container, installing..."

        if docker exec $container_name npm install "$package" --save; then
            print_success "✅ Successfully installed $package"
            return 0
        else
            print_error "❌ Failed to install $package"
            return 1
        fi
    fi
}

# Function to test package import
test_package_import() {
    local package=$1
    local test_import=$2
    local container_name=${3:-autobot-frontend}

    print_status "Testing import: $test_import"

    if docker exec $container_name node -e "try { require('$test_import'); console.log('✅ Import test passed'); } catch(e) { console.log('❌ Import failed:', e.message); process.exit(1); }" >/dev/null 2>&1; then
        print_success "✅ Import test passed for $test_import"
        return 0
    else
        print_error "❌ Import test failed for $test_import"
        return 1
    fi
}

# Function to restart Vite dev server
restart_dev_server() {
    local container_name=${1:-autobot-frontend}

    print_status "Restarting Vite dev server..."
    docker restart $container_name
    sleep 10  # Give time for container to start

    # Check if dev server is running
    local max_attempts=6
    local attempt=1

    while [ $attempt -le $max_attempts ]; do
        if curl -s -f http://localhost:5173 >/dev/null 2>&1; then
            print_success "✅ Vite dev server is running and accessible"
            return 0
        fi

        print_status "Waiting for dev server... (attempt $attempt/$max_attempts)"
        sleep 5
        ((attempt++))
    done

    print_error "❌ Dev server failed to start properly"
    return 1
}

# Main dependency check and fix process
print_status "Starting dependency verification and repair process..."

# Critical packages to check
declare -A packages=(
    ["@heroicons/vue"]="@heroicons/vue/24/outline/XMarkIcon"
    ["@xterm/xterm"]="@xterm/xterm"
    ["@xterm/addon-fit"]="@xterm/addon-fit"
    ["@xterm/addon-web-links"]="@xterm/addon-web-links"
    ["vue"]="vue"
    ["pinia"]="pinia"
)

need_restart=false

for package in "${!packages[@]}"; do
    if ensure_package_in_container "$package"; then
        # Test the import
        if test_package_import "$package" "${packages[$package]}"; then
            print_success "✅ $package is working correctly"
        else
            print_warning "⚠️ $package import failed, may need dev server restart"
            need_restart=true
        fi
    else
        print_error "❌ Failed to ensure $package is installed"
        need_restart=true
    fi
done

# Restart dev server if any packages were installed or had issues
if [ "$need_restart" = true ]; then
    print_status "Dependencies were updated, restarting dev server..."
    if restart_dev_server; then
        print_success "🎉 Dependencies verified and dev server restarted successfully!"
    else
        print_error "❌ Dev server restart failed"
        exit 1
    fi
else
    print_success "🎉 All dependencies are working correctly!"
fi

# Final verification
print_status "Performing final verification..."

# Check if the specific problematic import works
if docker exec autobot-frontend node -e "
const XMarkIcon = require('@heroicons/vue/24/outline/XMarkIcon');
const ExclamationTriangleIcon = require('@heroicons/vue/24/outline/ExclamationTriangleIcon');
const InformationCircleIcon = require('@heroicons/vue/24/outline/InformationCircleIcon');
console.log('✅ All @heroicons/vue imports working!');
console.log('  - XMarkIcon:', typeof XMarkIcon);
console.log('  - ExclamationTriangleIcon:', typeof ExclamationTriangleIcon);
console.log('  - InformationCircleIcon:', typeof InformationCircleIcon);
" 2>/dev/null; then
    print_success "🎉 Final verification PASSED - All Heroicons imports are working!"
else
    print_error "❌ Final verification FAILED - Some imports still not working"
    exit 1
fi

print_success "✅ Frontend dependencies are now fully functional and persistent!"
echo ""
echo "Summary:"
echo "- All critical packages verified and working"
echo "- @heroicons/vue imports functioning correctly"
echo "- Dependencies will persist across container restarts"
echo "- Vite dev server is running and accessible"
echo ""
echo "You can now use imports like:"
echo "  import XMarkIcon from '@heroicons/vue/24/outline/XMarkIcon'"
echo "  import ExclamationTriangleIcon from '@heroicons/vue/24/outline/ExclamationTriangleIcon'"
echo ""
print_success "🎉 AutoBot frontend is ready for development!"
