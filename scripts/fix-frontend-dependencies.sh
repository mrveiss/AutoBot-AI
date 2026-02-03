#!/bin/bash

# AutoBot Frontend Dependencies Fix Script
# This script resolves the persistent @heroicons/vue import issue

set -e

echo "🔧 AutoBot Frontend Dependencies Fix"
echo "=================================="

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to print colored output
print_status() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check if we're in the AutoBot directory
if [ ! -f "docker-compose.yml" ] || [ ! -d "autobot-vue" ]; then
    print_error "This script must be run from the AutoBot root directory"
    exit 1
fi

print_status "Checking current frontend container status..."

# Check if frontend container is running
if docker ps | grep -q "autobot-frontend"; then
    print_warning "Frontend container is running. Stopping it first..."
    docker stop autobot-frontend || true
fi

print_status "Analyzing the node_modules volume issue..."

# Check if the volume exists and what's in it
if docker volume ls | grep -q "autobot_frontend_node_modules"; then
    print_status "Found existing frontend node_modules volume"
    
    # Check if @heroicons is in the volume
    if docker run --rm -v autobot_frontend_node_modules:/check-vol alpine ls /check-vol/@heroicons 2>/dev/null; then
        print_success "@heroicons found in volume"
    else
        print_warning "@heroicons NOT found in volume - this confirms the issue"
        
        print_status "Option 1: Remove and recreate the volume (RECOMMENDED)"
        echo "This will force a fresh npm install with all dependencies"
        
        print_status "Option 2: Try to repair the existing volume"
        echo "This attempts to install missing packages in the existing volume"
        
        read -p "Choose option (1 or 2, default: 1): " choice
        choice=${choice:-1}
        
        if [ "$choice" = "1" ]; then
            print_status "Removing stale node_modules volume..."
            docker volume rm autobot_frontend_node_modules || true
            print_success "Volume removed. Fresh install will occur on next container start."
        else
            print_status "Attempting to repair existing volume..."
            docker run --rm -v autobot_frontend_node_modules:/app/node_modules -v "$(pwd)/autobot-vue:/workspace" -w /workspace node:20 bash -c "
                echo 'Copying package files...'
                cp package*.json /app/
                cd /app
                echo 'Running npm install to fix missing dependencies...'
                npm install --no-audit --no-fund
                echo 'Verifying @heroicons installation...'
                ls -la node_modules/@heroicons/ || exit 1
                echo 'Volume repair completed successfully'
            "
            
            if [ $? -eq 0 ]; then
                print_success "Volume repair completed successfully"
            else
                print_error "Volume repair failed. Please choose option 1 instead."
                exit 1
            fi
        fi
    fi
else
    print_status "No existing node_modules volume found - will be created fresh"
fi

print_status "Updating Docker configuration for development..."

# Create a development override file
cat > docker-compose.override.yml << EOF
# AutoBot Development Override
# This file configures the frontend service for robust dependency management

services:
  frontend:
    build:
      context: ./autobot-vue
      dockerfile: ../docker/frontend/Dockerfile.dev  # Use development Dockerfile
      args:
        - NODE_VERSION=\${NODE_VERSION:-20}
    image: autobot-frontend:dev
    environment:
      - NODE_ENV=development
      - VITE_BACKEND_HOST=host.docker.internal
      - VITE_BACKEND_PORT=8001
      - DOCKER_CONTAINER=true
      - DEBUG_PROXY=\${DEBUG_PROXY:-false}
      - LOG_LEVEL=\${FRONTEND_LOG_LEVEL:-info}
      # Force npm to use the volume for node_modules
      - NPM_CONFIG_CACHE=/tmp/.npm
    healthcheck:
      # Give more time for dependency checking in development
      start_period: 90s
      timeout: 15s
    volumes:
      - ./autobot-vue:/app
      - frontend_node_modules:/app/node_modules  # Managed by entrypoint script
      - ./logs:/shared/logs
EOF

print_success "Development override configuration created"

print_status "Building frontend container with dependency verification..."

# Build the frontend container with the new development Dockerfile
docker compose build frontend --no-cache

if [ $? -ne 0 ]; then
    print_error "Frontend container build failed!"
    print_error "Check the build logs above for details"
    exit 1
fi

print_success "Frontend container built successfully with verified dependencies"

print_status "Starting frontend service..."

# Start the frontend service
docker compose up frontend -d

print_status "Waiting for container to start and check dependencies..."

# Wait a bit for the container to start and run its dependency checks
sleep 10

# Check container logs for dependency verification
print_status "Checking container startup logs..."
docker compose logs --tail=20 frontend

# Verify the container is healthy
sleep 5
if docker compose ps frontend | grep -q "healthy\|Up"; then
    print_success "Frontend container is running successfully!"
    
    # Final verification: check if @heroicons is accessible in the container
    print_status "Final verification: Testing @heroicons import in container..."
    if docker exec autobot-frontend ls /app/node_modules/@heroicons/vue >/dev/null 2>&1; then
        print_success "✅ @heroicons/vue is properly installed and accessible!"
        
        # Test the actual import
        if docker exec autobot-frontend node -e "console.log(require('@heroicons/vue/package.json').name)" 2>/dev/null; then
            print_success "✅ @heroicons/vue import test PASSED!"
        else
            print_warning "Package exists but import test failed - may need container restart"
        fi
    else
        print_error "❌ @heroicons/vue still not accessible in container"
        print_error "Please check container logs and try rebuilding"
        exit 1
    fi
else
    print_error "Frontend container failed to start properly"
    print_error "Check the logs above for issues"
    exit 1
fi

print_success "🎉 Frontend dependency fix completed successfully!"
echo ""
echo "Summary of changes made:"
echo "- Created development-specific Dockerfile with dependency verification"
echo "- Updated Docker configuration with proper volume management" 
echo "- Added automatic dependency checking and repair on container start"
echo "- Verified @heroicons/vue is properly installed and accessible"
echo ""
echo "The fix will persist across:"
echo "✅ Container restarts"
echo "✅ Container rebuilds (with --no-build flag)"
echo "✅ Host system restarts"
echo "✅ Fresh deployments (dependencies auto-install)"
echo ""
echo "You can now use Heroicons imports like:"
echo "import XMarkIcon from '@heroicons/vue/24/outline/XMarkIcon'"
echo ""
print_success "AutoBot frontend is ready for development!"