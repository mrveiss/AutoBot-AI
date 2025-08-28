#!/bin/bash
# AutoBot - Unified Docker Deployment
# Automatically detects and configures for your environment

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Parse command line arguments  
DEV_MODE=false
TEST_MODE=false
FORCE_ENV=""
NO_BUILD=false
NO_BROWSER=false
BACKEND_PID=""

print_help() {
    echo "AutoBot - Unified Docker Deployment"
    echo "Usage: $0 [options]"
    echo ""
    echo "Options:"
    echo "  --dev         Development mode (hot reload, source mounting, auto-browser)"
    echo "  --test-mode   Test mode (minimal services)" 
    echo "  --no-build    Skip building Docker images (use existing)"
    echo "  --no-browser  Don't auto-launch browser in dev mode"
    echo "  --force-env   Force specific environment (docker-desktop|wsl|native|host-network)"
    echo "  --help        Show this help"
    echo ""
    echo "Environment is auto-detected if not forced."
}

while [[ $# -gt 0 ]]; do
    case $1 in
        --dev)
            DEV_MODE=true
            shift
            ;;
        --test-mode)
            TEST_MODE=true
            shift
            ;;
        --no-build)
            NO_BUILD=true
            shift
            ;;
        --no-browser)
            NO_BROWSER=true
            shift
            ;;
        --force-env)
            FORCE_ENV="$2"
            shift 2
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

echo -e "${GREEN}🚀 Starting AutoBot${NC}"
echo "=================="
echo "Mode: $([ "$DEV_MODE" = "true" ] && echo "Development" || ([ "$TEST_MODE" = "true" ] && echo "Test" || echo "Production"))"
echo "Time: $(date)"
echo

# Load Docker API compatibility helper
source ./scripts/docker_api_helper.sh

# Detect Docker environment
detect_environment() {
    echo -e "${YELLOW}🔍 Detecting environment...${NC}"
    
    # Check Docker API compatibility
    local api_version=$(get_compatible_api_version)
    if [ -n "$api_version" ]; then
        export DOCKER_API_VERSION="$api_version"
        echo -e "   ${GREEN}✅${NC} Docker API version: $api_version"
    fi
    
    # Check Docker Compose version
    local compose_version=$(check_docker_compose_v2)
    echo -e "   ${GREEN}✅${NC} Docker Compose: $compose_version"
    
    # Detect environment type
    local env_type="native"
    
    if [ -n "$FORCE_ENV" ]; then
        env_type="$FORCE_ENV"
        echo -e "   ${YELLOW}⚠️${NC}  Forced environment: $env_type"
    elif grep -q microsoft /proc/version 2>/dev/null; then
        env_type="wsl"
        # Check if Docker Desktop is running
        if docker context ls | grep -q "desktop-linux"; then
            env_type="docker-desktop"
        fi
    fi
    
    echo -e "   ${GREEN}✅${NC} Environment: $env_type"
    echo "$env_type"
}

# Load environment configuration
load_environment() {
    local env_type="$1"
    local env_file=""
    
    case "$env_type" in
        docker-desktop)
            env_file=".env.docker-desktop"
            ;;
        wsl)
            env_file=".env.wsl-host-network"
            ;;
        host-network)
            env_file=".env.wsl-host-network"
            ;;
        native|*)
            env_file=".env.localhost"
            ;;
    esac
    
    # Create default env if it doesn't exist
    if [ ! -f "$env_file" ]; then
        echo -e "${YELLOW}Creating default environment file: $env_file${NC}"
        cat > "$env_file" << EOF
# AutoBot Environment Configuration
# Generated on $(date)

# Network Configuration
DOCKER_SUBNET=172.18.0.0/16

# Service Ports
REDIS_PORT=6379
REDISINSIGHT_PORT=8002
SEQ_PORT=5341
API_PORT=8001
FRONTEND_PORT=5173
BROWSER_PORT=3001

# Service Hosts
REDIS_HOST=localhost
SEQ_URL=http://localhost:5341

# API Configuration
VITE_API_URL=http://localhost:8001
DEBUG_MODE=false

# Development Options
NODE_ENV=production
BACKEND_EXTRA_ARGS=
FRONTEND_COMMAND=npm run preview -- --host 0.0.0.0
EOF
    fi
    
    echo -e "${GREEN}📋 Loading configuration: $env_file${NC}"
    set -a
    source "$env_file"
    set +a
    
    # Override for development mode
    if [ "$DEV_MODE" = "true" ]; then
        export NODE_ENV=development
        export DEBUG_MODE=true
        export BACKEND_EXTRA_ARGS="--reload"
        export FRONTEND_COMMAND="npm run dev -- --host 0.0.0.0"
    fi
}

