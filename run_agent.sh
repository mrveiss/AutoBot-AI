#!/bin/bash

# Script to run the AutoBot application with backend and frontend components

# Parse command line arguments
TEST_MODE=false
START_ALL_CONTAINERS=false
CENTRALIZED_LOGGING=false
REDIS_SEPARATION=false
DEFAULT_COMPOSE_FILE="docker/compose/docker-compose.hybrid.yml"

while [[ $# -gt 0 ]]; do
    case $1 in
        --test-mode)
            TEST_MODE=true
            shift
            ;;
        --all-containers)
            START_ALL_CONTAINERS=true
            shift
            ;;
        --centralized-logs)
            CENTRALIZED_LOGGING=true
            DEFAULT_COMPOSE_FILE="docker-compose.centralized-logs.yml"
            shift
            ;;
        --redis-separation)
            REDIS_SEPARATION=true
            shift
            ;;
        --compose-file)
            DEFAULT_COMPOSE_FILE="$2"
            shift 2
            ;;
        --help)
            echo "AutoBot Application Startup Script"
            echo "Usage: $0 [options]"
            echo ""
            echo "Options:"
            echo "  --test-mode           Run in test mode with additional checks"
            echo "  --all-containers      Start all containers (Redis, NPU, AI Stack, Playwright)"
            echo "  --centralized-logs    Use centralized logging architecture (ALL logs in one place)"
            echo "  --redis-separation    Enable Redis database separation (11 isolated databases)"
            echo "  --compose-file FILE   Use specific Docker Compose file"
            echo "  --help               Show this help message"
            echo ""
            echo "Architecture Options:"
            echo "  Default:              Standard hybrid mode (Docker + local processes)"
            echo "  --centralized-logs:   ELK stack logging with Fluentd collection"
            echo "  --redis-separation:   Isolated databases (main, knowledge, prompts, agents, etc.)"
            echo ""
            echo "Examples:"
            echo "  $0                              # Standard startup"
            echo "  $0 --test-mode                  # Test mode with validation"
            echo "  $0 --centralized-logs           # All logs go to single location"
            echo "  $0 --redis-separation           # Use separated Redis databases"
            echo "  $0 --all-containers --centralized-logs  # Full setup with centralized logging"
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            echo "Usage: $0 [--test-mode] [--all-containers] [--centralized-logs] [--redis-separation] [--help]"
            exit 1
            ;;
    esac
done

echo "Starting AutoBot application..."
echo "Configuration:"
echo "  Test Mode: $TEST_MODE"
echo "  All Containers: $START_ALL_CONTAINERS"
echo "  Centralized Logging: $CENTRALIZED_LOGGING"
echo "  Redis Separation: $REDIS_SEPARATION"
echo "  Compose File: $DEFAULT_COMPOSE_FILE"
echo ""

# Enhanced cleanup function with better signal handling
cleanup() {
    echo "Received signal. Terminating all processes..."

    # Kill processes by PID if they were started in background
    if [ ! -z "$BACKEND_PID" ]; then
        echo "Terminating backend process (PID: $BACKEND_PID)..."
        kill -TERM "$BACKEND_PID" 2>/dev/null
        sleep 1
        kill -9 "$BACKEND_PID" 2>/dev/null
    fi

    if [ ! -z "$FRONTEND_PID" ]; then
        echo "Terminating frontend process (PID: $FRONTEND_PID)..."
        kill -TERM "$FRONTEND_PID" 2>/dev/null
        sleep 1
        kill -9 "$FRONTEND_PID" 2>/dev/null
    fi

    # Ensure all processes listening on our ports are killed
    echo "Ensuring all processes on ports 8001 and 5173 are terminated..."
    for port in 8001 5173; do
        # Use sudo with lsof for more comprehensive process identification
        PIDS=$(sudo lsof -t -i :$port 2>/dev/null)
        if [ -n "$PIDS" ]; then
            echo "Killing processes on port $port: $PIDS"
            sudo kill -9 $PIDS 2>/dev/null
        fi
    done

    # Kill any remaining uvicorn processes
    echo "Killing any remaining uvicorn processes..."
    sudo pkill -f "uvicorn main:app" 2>/dev/null

    # Kill any remaining child processes of this script
    echo "Killing any remaining child processes of this script..."
    pkill -P $$ -f "npm run dev" 2>/dev/null
    # The above pkill for uvicorn should cover this, but keeping for robustness
    # pkill -P $$ -f "uvicorn" 2>/dev/null

    echo "All processes terminated."
    exit 0
}

