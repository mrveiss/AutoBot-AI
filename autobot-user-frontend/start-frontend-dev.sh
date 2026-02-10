#!/bin/bash
# AutoBot Frontend Development Server Startup
# This script ensures the Vue.js development server starts properly with correct configuration

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
_PROJECT_ROOT="$SCRIPT_DIR"
while [ "$_PROJECT_ROOT" != "/" ] && [ ! -f "$_PROJECT_ROOT/.env" ]; do
    _PROJECT_ROOT="$(dirname "$_PROJECT_ROOT")"
done
source "$_PROJECT_ROOT/infrastructure/shared/scripts/lib/ssot-config.sh" 2>/dev/null || true

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}🚀 AutoBot Frontend Development Server${NC}"
echo -e "${BLUE}======================================${NC}"

# Check if we're in the correct directory
if [ ! -f "package.json" ]; then
    echo -e "${RED}❌ Error: package.json not found. Please run this script from the autobot-vue directory.${NC}"
    exit 1
fi

# Check if node_modules exists
if [ ! -d "node_modules" ]; then
    echo -e "${YELLOW}📦 Installing dependencies...${NC}"
    npm install
fi

# Check for .env file
# Define centralized defaults (should match defaults.js)
DEFAULT_BACKEND_HOST="${AUTOBOT_BACKEND_HOST:-172.16.168.20}"
DEFAULT_BACKEND_PORT="${AUTOBOT_BACKEND_PORT:-8001}"

if [ ! -f ".env" ]; then
    echo -e "${YELLOW}⚠️  Warning: .env file not found. Using centralized defaults.${NC}"
    echo -e "${YELLOW}   Backend will default to ${DEFAULT_BACKEND_HOST}:${DEFAULT_BACKEND_PORT}${NC}"
fi

# Load environment variables if .env exists
if [ -f ".env" ]; then
    export $(grep -v '^#' .env | xargs)
    echo -e "${GREEN}✅ Loaded environment variables from .env${NC}"
fi

# Show configuration
echo -e "${BLUE}📋 Configuration:${NC}"
echo -e "   Backend Host: ${VITE_BACKEND_HOST:-$DEFAULT_BACKEND_HOST}"
echo -e "   Backend Port: ${VITE_BACKEND_PORT:-$DEFAULT_BACKEND_PORT}"
echo -e "   Frontend Port: 5173"
echo -e "   Environment: ${VITE_ENV:-development}"

# Check if backend is accessible
echo -e "${BLUE}🔍 Checking backend connectivity...${NC}"
BACKEND_HOST=${VITE_BACKEND_HOST:-$DEFAULT_BACKEND_HOST}
BACKEND_PORT=${VITE_BACKEND_PORT:-$DEFAULT_BACKEND_PORT}

if curl -s --connect-timeout 5 "http://${BACKEND_HOST}:${BACKEND_PORT}/api/system/health" > /dev/null; then
    echo -e "${GREEN}✅ Backend is accessible at http://${BACKEND_HOST}:${BACKEND_PORT}${NC}"
else
    echo -e "${YELLOW}⚠️  Backend not accessible at http://${BACKEND_HOST}:${BACKEND_PORT}${NC}"
    echo -e "${YELLOW}   Frontend will still start but API calls may fail${NC}"
fi

# Kill any existing processes on port 5173
if lsof -ti:5173 > /dev/null 2>&1; then
    echo -e "${YELLOW}🔄 Stopping existing processes on port 5173...${NC}"
    kill -9 $(lsof -ti:5173) 2>/dev/null || true
fi

echo -e "${GREEN}🚀 Starting Vue.js development server...${NC}"
echo -e "${GREEN}   Available at:${NC}"
echo -e "${GREEN}   - http://localhost:5173/${NC}"
echo -e "${GREEN}   - http://${AUTOBOT_BACKEND_HOST:-172.16.168.20}:5173/${NC}"
echo -e "${GREEN}   - http://192.168.168.17:5173/${NC}"
echo ""
echo -e "${BLUE}The desktop interface will be available at:${NC}"
echo -e "${BLUE}   http://${AUTOBOT_BACKEND_HOST:-172.16.168.20}:5173/desktop${NC}"
echo ""
echo -e "${YELLOW}Press Ctrl+C to stop the server${NC}"

# Start the development server
npm run dev -- --host 0.0.0.0 --port 5173
