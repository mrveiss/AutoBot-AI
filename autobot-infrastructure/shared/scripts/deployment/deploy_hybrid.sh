#!/bin/bash
# =============================================================================
# DEV/SANDBOX ONLY - This script assumes Docker containers.
# Production uses native deployments. See Ansible roles for equivalent.
# =============================================================================
# AutoBot Hybrid Deployment Script
# Manages local + container deployment

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../../../.." && pwd)"
COMPOSE_FILE="$PROJECT_ROOT/docker-compose.hybrid.yml"

# Functions
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

check_dependencies() {
    log_info "Checking dependencies..."

    # Check Docker
    if ! command -v docker &> /dev/null; then
        log_error "Docker not found. Please install Docker."
        exit 1
    fi

    # Check Docker Compose
    if ! command -v docker-compose &> /dev/null && ! docker compose version &> /dev/null; then
        log_error "Docker Compose not found. Please install Docker Compose."
        exit 1
    fi

    # Check if Docker daemon is running
    if ! docker info &> /dev/null; then
        log_error "Docker daemon is not running. Please start Docker."
        exit 1
    fi

    log_success "All dependencies available"
}

build_ai_container() {
    log_info "Building AI stack container..."

    cd "$PROJECT_ROOT"

    # Create build context
    if [ ! -f "docker/ai-stack/Dockerfile" ]; then
        log_error "AI stack Dockerfile not found"
        exit 1
    fi

    # Build container
    docker build -f docker/ai-stack/Dockerfile -t autobot-ai-stack:latest .

    log_success "AI stack container built successfully"
}

start_containers() {
    log_info "Starting container services..."

    cd "$PROJECT_ROOT"

    # Use docker-compose or docker compose based on availability
    if command -v docker-compose &> /dev/null; then
        COMPOSE_CMD="docker-compose"
    else
        COMPOSE_CMD="docker compose"
    fi

    # Start services
    $COMPOSE_CMD -f "$COMPOSE_FILE" up -d

    log_success "Container services started"
}

stop_containers() {
    log_info "Stopping container services..."

    cd "$PROJECT_ROOT"

    if command -v docker-compose &> /dev/null; then
        COMPOSE_CMD="docker-compose"
    else
        COMPOSE_CMD="docker compose"
    fi

    $COMPOSE_CMD -f "$COMPOSE_FILE" down

    log_success "Container services stopped"
}

check_container_health() {
    log_info "Checking container health..."

    # Wait for containers to be ready
    sleep 10

    # Check Redis
    if ! docker exec autobot-redis redis-cli ping &> /dev/null; then
        log_warning "Redis container not responding"
        return 1
    fi

    # Check AI stack
    if ! curl -f http://localhost:8080/health &> /dev/null; then
        log_warning "AI stack container not responding"
        return 1
    fi

    log_success "All containers healthy"
    return 0
}

check_local_setup() {
    log_info "Checking local AutoBot setup..."

    # Check if virtual environment exists
    if [ ! -d "$PROJECT_ROOT/venv" ]; then
        log_warning "Virtual environment not found. Run setup_agent.sh first."
        return 1
    fi

    # Check if main files exist
    if [ ! -f "$PROJECT_ROOT/src/orchestrator.py" ]; then
        log_error "Main orchestrator not found"
        return 1
    fi

    log_success "Local setup ready"
    return 0
}

show_status() {
    echo
    log_info "=== AutoBot Hybrid Deployment Status ==="
    echo

    # Container status
    echo "📦 Container Services:"
    if docker ps --format "table {{.Names}}\t{{.Status}}" | grep -E "(autobot-redis|autobot-ai-stack)"; then
        echo
    else
        echo "  No AutoBot containers running"
    fi

    # Health checks
    echo "🏥 Health Status:"

    # Redis health
    if docker exec autobot-redis redis-cli ping &> /dev/null; then
        echo "  ✅ Redis: Healthy"
    else
        echo "  ❌ Redis: Unhealthy"
    fi

    # AI stack health
    if curl -s -f http://localhost:8080/health &> /dev/null; then
        echo "  ✅ AI Stack: Healthy"

        # Get agent status
        echo "  🤖 AI Agents:"
        curl -s http://localhost:8080/agents | jq -r '.agents[].type' 2>/dev/null | sed 's/^/    - /' || echo "    Unable to fetch agent list"
    else
        echo "  ❌ AI Stack: Unhealthy"
    fi

    # Resource usage
    echo
    echo "💾 Resource Usage:"
    docker stats --no-stream --format "table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}" | grep autobot || echo "  No resource data available"

    echo
}

show_logs() {
    local service=$1

    if [ -z "$service" ]; then
        log_info "Available services: redis, ai-stack, all"
        return
    fi

    cd "$PROJECT_ROOT"

    if command -v docker-compose &> /dev/null; then
        COMPOSE_CMD="docker-compose"
    else
        COMPOSE_CMD="docker compose"
    fi

    case $service in
        "redis")
            $COMPOSE_CMD -f "$COMPOSE_FILE" logs autobot-redis
            ;;
        "ai-stack")
            $COMPOSE_CMD -f "$COMPOSE_FILE" logs autobot-ai-stack
            ;;
        "all")
            $COMPOSE_CMD -f "$COMPOSE_FILE" logs
            ;;
        *)
            log_error "Unknown service: $service"
            ;;
    esac
}

