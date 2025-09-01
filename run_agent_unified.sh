#!/bin/bash
# AutoBot - Unified Docker Deployment
# Automatically detects and configures for your environment

set -e

# CRITICAL FIX: Force tf-keras usage to fix Transformers compatibility with Keras 3
export TF_USE_LEGACY_KERAS=1
export KERAS_BACKEND=tensorflow

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
REBUILD=false
BUILD_DEFAULT=false  # Changed: Don't build by default unless images are missing
NO_BROWSER=false
CLEAN_SHUTDOWN=false
BACKEND_PID=""
BROWSER_PID=""
DESKTOP_ACCESS=true
VNC_PID=""

print_help() {
    echo "AutoBot - Unified Docker Deployment"
    echo "Usage: $0 [options]"
    echo ""
    echo "Options:"
    echo "  --dev         Development mode (hot reload, source mounting, smart browser reuse)"
    echo "  --test-mode   Test mode (minimal services)" 
    echo "  --no-build    Skip building Docker images (use existing)"
    echo "  --build       Force build even if images exist"  
    echo "  --rebuild     Force rebuild of all Docker images"
    echo "  --no-browser  Don't auto-launch browser in dev mode"
    echo "  --desktop     Enable desktop access via VNC (default: enabled, launches VNC server + noVNC web client)"
    echo "  --no-desktop  Disable desktop access via VNC"
    echo "  --clean       Remove containers on shutdown (default: just stop)"
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
        --build)
            BUILD_DEFAULT=true
            shift
            ;;
        --rebuild)
            REBUILD=true
            shift
            ;;
        --no-browser)
            NO_BROWSER=true
            shift
            ;;
        --desktop)
            DESKTOP_ACCESS=true
            shift
            ;;
        --no-desktop)
            DESKTOP_ACCESS=false
            shift
            ;;
        --clean)
            CLEAN_SHUTDOWN=true
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

echo -e "${GREEN}🤖 Welcome to AutoBot!${NC}"
echo "======================="
echo -e "${GREEN}🚀 Starting AutoBot system...${NC}"
echo ""
echo -e "Mode: ${YELLOW}$([ "$DEV_MODE" = "true" ] && echo "Development 👨‍💻" || ([ "$TEST_MODE" = "true" ] && echo "Test 🧪" || echo "Production 🏭"))${NC}"
echo "Desktop: $([ "$DESKTOP_ACCESS" = "true" ] && echo "Enabled (VNC + noVNC)" || echo "Disabled")"
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
        # Frontend runs in Docker, backend on host - use Docker internal hostname
        export VITE_API_BASE_URL=http://host.docker.internal:8001
        export VITE_WS_BASE_URL=ws://host.docker.internal:8001/ws
    fi
}

# Function to check if browser is already open with frontend URL
check_existing_browser() {
    local frontend_url="http://localhost:${FRONTEND_PORT:-5173}"
    
    # Check for Chrome/Chromium processes with our URL
    if pgrep -f "chrome.*${FRONTEND_PORT:-5173}" >/dev/null 2>&1; then
        echo -e "${GREEN}   ✅ Chrome already open with frontend${NC}"
        return 0
    elif pgrep -f "chromium.*${FRONTEND_PORT:-5173}" >/dev/null 2>&1; then
        echo -e "${GREEN}   ✅ Chromium already open with frontend${NC}"
        return 0
    elif pgrep -f "firefox.*${FRONTEND_PORT:-5173}" >/dev/null 2>&1; then
        echo -e "${GREEN}   ✅ Firefox already open with frontend${NC}"
        return 0
    fi
    
    return 1
}

# Function to focus existing browser window (try to bring it to front)
focus_existing_browser() {
    local frontend_url="http://localhost:${FRONTEND_PORT:-5173}"
    
    # Try to use xdg-open to open URL in existing browser instance
    if command -v xdg-open >/dev/null 2>&1; then
        echo -e "${YELLOW}   🔄 Opening frontend in existing browser...${NC}"
        xdg-open "$frontend_url" >/dev/null 2>&1 &
        return 0
    fi
    
    # Try wmctrl to focus existing browser window if available
    if command -v wmctrl >/dev/null 2>&1; then
        wmctrl -a "localhost:${FRONTEND_PORT:-5173}" 2>/dev/null || true
        return 0
    fi
    
    return 1
}