# Trap multiple signals for robust cleanup
trap cleanup SIGINT SIGTERM SIGQUIT

# Enhanced port cleanup function
cleanup_port() {
    local port=$1
    local service_name=$2

    echo "Stopping any existing $service_name processes on port $port..."
    # Use sudo with lsof for more comprehensive process identification
    if sudo lsof -i :$port -t > /dev/null 2>&1; then
        # Attempt to kill processes associated with uvicorn specifically
        PIDS=$(sudo lsof -t -i :$port -sTCP:LISTEN 2>/dev/null | xargs -r ps -o pid,command | grep -E 'uvicorn main:app|python3 main.py' | awk '{print $1}')
        if [ -n "$PIDS" ]; then
            echo "Killing processes on port $port: $PIDS"
            sudo kill -9 $PIDS 2>/dev/null
        else
            # Fallback to killing any process on the port if not a uvicorn/python3 main.py process
            PIDS=$(sudo lsof -t -i :$port 2>/dev/null)
            if [ -n "$PIDS" ]; then
                echo "Killing non-uvicorn processes on port $port: $PIDS"
                sudo kill -9 $PIDS 2>/dev/null
            fi
        fi
        echo "$service_name processes on port $port terminated."
    else
        echo "No $service_name process found on port $port."
    fi
}

# Clean up ports before starting
cleanup_port 8001 "backend"
cleanup_port 5173 "frontend"


# Ensure user is in docker group and docker command is accessible
if ! id -nG "$USER" | grep -qw "docker"; then
    echo "Adding user '$USER' to the 'docker' group..."
    sudo usermod -aG docker "$USER" || { echo "❌ Failed to add user to docker group."; exit 1; }
    echo "✅ User '$USER' added to 'docker' group. Please log out and log back in for changes to take effect."
    echo "You may need to run 'newgrp docker' or restart your terminal for changes to apply immediately."
    exit 1 # Exit to prompt user to re-login
fi

# Start all required Docker containers (from docker-compose)
echo "Starting all required Docker containers..."

# Architecture-specific startup
if [ "$CENTRALIZED_LOGGING" = true ]; then
    echo "🚀 Starting AutoBot with CENTRALIZED LOGGING architecture..."
    echo "   All container logs will be collected in a single location"
    echo "   Log viewer available at http://localhost:5341"

    # Ensure log directories exist
    mkdir -p logs/autobot-centralized

    # Start centralized logging infrastructure first
    docker-compose -f "$DEFAULT_COMPOSE_FILE" up -d autobot-log-collector || {
        echo "❌ Failed to start log collector."
        exit 1
    }

    # Wait for log collector to be ready
    echo "⏳ Waiting for log collector to be ready..."
    sleep 5

    echo "✅ Centralized logging infrastructure started"

elif [ "$START_ALL_CONTAINERS" = true ]; then
    echo "🚀 Starting ALL containers (Redis, NPU, AI Stack, Playwright)..."
    ./scripts/deployment/start_all_containers.sh || {
        echo "❌ Failed to start all containers."
        exit 1
    }
else
    echo "📦 Starting essential containers only (Redis, NPU, Playwright)..."
fi

# Start Redis Stack with database separation support
echo "🔄 Starting Redis Stack..."

if [ "$REDIS_SEPARATION" = true ]; then
    echo "   Using Redis database separation (11 isolated databases)"
    echo "   Databases: main(0), knowledge(1), prompts(2), agents(3), metrics(4), cache(5), sessions(6), tasks(7), logs(8), temp(9), backup(10)"

    # Ensure Redis database configuration exists
    mkdir -p docker/volumes/config
    if [ ! -f "docker/volumes/config/redis-databases.yaml" ]; then
        echo "⚠️  Redis database configuration missing. Creating default configuration..."
        cat > docker/volumes/config/redis-databases.yaml << EOF