# Cleanup function
cleanup() {
    echo -e "\n${RED}🛑 Stopping AutoBot...${NC}"
    
    # Stop backend process if running
    if [ ! -z "$BACKEND_PID" ] && kill -0 $BACKEND_PID 2>/dev/null; then
        echo "Stopping backend process (PID: $BACKEND_PID)..."
        kill $BACKEND_PID 2>/dev/null || true
        wait $BACKEND_PID 2>/dev/null || true
    fi
    
    # Stop Docker services
    if [ "$compose_cmd" = "docker compose" ]; then
        docker compose -f $COMPOSE_FILE down
    else
        docker-compose -f $COMPOSE_FILE down
    fi
    
    # Stop any remaining orphaned processes
    pkill -f "uvicorn.*backend.main:app" 2>/dev/null || true
    pkill -f "playwright-server" 2>/dev/null || true
    pkill -f "npm run" 2>/dev/null || true
    
    echo -e "${GREEN}✅ AutoBot stopped${NC}"
    exit 0
}

# Main execution
main() {
    # Detect environment
    env_type=$(detect_environment)
    
    # Load configuration
    load_environment "$env_type"
    
    # Determine docker-compose command
    compose_cmd="docker-compose"
    if [ "$(check_docker_compose_v2)" = "v2" ]; then
        compose_cmd="docker compose"
    fi
    
    # Set up cleanup trap
    trap cleanup INT TERM
    
    # Stop existing services
    echo -e "${YELLOW}🧹 Cleaning up previous services...${NC}"
    $compose_cmd -f docker-compose.unified.yml down 2>/dev/null || true
    
    # Handle special networking cases
    if [ "$env_type" = "host-network" ] || [ "$env_type" = "wsl" ]; then
        echo -e "${YELLOW}📌 Using host networking mode${NC}"
        export COMPOSE_FILE=docker-compose.unified.yml:docker/compose/docker-compose.host-network-override.yml
    else
        export COMPOSE_FILE=docker-compose.unified.yml
    fi
    
    # Build images if needed
    build_needed=false
    
    # Skip build if --no-build flag is used
    if [ "$NO_BUILD" = "true" ]; then
        echo -e "${GREEN}⏭️  Skipping Docker build (--no-build flag)${NC}"
    # Always build in dev mode for latest changes
    elif [ "$DEV_MODE" = "true" ]; then
        echo -e "${YELLOW}🔨 Building Docker images (dev mode)...${NC}"
        build_needed=true
    else
        # Check if images exist for production mode
        missing_images=""
        for image in "autobot-frontend:latest" "autobot-browser:latest" "autobot-ai-stack:latest" "autobot-npu-worker:latest"; do
            if [ -z "$(docker images -q $image 2>/dev/null)" ]; then
                missing_images="$missing_images $image"
                build_needed=true
            fi
        done
        
        if [ "$build_needed" = "true" ]; then
            echo -e "${YELLOW}🔨 Building missing Docker images:$missing_images${NC}"
        else
            echo -e "${GREEN}✅ All Docker images exist, skipping build${NC}"
        fi
    fi
    
    if [ "$build_needed" = "true" ]; then
        $compose_cmd -f $COMPOSE_FILE build
    fi
    
    # Start services
    echo -e "${GREEN}🚀 Starting services...${NC}"
    
    if [ "$TEST_MODE" = "true" ]; then
        # Start only essential services in test mode
        $compose_cmd -f $COMPOSE_FILE up -d redis seq
    else
        # Start all Docker services
        $compose_cmd -f $COMPOSE_FILE up -d
    fi
    
    # Start backend on host (needed for system access)
    if [ "$TEST_MODE" != "true" ]; then
        echo -e "${YELLOW}🖥️  Starting backend on host...${NC}"
        
        # Ensure we're in project root for proper module imports
        if [ ! -f "backend/main.py" ]; then
            echo "Error: backend/main.py not found. Make sure you're in the project root."
            exit 1
        fi
        
        # Start backend in background from project root
        if [ "$DEV_MODE" = "true" ]; then
            echo "Starting backend in development mode..."
            python -m uvicorn backend.main:app --host 0.0.0.0 --port ${API_PORT:-8001} --reload &
        else
            echo "Starting backend in production mode..."
            python -m uvicorn backend.main:app --host 0.0.0.0 --port ${API_PORT:-8001} &
        fi
        
        BACKEND_PID=$!
        echo "Backend started with PID: $BACKEND_PID"
    fi
    
    # Wait for services to be ready
    echo -e "${YELLOW}⏳ Waiting for services to be ready...${NC}"
    
    # Check Redis
    echo -n "   Redis: "
    for i in {1..30}; do
        if docker exec autobot-redis redis-cli ping >/dev/null 2>&1; then
            echo -e "${GREEN}✅ Ready${NC}"
            break
        elif [ $i -eq 30 ]; then
            echo -e "${RED}❌ Failed${NC}"
            echo "Redis container logs:"
            docker logs autobot-redis --tail 10
            exit 1
        fi
        sleep 2
    done
    
    # Check Seq
    echo -n "   Seq: "
    for i in {1..30}; do
        if curl -s http://${SEQ_HOST:-localhost}:${SEQ_PORT:-5341}/ >/dev/null 2>&1; then
            echo -e "${GREEN}✅ Ready${NC}"
            break
        elif [ $i -eq 30 ]; then
            echo -e "${YELLOW}⚠️  Timeout${NC}"
        fi
        sleep 2
    done
    
    if [ "$TEST_MODE" != "true" ]; then
        # Check Backend (runs on host, not in container)
        echo -n "   Backend: "
        for i in {1..30}; do
            if curl -s http://localhost:${API_PORT:-8001}/api/system/health >/dev/null 2>&1; then
                echo -e "${GREEN}✅ Ready${NC}"
                break
            elif [ $i -eq 30 ]; then
                echo -e "${RED}❌ Failed${NC}"
                echo "Backend is not running on port ${API_PORT:-8001}"
                echo "Start backend manually with: ./run_agent.sh or python backend/main.py"
                exit 1
            fi
            sleep 2
        done
        
        # Check Frontend
        echo -n "   Frontend: "
        for i in {1..30}; do
            if curl -s http://localhost:${FRONTEND_PORT:-5173}/ >/dev/null 2>&1; then
                echo -e "${GREEN}✅ Ready${NC}"
                break
            elif [ $i -eq 30 ]; then
                echo -e "${YELLOW}⚠️  Timeout${NC}"
            fi
            sleep 2
        done
    fi
    
    # Display access information
    echo
    echo -e "${GREEN}🎉 AutoBot Started Successfully!${NC}"
    echo "==============================="
    echo "📍 Services:"
    echo "   🌐 Frontend:  http://localhost:${FRONTEND_PORT:-5173}"
    echo "   🖥️  Backend:   http://localhost:${API_PORT:-8001}"
    echo "   📊 Logs:      http://localhost:${SEQ_PORT:-5341}"
    echo "   🔍 Redis:     http://localhost:${REDISINSIGHT_PORT:-8002}"
    echo
    echo "🔧 Configuration:"
    echo "   Environment: $env_type"
    echo "   Mode: $([ "$DEV_MODE" = "true" ] && echo "Development" || echo "Production")"
    echo "   Compose: $COMPOSE_FILE"
    echo
    echo -e "${YELLOW}💡 Commands:${NC}"
    echo "   View logs:    $compose_cmd -f $COMPOSE_FILE logs -f"
    echo "   Stop:         Press Ctrl+C"
    echo "   Status:       $compose_cmd -f $COMPOSE_FILE ps"
    echo
    
    # Launch browser in development mode
    if [ "$DEV_MODE" = "true" ] && [ "$NO_BROWSER" = "false" ]; then
        echo -e "${YELLOW}🌐 Opening browser for development...${NC}"
        
        # Try different browser commands in order of preference
        browser_launched=false
        
        # Try xdg-open (Linux standard)
        if command -v xdg-open >/dev/null 2>&1; then
            echo "Opening frontend in default browser..."
            xdg-open "http://localhost:${FRONTEND_PORT:-5173}" >/dev/null 2>&1 &
            browser_launched=true
        # Try google-chrome
        elif command -v google-chrome >/dev/null 2>&1; then
            echo "Opening frontend in Google Chrome..."
            google-chrome "http://localhost:${FRONTEND_PORT:-5173}" >/dev/null 2>&1 &
            browser_launched=true
        # Try chromium
        elif command -v chromium-browser >/dev/null 2>&1; then
            echo "Opening frontend in Chromium..."
            chromium-browser "http://localhost:${FRONTEND_PORT:-5173}" >/dev/null 2>&1 &
            browser_launched=true
        # Try firefox
        elif command -v firefox >/dev/null 2>&1; then
            echo "Opening frontend in Firefox..."
            firefox "http://localhost:${FRONTEND_PORT:-5173}" >/dev/null 2>&1 &
            browser_launched=true
        fi
        
        if [ "$browser_launched" = "true" ]; then
            echo -e "${GREEN}✅ Browser launched - you can monitor frontend logs and development${NC}"
        else
            echo -e "${YELLOW}⚠️  No browser found. Please manually open: http://localhost:${FRONTEND_PORT:-5173}${NC}"
        fi
        
        echo
    fi
    
    # Keep running and show logs
    echo -e "${GREEN}📋 Following logs (Ctrl+C to stop)...${NC}"
    $compose_cmd -f $COMPOSE_FILE logs -f
}

# Run main function
main