cleanup() {
    log_info "Cleaning up AutoBot hybrid deployment..."

    # Stop containers
    stop_containers

    # Remove containers and volumes (optional)
    read -p "Remove containers and volumes? (y/N): " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        cd "$PROJECT_ROOT"

        if command -v docker-compose &> /dev/null; then
            COMPOSE_CMD="docker-compose"
        else
            COMPOSE_CMD="docker compose"
        fi

        $COMPOSE_CMD -f "$COMPOSE_FILE" down -v --remove-orphans
        docker rmi autobot-ai-stack:latest 2>/dev/null || true

        log_success "Cleanup completed"
    fi
}

cleanup_port() {
    local port=$1
    local service_name=$2

    log_info "Stopping any existing $service_name on port $port..."
    if sudo lsof -i :"$port" -t > /dev/null 2>&1; then
        PIDS=$(sudo lsof -t -i :"$port" 2>/dev/null)
        if [ -n "$PIDS" ]; then
            sudo kill -9 $PIDS 2>/dev/null
        fi
    fi
}

run_all_signal_cleanup() {
    log_info "Shutting down all processes..."
    [ -n "$BACKEND_PID" ] && kill -TERM "$BACKEND_PID" 2>/dev/null
    [ -n "$FRONTEND_PID" ] && kill -TERM "$FRONTEND_PID" 2>/dev/null
    sleep 1
    [ -n "$BACKEND_PID" ] && kill -9 "$BACKEND_PID" 2>/dev/null
    [ -n "$FRONTEND_PID" ] && kill -9 "$FRONTEND_PID" 2>/dev/null
    for port in 8001 5173; do
        PIDS=$(sudo lsof -t -i :"$port" 2>/dev/null)
        [ -n "$PIDS" ] && sudo kill -9 $PIDS 2>/dev/null
    done
    exit 0
}

# Combined run: start containers + local backend + frontend (merged from run_hybrid.sh)
run_all() {
    trap run_all_signal_cleanup SIGINT SIGTERM SIGQUIT
    cleanup_port 8001 "backend"
    cleanup_port 5173 "frontend"

    start_containers
    log_info "Waiting for containers..."
    sleep 10
    check_container_health || log_warning "Some containers may not be ready"

    export AUTOBOT_DEPLOYMENT_MODE=hybrid
    export REDIS_HOST=localhost
    export AI_STACK_URL=http://localhost:8080

    log_info "Starting FastAPI backend on port 8001..."
    uvicorn main:app --host 0.0.0.0 --port 8001 --log-level info &
    BACKEND_PID=$!
    sleep 5

    if ! ps -p $BACKEND_PID > /dev/null; then
        log_error "Backend failed to start"
        run_all_signal_cleanup
    fi

    log_info "Starting Vue frontend..."
    cd "$PROJECT_ROOT/autobot-slm-frontend"
    npm run dev &
    FRONTEND_PID=$!
    cd "$PROJECT_ROOT"
    sleep 5

    if ! ps -p $FRONTEND_PID > /dev/null; then
        log_error "Frontend failed to start"
        run_all_signal_cleanup
    fi

    log_success "All services running!"
    echo "  Backend:  http://localhost:8001 (PID: $BACKEND_PID)"
    echo "  Frontend: http://localhost:5173 (PID: $FRONTEND_PID)"
    echo "Press Ctrl+C to stop."
    wait
}

show_help() {
    echo "AutoBot Hybrid Deployment Manager"
    echo
    echo "Usage: $0 [command]"
    echo
    echo "Commands:"
    echo "  start     - Start hybrid deployment (build + run containers)"
    echo "  run       - Start containers + local backend + frontend"
    echo "  stop      - Stop container services"
    echo "  restart   - Restart container services"
    echo "  status    - Show deployment status"
    echo "  logs      - Show service logs [redis|ai-stack|all]"
    echo "  build     - Build AI stack container"
    echo "  health    - Check container health"
    echo "  cleanup   - Stop and remove containers/volumes"
    echo "  help      - Show this help message"
    echo
    echo "Examples:"
    echo "  $0 start"
    echo "  $0 run"
    echo "  $0 logs ai-stack"
    echo "  $0 status"
}

# Main script logic
case "${1:-help}" in
    "start")
        check_dependencies
        check_local_setup
        build_ai_container
        start_containers

        log_info "Waiting for services to start..."
        sleep 15

        if check_container_health; then
            log_success "AutoBot hybrid deployment started successfully!"
            show_status
        else
            log_error "Some services failed to start properly"
            show_logs all
            exit 1
        fi
        ;;

    "run")
        check_dependencies
        run_all
        ;;

    "stop")
        stop_containers
        ;;

    "restart")
        stop_containers
        sleep 5
        start_containers
        ;;

    "status")
        show_status
        ;;

    "logs")
        show_logs "$2"
        ;;

    "build")
        check_dependencies
        build_ai_container
        ;;

    "health")
        check_container_health
        ;;

    "cleanup")
        cleanup
        ;;

    "help"|*)
        show_help
        ;;
esac