# Redis Database Separation Configuration
databases:
  main: 0           # Main application data
  knowledge: 1      # Knowledge base and documents
  prompts: 2        # Prompt templates and management
  agents: 3         # Agent communication
  metrics: 4        # Performance metrics
  cache: 5          # General caching
  sessions: 6       # User sessions
  tasks: 7          # Task management
  logs: 8           # Log data
  temp: 9           # Temporary data
  backup: 10        # Backup data
EOF
    fi
fi

if docker ps --format '{{.Names}}' | grep -q '^autobot-redis$'; then
    echo "✅ 'autobot-redis' container is already running."

    # Verify Redis database separation if enabled
    if [ "$REDIS_SEPARATION" = true ]; then
        echo "🔍 Verifying Redis database separation..."
        python -c "
from src.utils.redis_database_manager import redis_db_manager
try:
    if redis_db_manager.validate_database_separation():
        print('✅ Redis database separation validated')
    else:
        print('⚠️  Redis database separation validation failed')
except Exception as e:
    print(f'⚠️  Could not validate Redis separation: {e}')
" 2>/dev/null || echo "⚠️  Could not validate Redis separation (Python environment may not be ready)"
    fi

elif docker ps -a --format '{{.Names}}' | grep -q '^autobot-redis$'; then
    echo "🔄 Starting existing 'autobot-redis' container..."
    docker start autobot-redis || {
        echo "❌ Failed to start existing Redis container. Removing and recreating..."
        docker rm autobot-redis
        docker-compose -f "$DEFAULT_COMPOSE_FILE" up -d autobot-redis || {
            echo "❌ Failed to recreate Redis Stack container."
            exit 1
        }
    }
    echo "✅ 'autobot-redis' container started."
else
    docker-compose -f "$DEFAULT_COMPOSE_FILE" up -d autobot-redis || {
        echo "❌ Failed to start Redis Stack container via docker-compose."
        exit 1
    }
    echo "✅ 'autobot-redis' container started."
fi

# Start NPU Worker (optional but recommended for performance)
echo "🔄 Starting NPU Worker..."
if docker ps --format '{{.Names}}' | grep -q '^autobot-npu-worker$'; then
    echo "✅ 'autobot-npu-worker' container is already running."

    # Test NPU worker code search capabilities
    if [ "$TEST_MODE" = true ]; then
        echo "🧪 Testing NPU Worker code search capabilities..."
        python test_npu_worker.py 2>/dev/null && echo "✅ NPU Worker tests passed" || echo "⚠️  NPU Worker tests failed (continuing anyway)"
    fi

elif docker ps -a --format '{{.Names}}' | grep -q '^autobot-npu-worker$'; then
    echo "🔄 Starting existing 'autobot-npu-worker' container..."
    docker start autobot-npu-worker || {
        echo "⚠️  Warning: Failed to start existing NPU Worker. Continuing without NPU acceleration."
        # Don't exit - NPU worker is optional
    }
else
    docker-compose -f "$DEFAULT_COMPOSE_FILE" up -d autobot-npu-worker || {
        echo "⚠️  Warning: Failed to start NPU Worker container. Continuing without NPU acceleration."
        # Don't exit - NPU worker is optional
    }
fi

# Wait for containers to be ready
echo "⏳ Waiting for containers to be ready..."
sleep 5