# Function to setup and start VNC desktop access
setup_desktop_access() {
    echo -e "${YELLOW}🖥️  Setting up desktop access via VNC...${NC}"
    
    # Check if VNC server is available
    if ! command -v vncserver >/dev/null 2>&1; then
        echo -e "${RED}❌ VNC server not found. Install with: sudo apt install tigervnc-standalone-server${NC}"
        return 1
    fi
    
    # Check if noVNC is available
    if ! command -v python3 >/dev/null 2>&1; then
        echo -e "${RED}❌ Python3 required for noVNC websockify${NC}"
        return 1
    fi
    
    # Ensure VNC password is configured for kex
    if [ ! -f ~/.vnc/passwd ]; then
        echo -e "${YELLOW}   🔐 Setting up VNC password (using 'autobot' as default)${NC}"
        mkdir -p ~/.vnc
        echo -e "autobot\nautobot" | vncpasswd -f > ~/.vnc/passwd
        chmod 600 ~/.vnc/passwd
        echo -e "${GREEN}   ✅ VNC password configured${NC}"
    fi
    
    # Start Kali kex VNC server (or check if already running)
    if ! pgrep -f "Xtigervnc" > /dev/null; then
        echo -e "${YELLOW}   🚀 Starting Kali kex VNC server...${NC}"
        echo -e "${YELLOW}   💡 If prompted for VNC password, enter: autobot${NC}"
        
        # Start kex in window mode with server only (no client)
        kex --win --start &
        
        # Wait for kex to start
        echo -e "${YELLOW}   ⏳ Waiting for kex to initialize...${NC}"
        sleep 10
    else
        echo -e "${GREEN}   ✅ Kali kex VNC server already running${NC}"
    fi
    
    # Check if kex VNC server started
    if ! pgrep -f "kex.*vnc" > /dev/null && ! pgrep -f "Xtigervnc" > /dev/null; then
        echo -e "${RED}❌ Failed to start kex VNC server${NC}"
        return 1
    fi
    
    echo -e "${GREEN}   ✅ Kali kex VNC server running${NC}"
    
    # Start noVNC web client using Python websockify
    echo -e "${YELLOW}   🌐 Starting noVNC web client on port 6080...${NC}"
    
    # Check if websockify is available
    if ! python3 -c "import websockify" 2>/dev/null; then
        echo -e "${YELLOW}   📦 Installing websockify...${NC}"
        pip3 install websockify --user >/dev/null 2>&1 || {
            echo -e "${RED}❌ Failed to install websockify${NC}"
            return 1
        }
    fi
    
    # Download noVNC if not present
    if [ ! -d ~/.novnc ]; then
        echo -e "${YELLOW}   📦 Downloading noVNC...${NC}"
        git clone https://github.com/novnc/noVNC.git ~/.novnc >/dev/null 2>&1 || {
            echo -e "${RED}❌ Failed to download noVNC${NC}"
            return 1
        }
    fi
    
    # Start websockify to bridge kex VNC and WebSocket (port 5901 for display :1)
    cd ~/.novnc
    python3 -m websockify 6080 localhost:5901 >/dev/null 2>&1 &
    WEBSOCKIFY_PID=$!
    sleep 2
    
    echo -e "${GREEN}   ✅ noVNC web client running on http://localhost:6080${NC}"
    echo -e "${GREEN}   🔗 Direct URL: http://localhost:6080/vnc.html?autoconnect=true&password=autobot${NC}"
    
    return 0
}

# Function to stop desktop access
stop_desktop_access() {
    echo -e "${YELLOW}🛑 Stopping desktop access...${NC}"
    
    # Stop websockify
    if [ ! -z "$WEBSOCKIFY_PID" ] && kill -0 $WEBSOCKIFY_PID 2>/dev/null; then
        kill $WEBSOCKIFY_PID 2>/dev/null || true
    fi
    
    # Kill any remaining websockify processes
    pkill -f "websockify.*6080" 2>/dev/null || true
    
    # Stop kex VNC server
    kex --stop 2>/dev/null || true
    pkill -f "kex.*vnc" 2>/dev/null || true
    
    echo -e "${GREEN}   ✅ Desktop access stopped${NC}"
}

