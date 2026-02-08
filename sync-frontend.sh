#!/bin/bash
# AutoBot Frontend Sync Script
# Builds Vue.js frontend and deploys to native VM

set -e  # Exit on any error

# Source SSOT configuration (#808)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=infrastructure/shared/scripts/lib/ssot-config.sh
source "${SCRIPT_DIR}/infrastructure/shared/scripts/lib/ssot-config.sh" 2>/dev/null || true

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}🔧 AutoBot Frontend Sync${NC}"
echo "=================================="

# Parse command line arguments
DEV_MODE=false
if [[ "$1" == "--help" ]] || [[ "$1" == "-h" ]]; then
    echo -e "${BLUE}AutoBot Frontend Sync Script${NC}"
    echo ""
    echo "Usage: $0 [OPTIONS]"
    echo ""
    echo "Options:"
    echo "  --dev         Development mode: Sync source files (fast, hot reload)"
    echo "  --restart     Production mode + restart frontend server"
    echo "  (no flags)    Production mode: Build and deploy"
    echo "  --help, -h    Show this help message"
    echo ""
    echo "Examples:"
    echo "  $0                # Production build and deploy"
    echo "  $0 --dev         # Development source sync (recommended for development)"
    echo "  $0 --restart     # Production build + server restart"
    exit 0
elif [[ "$1" == "--dev" ]]; then
    DEV_MODE=true
    echo -e "${YELLOW}🧪 Development mode: Syncing source files${NC}"
else
    echo -e "${BLUE}🏭 Production mode: Building and deploying${NC}"
fi

# Check if we're in the right directory
if [[ ! -f "autobot-vue/package.json" ]]; then
    echo -e "${RED}❌ Error: Must run from AutoBot root directory${NC}"
    echo "Current directory: $(pwd)"
    echo "Expected: /home/kali/Desktop/AutoBot"
    exit 1
fi

# Check if ansible inventory exists
if [[ ! -f "ansible/inventory/production.yml" ]]; then
    echo -e "${RED}❌ Error: Ansible inventory not found${NC}"
    echo "Expected: ansible/inventory/production.yml"
    exit 1
fi

# Show current git status for context
if git status &>/dev/null; then
    echo -e "${BLUE}Git status:${NC}"
    git status --porcelain | head -5
    echo ""
fi

if [[ "$DEV_MODE" == "true" ]]; then
    # Development mode: Sync source files
    echo -e "${YELLOW}📁 Syncing source files to frontend VM...${NC}"
    start_time=$(date +%s)

    if ./scripts/utilities/sync-to-vm.sh frontend autobot-vue/src/ /home/autobot/autobot-vue/src/; then
        end_time=$(date +%s)
        sync_time=$((end_time - start_time))
        echo -e "${GREEN}✅ Source sync completed in ${sync_time}s${NC}"
    else
        echo -e "${RED}❌ Source sync failed${NC}"
        exit 1
    fi

    # Check if dependencies need repopulation
    echo -e "${YELLOW}🔍 Checking dependencies status...${NC}"
    if ssh -i ~/.ssh/autobot_key autobot@"${AUTOBOT_FRONTEND_HOST:-172.16.168.21}" "test -f /home/autobot/autobot-vue/node_modules/.vite/deps/vue.js" 2>/dev/null; then
        echo -e "${GREEN}✅ Dependencies are current, skipping sync${NC}"
    else
        echo -e "${YELLOW}📦 Dependencies missing or outdated, syncing...${NC}"
        if ./scripts/utilities/sync-to-vm.sh frontend autobot-vue/node_modules/ /home/autobot/autobot-vue/node_modules/; then
            echo -e "${GREEN}✅ Dependencies sync completed${NC}"
        else
            echo -e "${RED}❌ Dependencies sync failed${NC}"
            exit 1
        fi
    fi

    # Skip production deployment in dev mode
    echo -e "${GREEN}🎉 Development sync completed!${NC}"
    echo "=================================="
    echo -e "${BLUE}Summary:${NC}"
    echo "  • Mode: 🧪 Development source sync"
    echo "  • Target: Frontend VM (${AUTOBOT_FRONTEND_HOST:-172.16.168.21})"
    echo "  • Status: ✅ Source files synced"
    echo ""
    echo -e "${BLUE}Next steps:${NC}"
    echo "  • Frontend dev server will auto-reload changes"
    echo "  • Open browser: http://${AUTOBOT_FRONTEND_HOST:-172.16.168.21}:${AUTOBOT_FRONTEND_PORT:-5173}"
    echo "  • Check console for any errors"
    exit 0