# Check Redis health and database separation
echo "🔍 Checking Redis health..."
for i in {1..10}; do
    if docker exec autobot-redis redis-cli ping >/dev/null 2>&1; then
        echo "✅ Redis is ready."

        # Test Redis database separation if enabled
        if [ "$REDIS_SEPARATION" = true ]; then
            echo "🔍 Testing Redis database separation..."
            docker exec autobot-redis redis-cli -n 0 set "test_main" "main_db" >/dev/null 2>&1
            docker exec autobot-redis redis-cli -n 1 set "test_knowledge" "knowledge_db" >/dev/null 2>&1
            docker exec autobot-redis redis-cli -n 2 set "test_prompts" "prompts_db" >/dev/null 2>&1

            MAIN_VAL=$(docker exec autobot-redis redis-cli -n 0 get "test_main" 2>/dev/null)
            KNOWLEDGE_VAL=$(docker exec autobot-redis redis-cli -n 1 get "test_knowledge" 2>/dev/null)
            PROMPTS_VAL=$(docker exec autobot-redis redis-cli -n 2 get "test_prompts" 2>/dev/null)

            if [ "$MAIN_VAL" = "main_db" ] && [ "$KNOWLEDGE_VAL" = "knowledge_db" ] && [ "$PROMPTS_VAL" = "prompts_db" ]; then
                echo "✅ Redis database separation working correctly"
                # Clean up test data
                docker exec autobot-redis redis-cli -n 0 del "test_main" >/dev/null 2>&1
                docker exec autobot-redis redis-cli -n 1 del "test_knowledge" >/dev/null 2>&1
                docker exec autobot-redis redis-cli -n 2 del "test_prompts" >/dev/null 2>&1
            else
                echo "⚠️  Redis database separation test failed - databases may not be isolated"
            fi
        fi
        break
    fi
    echo "⏳ Waiting for Redis... (attempt $i/10)"
    sleep 2
done

# Check NPU Worker health (if running)
if docker ps --format '{{.Names}}' | grep -q '^autobot-npu-worker$'; then
    echo "🔍 Checking NPU Worker health..."
    for i in {1..10}; do
        if curl -sf http://localhost:8081/health >/dev/null 2>&1; then
            echo "✅ NPU Worker is ready."
            break
        fi
        echo "⏳ Waiting for NPU Worker... (attempt $i/10)"
        sleep 2
    done
fi

# Start Playwright Service Docker container
echo "Starting Playwright Service Docker container..."

# Ensure playwright-server.js exists and is a file
if [ ! -f "/home/kali/Desktop/AutoBot/playwright-server.js" ]; then
    echo "⚠️  playwright-server.js not found in project root. Checking for it..."
    if [ -f "/home/kali/Desktop/AutoBot/tests/playwright-server.js" ]; then
        echo "📋 Copying playwright-server.js from tests directory..."
        cp "/home/kali/Desktop/AutoBot/tests/playwright-server.js" "/home/kali/Desktop/AutoBot/playwright-server.js"
    else
        echo "❌ playwright-server.js not found. Playwright container cannot start."
        echo "   Please ensure playwright-server.js exists in the project root."
    fi
fi

# Check for Playwright container (either name)
PLAYWRIGHT_CONTAINER=""
if docker ps -a --format '{{.Names}}' | grep -q '^autobot-playwright-vnc$'; then
    PLAYWRIGHT_CONTAINER="autobot-playwright-vnc"
elif docker ps -a --format '{{.Names}}' | grep -q '^autobot-playwright$'; then
    PLAYWRIGHT_CONTAINER="autobot-playwright"
fi

if [ -n "$PLAYWRIGHT_CONTAINER" ]; then
    if docker inspect -f '{{.State.Running}}' "$PLAYWRIGHT_CONTAINER" | grep -q 'true'; then
        echo "✅ '$PLAYWRIGHT_CONTAINER' container is already running."
    else
        echo "🔄 '$PLAYWRIGHT_CONTAINER' container found but not running. Starting it..."
        docker start "$PLAYWRIGHT_CONTAINER" || {
            echo "❌ Failed to start '$PLAYWRIGHT_CONTAINER' container."
            echo "   This may be due to mount issues. Try removing and recreating the container:"
            echo "   docker rm $PLAYWRIGHT_CONTAINER"
            echo "   Then run setup_agent.sh again to recreate it."
            exit 1
        }
        echo "✅ '$PLAYWRIGHT_CONTAINER' container started."

        # Wait for service to be ready
        echo "⏳ Waiting for Playwright service to be ready..."
        for i in {1..15}; do
            if curl -sf http://localhost:3000/health > /dev/null 2>&1; then
                echo "✅ Playwright service is ready."
                break
            fi
            echo "⏳ Waiting for Playwright service... (attempt $i/15)"
            sleep 2
        done
    fi
