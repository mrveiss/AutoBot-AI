#!/bin/bash
# AutoBot - Native VM Deployment Startup Script
# Starts WSL backend to connect to distributed native VM services

set -e

# CRITICAL FIX: Force tf-keras usage to fix Transformers compatibility with Keras 3
export TF_USE_LEGACY_KERAS=1
export KERAS_BACKEND=tensorflow

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Native VM Configuration
NATIVE_ENV_FILE=".env.native-vm"
BACKEND_PID=""
BROWSER_PID=""

# Default options
AUTO_BROWSER=true
SHOW_LOGS=true

print_help() {
    echo -e "${GREEN}AutoBot - Native VM Deployment Startup${NC}"
    echo "Usage: $0 [options]"
    echo ""
    echo "Options:"
    echo "  --no-browser  Don't auto-launch browser"
    echo "  --no-logs     Don't show backend logs"
    echo "  --help        Show this help"
    echo ""
    echo -e "${BLUE}Native VM Architecture:${NC}"
    echo "  WSL Backend:  172.16.168.20:8001"
    echo "  Frontend:     172.16.168.21      (VM1)"
    echo "  NPU Worker:   172.16.168.22:8081 (VM2)" 
    echo "  Redis:        172.16.168.23:6379 (VM3)"
    echo "  AI Stack:     172.16.168.24:8080 (VM4)"
    echo "  Browser:      172.16.168.25:3000 (VM5)"
}

while [[ $# -gt 0 ]]; do
    case $1 in
        --no-browser)
            AUTO_BROWSER=false
            shift
            ;;
        --no-logs)
            SHOW_LOGS=false
            shift
            ;;
        --help|-h)
            print_help
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            print_help
            exit 1
            ;;
    esac
done

# Cleanup function
cleanup() {
    echo -e "\n${YELLOW}🛑 Shutting down AutoBot Native...${NC}"
    
    if [ ! -z "$BACKEND_PID" ]; then
        echo "Stopping backend (PID: $BACKEND_PID)..."
        kill -TERM $BACKEND_PID 2>/dev/null || true
        wait $BACKEND_PID 2>/dev/null || true
    fi
    
    if [ ! -z "$BROWSER_PID" ]; then
        echo "Closing browser (PID: $BROWSER_PID)..."
        kill -TERM $BROWSER_PID 2>/dev/null || true
    fi
    
    echo -e "${GREEN}✅ AutoBot Native stopped cleanly${NC}"
    exit 0
}

# Set up cleanup trap
trap cleanup SIGINT SIGTERM

# Check if native environment file exists
if [ ! -f "$NATIVE_ENV_FILE" ]; then
    echo -e "${RED}❌ Native environment file not found: $NATIVE_ENV_FILE${NC}"
    echo "Please run the native deployment first."
    exit 1
fi

echo -e "${GREEN}🚀 Starting AutoBot Native VM Deployment${NC}"
echo -e "${BLUE}📋 Architecture Overview:${NC}"
echo "  WSL Backend:  172.16.168.20:8001 (This machine)"
echo "  Frontend:     172.16.168.21      (VM1)"
echo "  NPU Worker:   172.16.168.22:8081 (VM2)" 
echo "  Redis:        172.16.168.23:6379 (VM3)"
echo "  AI Stack:     172.16.168.24:8080 (VM4)"
echo "  Browser:      172.16.168.25:3000 (VM5)"
echo ""

# Load native VM environment
echo -e "${YELLOW}📁 Loading native VM configuration...${NC}"
set -a
source "$NATIVE_ENV_FILE"
set +a

# Verify VM services are accessible
echo -e "${YELLOW}🔍 Checking VM services health...${NC}"

check_service() {
    local name=$1
    local url=$2
    local timeout=${3:-5}
    
    if timeout $timeout curl -s "$url" >/dev/null 2>&1; then
        echo -e "  ${GREEN}✅ $name${NC}: $url"
        return 0
    else
        echo -e "  ${RED}❌ $name${NC}: $url (unreachable)"
        return 1
    fi
}

# Check critical services
SERVICES_OK=true

check_service "Frontend" "http://172.16.168.21/" 3 || SERVICES_OK=false
check_service "NPU Worker" "http://172.16.168.22:8081/health" 3 || SERVICES_OK=false
check_service "Redis" "http://172.16.168.23:6379" 3 || SERVICES_OK=false
check_service "AI Stack" "http://172.16.168.24:8080/health" 3 || SERVICES_OK=false
check_service "Browser" "http://172.16.168.25:3000/health" 3 || SERVICES_OK=false

if [ "$SERVICES_OK" = false ]; then
    echo -e "${RED}⚠️  Some VM services are not responding. Backend may have limited functionality.${NC}"
    echo -e "${YELLOW}   You can continue, but some features may not work properly.${NC}"
    read -p "Continue anyway? (y/n): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
else
    echo -e "${GREEN}✅ All VM services are healthy!${NC}"
fi

echo ""

# Start backend with native VM configuration
echo -e "${YELLOW}🔧 Starting WSL backend with native VM configuration...${NC}"

# Use fast backend startup for native deployment
if [ -f "backend/fast_app_factory_fix.py" ]; then
    echo "Using optimized backend startup..."
    cd backend && python3 fast_app_factory_fix.py &
else
    echo "Using standard backend startup..."
    cd backend && python3 -m uvicorn api.main:app --host 0.0.0.0 --port 8001 --reload &
fi

BACKEND_PID=$!
cd ..

echo -e "${GREEN}✅ Backend started (PID: $BACKEND_PID)${NC}"

# Wait for backend to be ready
echo -e "${YELLOW}⏳ Waiting for backend to be ready...${NC}"
for i in {1..30}; do
    if curl -s http://127.0.0.1:8001/api/health >/dev/null 2>&1; then
        echo -e "${GREEN}✅ Backend is ready!${NC}"
        break
    fi
    sleep 1
    echo -n "."
done
echo ""

# Launch browser if requested
if [ "$AUTO_BROWSER" = true ]; then
    echo -e "${YELLOW}🌐 Launching browser...${NC}"
    if command -v firefox >/dev/null 2>&1; then
        firefox "http://172.16.168.21/" >/dev/null 2>&1 &
        BROWSER_PID=$!
    elif command -v google-chrome >/dev/null 2>&1; then
        google-chrome "http://172.16.168.21/" >/dev/null 2>&1 &
        BROWSER_PID=$!
    else
        echo -e "${YELLOW}No browser found. Please open http://172.16.168.21/ manually${NC}"
    fi
fi

echo ""
echo -e "${GREEN}🎉 AutoBot Native VM Deployment is running!${NC}"
echo -e "${BLUE}📱 Access Points:${NC}"
echo "  🌐 Frontend:  http://172.16.168.21/"
echo "  🔧 Backend:   http://172.16.168.20:8001/"
echo "  🧠 AI Stack:  http://172.16.168.24:8080/health"
echo "  🚀 NPU Worker: http://172.16.168.22:8081/health"
echo "  🌍 Browser:   http://172.16.168.25:3000/health"
echo ""
echo -e "${YELLOW}Press Ctrl+C to stop all services${NC}"

# Show logs if requested
if [ "$SHOW_LOGS" = true ]; then
    echo -e "${BLUE}📋 Backend logs (Ctrl+C to stop):${NC}"
    wait $BACKEND_PID
else
    # Just wait for backend without showing logs
    wait $BACKEND_PID
fi