else
    # Production mode: Build and deploy
    echo -e "${YELLOW}📦 Building frontend...${NC}"
    cd autobot-vue

    # Build with timing
    start_time=$(date +%s)
    if npm run build; then
        end_time=$(date +%s)
        build_time=$((end_time - start_time))
        echo -e "${GREEN}✅ Build completed in ${build_time}s${NC}"
    else
        echo -e "${RED}❌ Build failed${NC}"
        exit 1
    fi

    # Extract new bundle name
    cd dist
    bundle_name=$(ls js/index-*.js 2>/dev/null | head -1 | xargs basename 2>/dev/null || echo "unknown")
    css_name=$(ls assets/index-*.css 2>/dev/null | head -1 | xargs basename 2>/dev/null || echo "unknown")
    echo -e "${BLUE}📄 New bundle: ${bundle_name}${NC}"

    # Go back to AutoBot root
    cd ../..
fi

# Step 2: Test backend connectivity
echo -e "${YELLOW}🔍 Testing backend connectivity...${NC}"
if ansible backend -i ansible/inventory/production.yml -m shell -a "curl -s -o /dev/null -w '%{http_code}' http://localhost:8001/api/system/health" | grep -q "200"; then
    echo -e "${GREEN}✅ Backend is healthy${NC}"
else
    echo -e "${YELLOW}⚠️  Warning: Backend may not be responding${NC}"
fi

# Step 3: Deploy to frontend VM
echo -e "${YELLOW}🚀 Deploying to frontend VM...${NC}"

# Clear old files
echo "  📝 Clearing old files..."
if ansible frontend -i ansible/inventory/production.yml -m shell -a "rm -rf /var/www/html/*" &>/dev/null; then
    echo -e "${GREEN}  ✅ Old files cleared${NC}"
else
    echo -e "${RED}  ❌ Failed to clear old files${NC}"
    exit 1
fi

# Copy new files
echo "  📂 Copying new build..."
if ansible frontend -i ansible/inventory/production.yml -m copy -a "src=autobot-vue/dist/ dest=/var/www/html/ directory_mode=0755 mode=0644 owner=www-data group=www-data" &>/dev/null; then
    echo -e "${GREEN}  ✅ Files copied successfully${NC}"
else
    echo -e "${RED}  ❌ Failed to copy files${NC}"
    exit 1
fi

# Optional: Restart frontend server (usually not needed for static files)
restart_server=false
if [[ "$1" == "--restart" ]] || [[ "$1" == "-r" ]]; then
    restart_server=true
fi

if $restart_server; then
    echo -e "${YELLOW}  🔄 Restarting frontend server...${NC}"
    if ansible frontend -i ansible/inventory/production.yml -m systemd -a "name=frontend-server state=restarted" &>/dev/null; then
        echo -e "${GREEN}  ✅ Frontend server restarted${NC}"
    else
        echo -e "${YELLOW}  ⚠️  Warning: Failed to restart frontend server${NC}"
    fi
fi

# Step 4: Verify deployment
echo -e "${YELLOW}🔍 Verifying deployment...${NC}"

# Get frontend VM IP
frontend_ip=$(ansible frontend -i ansible/inventory/production.yml -m shell -a "ip addr show | grep 'inet 172' | awk '{print \$2}' | cut -d'/' -f1" 2>/dev/null | tail -1 | grep -oE '172\.[0-9]+\.[0-9]+\.[0-9]+' || echo "unknown")

if [[ "$frontend_ip" != "unknown" ]]; then
    echo -e "${BLUE}  🌐 Frontend URL: http://${frontend_ip}:5173${NC}"

    # Test if frontend is serving files
    if curl -s -o /dev/null -w '%{http_code}' "http://${frontend_ip}:5173" | grep -q "200"; then
        echo -e "${GREEN}  ✅ Frontend is serving files${NC}"

        # Check if new bundle is being served
        if curl -s "http://${frontend_ip}:5173" | grep -q "$bundle_name"; then
            echo -e "${GREEN}  ✅ New bundle is active: ${bundle_name}${NC}"
        else
            echo -e "${YELLOW}  ⚠️  Warning: Bundle name not found in HTML${NC}"
        fi
    else
        echo -e "${RED}  ❌ Frontend not responding${NC}"
    fi
else
    echo -e "${YELLOW}  ⚠️  Warning: Could not determine frontend IP${NC}"
fi

# Summary
echo ""
echo -e "${GREEN}🎉 Frontend sync completed!${NC}"
echo "=================================="
echo -e "${BLUE}Summary:${NC}"
echo "  • Build: ✅ ${bundle_name}"
echo "  • Deploy: ✅ Files copied to VM"
echo "  • URL: http://${frontend_ip}:5173"
echo ""
echo -e "${BLUE}Next steps:${NC}"
echo "  • Open browser and test changes"
echo "  • Check browser console for errors"
echo "  • Use --restart flag if server issues occur"
echo ""
echo -e "${BLUE}Usage examples:${NC}"
echo "  ./sync-frontend.sh           # Normal sync"
echo "  ./sync-frontend.sh --restart  # Sync + restart server"