else
    echo "❌ Playwright container not found. Please run setup_agent.sh to deploy it."
    echo "   Or manually start the VNC-enabled container with:"
    echo "   docker-compose -f docker/compose/docker-compose.playwright-vnc.yml up -d"
    exit 1
fi

# Start backend (FastAPI) in background using uvicorn
echo "Starting FastAPI backend on port 8001..."
uvicorn main:app --host 0.0.0.0 --port 8001 --log-level debug &
BACKEND_PID=$!

# Give backend time to start and bind to port
sleep 5 # Increased sleep to allow more time for startup

# Check if backend process is running
if ! ps -p $BACKEND_PID > /dev/null; then
  echo "Error: Backend process (PID: $BACKEND_PID) failed to start. Check logs for details."
  cleanup
  exit 1
fi

# Wait for backend to listen on port 8001
echo "Waiting for backend to listen on port 8001..."
TIMEOUT=120 # Increased timeout to 120 seconds
for i in $(seq 1 $TIMEOUT); do
    # Check if the uvicorn process is still running
    if ! ps -p $BACKEND_PID > /dev/null; then
        echo "Error: Backend process (PID: $BACKEND_PID) died unexpectedly."
        cleanup
        exit 1
    fi

    # Check if the port is listening
    if sudo netstat -tlnp | grep -q ":8001"; then
        echo "Backend is listening on port 8001."
        break
    fi

    if [ $i -eq $TIMEOUT ]; then
        echo "Error: Backend did not start listening on port 8001 within $TIMEOUT seconds."
        cleanup
        exit 1
    fi
    sleep 1
done

echo "Backend started successfully (PID: $BACKEND_PID)"

# Check for frontend server on port 5173
echo "Checking for Vite frontend server on port 5173..."
lsof -i :5173 -t | xargs kill -9 2>/dev/null
echo "Existing Vite server terminated."

# Start frontend (Vite with Vue)
echo "Starting Vite frontend server..."
echo "Cleaning frontend build artifacts and cache..."
rm -rf /home/kali/Desktop/AutoBot/autobot-vue/node_modules /home/kali/Desktop/AutoBot/autobot-vue/.vite
cd /home/kali/Desktop/AutoBot/autobot-vue && npm install --force && npm run build && npm run dev &
FRONTEND_PID=$!
cd /home/kali/Desktop/AutoBot

# Check if frontend started successfully
sleep 5
if ! ps -p $FRONTEND_PID > /dev/null; then
  echo "Error: Frontend failed to start. Check logs for details."
  cleanup
  exit 1
fi

echo "AutoBot application started."
echo "Backend available at http://localhost:8001/ (PID: $BACKEND_PID)"
echo "Frontend available at http://localhost:5173/ (PID: $FRONTEND_PID)"
echo ""
echo "🚀 Additional Services:"
if [ "$CENTRALIZED_LOGGING" = true ]; then
    echo "📊 Centralized Logs: http://localhost:5341 (Seq log viewer)"
    echo "🔍 Log Aggregator: http://localhost:9200 (Elasticsearch)"
    echo "📋 All logs location: ./logs/autobot-centralized/"
fi
if docker ps --format '{{.Names}}' | grep -q '^autobot-npu-worker$'; then
    echo "⚡ NPU Worker: http://localhost:8081 (Code search acceleration)"
fi
if [ "$REDIS_SEPARATION" = true ]; then
    echo "💾 Redis: localhost:6379 (11 separated databases)"
else
    echo "💾 Redis: localhost:6379"
fi
echo "🎭 Playwright: http://localhost:3000 (Browser automation)"
echo ""
echo "Press Ctrl+C to stop all processes."

# Wait for Ctrl+C
wait