# Cleanup function
cleanup() {
    echo -e "\n${RED}🛑 Stopping AutoBot...${NC}"
    
    # Stop desktop access if enabled
    if [ "$DESKTOP_ACCESS" = "true" ]; then
        stop_desktop_access
    fi
    
    # Stop browser process if running
    if [ ! -z "$BROWSER_PID" ] && kill -0 $BROWSER_PID 2>/dev/null; then
        echo "Stopping browser process (PID: $BROWSER_PID)..."
        kill -TERM $BROWSER_PID 2>/dev/null || true
        sleep 1
        # Force kill if still running
        if kill -0 $BROWSER_PID 2>/dev/null; then
            echo "Force killing browser process..."
            kill -KILL $BROWSER_PID 2>/dev/null || true
        fi
        wait $BROWSER_PID 2>/dev/null || true
    fi
    
    # Stop backend process if running
    if [ ! -z "$BACKEND_PID" ] && kill -0 $BACKEND_PID 2>/dev/null; then
        echo "Stopping backend process (PID: $BACKEND_PID)..."
        kill -TERM $BACKEND_PID 2>/dev/null || true
        sleep 2
        # Force kill if still running
        if kill -0 $BACKEND_PID 2>/dev/null; then
            echo "Force killing backend process..."
            kill -KILL $BACKEND_PID 2>/dev/null || true
        fi
        wait $BACKEND_PID 2>/dev/null || true
    fi
    
    # Stop Docker services
    if [ "$CLEAN_SHUTDOWN" = "true" ]; then
        echo "Removing containers and cleaning up..."
        if [ "$compose_cmd" = "docker compose" ]; then
            docker compose -f $COMPOSE_FILE down
        else
            docker-compose -f $COMPOSE_FILE down
        fi
    else
        echo "Stopping containers (preserving data)..."
        if [ "$compose_cmd" = "docker compose" ]; then
            docker compose -f $COMPOSE_FILE stop
        else
            docker-compose -f $COMPOSE_FILE stop
        fi
    fi
    
    # Kill remaining processes more aggressively
    echo "Cleaning up any remaining processes..."
    
    # Kill browser processes that might be holding frontend open
    if [ "$DEV_MODE" = "true" ]; then
        echo "Closing any browsers opened for frontend monitoring..."
        # Kill Chrome/Chromium processes specifically opened for our frontend
        pkill -f "chrome.*localhost:${FRONTEND_PORT:-5173}" 2>/dev/null || true
        pkill -f "chromium.*localhost:${FRONTEND_PORT:-5173}" 2>/dev/null || true
        pkill -f "firefox.*localhost:${FRONTEND_PORT:-5173}" 2>/dev/null || true
    fi
    
    # Kill VNC and noVNC processes if desktop access was enabled
    if [ "$DESKTOP_ACCESS" = "true" ]; then
        echo "Cleaning up VNC desktop processes..."
        pkill -f "websockify.*6080" 2>/dev/null || true
        vncserver -kill :1 2>/dev/null || true
        pkill -f "chrome.*localhost:6080" 2>/dev/null || true
        pkill -f "chromium.*localhost:6080" 2>/dev/null || true
        pkill -f "firefox.*localhost:6080" 2>/dev/null || true
    fi
    
    # Kill uvicorn processes (including both old and new backend)
    pkill -f "uvicorn.*backend" 2>/dev/null || true
    pkill -f "uvicorn.*fast_app_factory_fix" 2>/dev/null || true
    pkill -f "uvicorn.*async_app_factory" 2>/dev/null || true
    pkill -f "uvicorn.*backend.main:app" 2>/dev/null || true
    pkill -f "playwright-server" 2>/dev/null || true
    pkill -f "npm run" 2>/dev/null || true
    
    # Force kill processes on specific ports
    echo "Killing processes on ports ${API_PORT:-8001}, ${FRONTEND_PORT:-5173}..."
    
    # Kill backend port
    if command -v fuser >/dev/null 2>&1; then
        fuser -k ${API_PORT:-8001}/tcp 2>/dev/null || true
        fuser -k ${FRONTEND_PORT:-5173}/tcp 2>/dev/null || true
    elif command -v lsof >/dev/null 2>&1; then
        # Alternative using lsof + kill
        for port in ${API_PORT:-8001} ${FRONTEND_PORT:-5173}; do
            pids=$(lsof -t -i:$port 2>/dev/null || true)
            if [ ! -z "$pids" ]; then
                echo "Killing processes on port $port: $pids"
                kill -TERM $pids 2>/dev/null || true
                sleep 1
                kill -KILL $pids 2>/dev/null || true
            fi
        done
    else
        echo "Warning: Neither fuser nor lsof available for port cleanup"
    fi
    
    # Give processes time to shut down
    sleep 1
    
    # Final check and report
    if command -v lsof >/dev/null 2>&1; then
        remaining=$(lsof -t -i:${API_PORT:-8001} -i:${FRONTEND_PORT:-5173} 2>/dev/null || true)
        if [ ! -z "$remaining" ]; then
            echo -e "${YELLOW}⚠️  Some processes might still be running on ports ${API_PORT:-8001}, ${FRONTEND_PORT:-5173}${NC}"
            echo "   If needed, run: sudo fuser -k ${API_PORT:-8001}/tcp"
        fi
    fi
    
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
    # Force rebuild if --rebuild flag is used
    elif [ "$REBUILD" = "true" ]; then
        echo -e "${YELLOW}🔨 Force rebuilding all Docker images (--rebuild flag)...${NC}"
        build_needed=true
    # Force build if --build flag is used (even if images exist)
    elif [ "$BUILD_DEFAULT" = "true" ]; then
        echo -e "${YELLOW}🔨 Force building Docker images (--build flag)...${NC}"
        build_needed=true
    else
        # Check if images exist - only build missing images
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
            echo -e "   ${YELLOW}ℹ️  Use --build to force build, --rebuild to force rebuild${NC}"
        fi
    fi
    
    if [ "$build_needed" = "true" ]; then
        $compose_cmd -f $COMPOSE_FILE build
    fi
    
    # Start services
    echo -e "${GREEN}🚀 Launching AutoBot services...${NC}"
    echo -e "   ${YELLOW}📦 Starting Docker containers (this may take a moment)...${NC}"
    
    if [ "$TEST_MODE" = "true" ]; then
        # Start only essential services in test mode
        $compose_cmd -f $COMPOSE_FILE up -d redis seq
    else
        # Start all Docker services
        $compose_cmd -f $COMPOSE_FILE up -d
    fi
    
    # Rotate startup logs before starting services
    echo -e "${YELLOW}📋 Rotating startup logs...${NC}"
    if [ -f "scripts/rotate_startup_logs.py" ]; then
        python3 scripts/rotate_startup_logs.py
    else
        echo -e "${YELLOW}   ⚠️  Startup log rotation script not found, skipping...${NC}"
    fi
    
    # Start backend on host (needed for system access)
    if [ "$TEST_MODE" != "true" ]; then
        echo -e "${GREEN}🖥️  Starting AutoBot backend...${NC}"
        echo -e "   ${YELLOW}⚡ Using fast startup mode (2-3 seconds)...${NC}"
        
        # Ensure we're in project root for proper module imports
        if [ ! -f "backend/main.py" ]; then
            echo "Error: backend/main.py not found. Make sure you're in the project root."
            exit 1
        fi
        
        # Start backend in background from project root
        # Use venv python directly to ensure dependencies are available
        # CRITICAL FIX: Use fast_app_factory_fix to prevent deadlocks (per CLAUDE.md)
        if [ "$DEV_MODE" = "true" ]; then
            echo -e "   ${YELLOW}🔄 Development mode: Hot reload enabled (fast startup)${NC}"
            ./venv/bin/python -m uvicorn backend.fast_app_factory_fix:app --host 0.0.0.0 --port ${API_PORT:-8001} --reload &
        else
            echo -e "   ${YELLOW}🏭 Production mode: Optimized performance (fast startup)${NC}"
            ./venv/bin/python -m uvicorn backend.fast_app_factory_fix:app --host 0.0.0.0 --port ${API_PORT:-8001} &
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
    if [ "$DESKTOP_ACCESS" = "true" ]; then
        echo "   🖥️  Desktop:   http://localhost:6080/vnc.html?autoconnect=true&password=autobot"
    fi
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
    if [ "$DESKTOP_ACCESS" = "true" ]; then
        echo "   Desktop:      VNC Password is 'autobot'"
    fi
    echo
    
    # Auto-launch browser in dev mode for error monitoring
    if [ "$DEV_MODE" = "true" ] && [ "$NO_BROWSER" = "false" ]; then
        echo -e "${YELLOW}🖥️  Setting up browser for frontend error monitoring...${NC}"
        sleep 3  # Give frontend a moment to fully load
        
        # Check if browser is already open with our frontend
        if check_existing_browser; then
            # Browser already running, try to focus/open new tab
            focus_existing_browser
        else
            # Launch new browser instance
            echo -e "${YELLOW}   📖 Launching new browser instance...${NC}"
            
            # Try different browser commands (copied from proven run_agent.sh logic)
            if command -v google-chrome >/dev/null 2>&1; then
                google-chrome --new-window --auto-open-devtools-for-tabs "http://localhost:${FRONTEND_PORT:-5173}" >/dev/null 2>&1 &
                BROWSER_PID=$!
                echo -e "${GREEN}   ✅ Chrome launched with DevTools open (PID: $BROWSER_PID)${NC}"
            elif command -v chromium-browser >/dev/null 2>&1; then
                chromium-browser --new-window --auto-open-devtools-for-tabs "http://localhost:${FRONTEND_PORT:-5173}" >/dev/null 2>&1 &
                BROWSER_PID=$!
                echo -e "${GREEN}   ✅ Chromium launched with DevTools open (PID: $BROWSER_PID)${NC}"
            elif command -v firefox >/dev/null 2>&1; then
                firefox --new-window "http://localhost:${FRONTEND_PORT:-5173}" >/dev/null 2>&1 &
                BROWSER_PID=$!
                echo -e "${GREEN}   ✅ Firefox launched (PID: $BROWSER_PID) - open F12 for DevTools${NC}"
            else
                echo -e "${YELLOW}   ⚠️  No browser found - manually open: http://localhost:${FRONTEND_PORT:-5173}${NC}"
                echo -e "${YELLOW}   💡 Press F12 to open DevTools for error monitoring${NC}"
            fi
        fi
        echo
    fi
    
    # Setup desktop access if requested
    if [ "$DESKTOP_ACCESS" = "true" ]; then
        if setup_desktop_access; then
            # Launch browser for desktop access too
            if [ "$NO_BROWSER" = "false" ]; then
                echo -e "${YELLOW}🖥️  Opening desktop access in browser...${NC}"
                sleep 2
                desktop_url="http://localhost:6080/vnc.html?autoconnect=true&password=autobot"
                
                # Try to open in existing browser first
                if command -v xdg-open >/dev/null 2>&1; then
                    xdg-open "$desktop_url" >/dev/null 2>&1 &
                elif command -v google-chrome >/dev/null 2>&1; then
                    google-chrome --new-tab "$desktop_url" >/dev/null 2>&1 &
                elif command -v chromium-browser >/dev/null 2>&1; then
                    chromium-browser --new-tab "$desktop_url" >/dev/null 2>&1 &
                elif command -v firefox >/dev/null 2>&1; then
                    firefox --new-tab "$desktop_url" >/dev/null 2>&1 &
                fi
                echo -e "${GREEN}   ✅ Desktop access opened in browser${NC}"
                echo -e "${GREEN}   🔗 Manual URL: $desktop_url${NC}"
                echo -e "${GREEN}   🔐 VNC Password: autobot${NC}"
            fi
        else
            echo -e "${RED}❌ Failed to setup desktop access${NC}"
        fi
        echo
    fi
    
    # Show final status
    echo -e "${GREEN}🎉 AutoBot is now ready!${NC}"
    echo -e "${GREEN}========================${NC}"
    echo -e "${GREEN}   🌐 Web Interface: http://localhost:${FRONTEND_PORT:-5173}${NC}"
    echo -e "${GREEN}   🔧 Backend API: http://localhost:${API_PORT:-8001}${NC}"
    if [ "$DESKTOP_ACCESS" = "true" ]; then
        echo -e "${GREEN}   🖥️  Desktop Access: http://localhost:6080/vnc.html?autoconnect=true&password=autobot${NC}"
        echo -e "${YELLOW}   🔐 VNC Password: autobot${NC}"
    fi
    echo -e "${GREEN}   📚 Redis Insight: http://localhost:${REDISINSIGHT_PORT:-8002}${NC}"
    echo ""
    echo -e "${YELLOW}💡 Quick Start:${NC}"
    echo -e "   • Open the web interface and start chatting with AutoBot"
    echo -e "   • Try: 'Hello AutoBot, what can you help me with?'"
    echo -e "   • Access desktop tools via VNC for advanced tasks"
    echo ""
    
    # Keep running and show logs
    echo -e "${GREEN}📋 Following logs (Ctrl+C to stop)...${NC}"
    $compose_cmd -f $COMPOSE_FILE logs -f
}

# Run main function
main