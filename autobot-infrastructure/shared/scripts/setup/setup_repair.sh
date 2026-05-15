#!/bin/bash

# AutoBot Setup & Repair Script
# Comprehensive setup with intelligent repair capabilities

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Script directory (project root)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Default options
REPAIR_MODE=false
CHECK_ONLY=false
FORCE_RECREATE=false
UPDATE_DEPS=false
VERBOSE=false
FIX_PERMISSIONS=false

# Parse command line arguments
print_usage() {
    echo "Usage: $0 [OPTIONS]"
    echo ""
    echo "Options:"
    echo "  --repair          Repair mode: fix broken containers and dependencies"
    echo "  --check           Check only: diagnose issues without fixing"
    echo "  --force-recreate  Force recreate all containers"
    echo "  --update-deps     Update all dependencies to latest versions"
    echo "  --fix-permissions Fix file and docker permissions"
    echo "  --verbose         Show detailed output"
    echo "  --help            Show this help message"
    echo ""
    echo "Examples:"
    echo "  $0 --repair       # Fix any issues found"
    echo "  $0 --check        # Diagnose without changes"
    echo "  $0 --repair --update-deps  # Repair and update dependencies"
}

while [[ $# -gt 0 ]]; do
    case $1 in
        --repair)
            REPAIR_MODE=true
            shift
            ;;
        --check)
            CHECK_ONLY=true
            shift
            ;;
        --force-recreate)
            FORCE_RECREATE=true
            shift
            ;;
        --update-deps)
            UPDATE_DEPS=true
            shift
            ;;
        --fix-permissions)
            FIX_PERMISSIONS=true
            shift
            ;;
        --verbose)
            VERBOSE=true
            shift
            ;;
        --help)
            print_usage
            exit 0
            ;;
        *)
            echo -e "${RED}Unknown option: $1${NC}"
            print_usage
            exit 1
            ;;
    esac
done

# Logging functions
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[✓]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[!]${NC} $1"
}

log_error() {
    echo -e "${RED}[✗]${NC} $1"
}

log_verbose() {
    if [ "$VERBOSE" = true ]; then
        echo -e "${PURPLE}[DEBUG]${NC} $1"
    fi
}

# Health check results
declare -A HEALTH_STATUS
declare -A ISSUES_FOUND

# Function to check Docker installation and daemon
check_docker() {
    log_info "Checking Docker installation..."

    if ! command -v docker &> /dev/null; then
        log_error "Docker is not installed"
        ISSUES_FOUND["docker_missing"]=true
        return 1
    fi

    if ! docker info &> /dev/null; then
        log_error "Docker daemon is not running"
        ISSUES_FOUND["docker_not_running"]=true
        return 1
    fi

    # Check docker-compose
    if command -v docker-compose &> /dev/null; then
        COMPOSE_CMD="docker-compose"
    elif docker compose version &> /dev/null 2>&1; then
        COMPOSE_CMD="docker compose"
    else
        log_error "Docker Compose is not installed"
        ISSUES_FOUND["compose_missing"]=true
        return 1
    fi

    log_success "Docker and Docker Compose are properly installed"
    return 0
}

# Function to check container health
check_container_health() {
    local container_name=$1
    local health_endpoint=$2
    local port=$3

    log_verbose "Checking container: $container_name"

    # Check if container exists
    if ! docker ps -a --format '{{.Names}}' | grep -q "^${container_name}$"; then
        log_warning "Container '$container_name' does not exist"
        HEALTH_STATUS[$container_name]="missing"
        return 1
    fi

    # Check if container is running
    if ! docker ps --format '{{.Names}}' | grep -q "^${container_name}$"; then
        log_warning "Container '$container_name' exists but is not running"
        HEALTH_STATUS[$container_name]="stopped"
        return 1
    fi

    # Check container health status
    local health_status=$(docker inspect --format='{{.State.Health.Status}}' "$container_name" 2>/dev/null || echo "none")
    if [ "$health_status" = "unhealthy" ]; then
        log_warning "Container '$container_name' is unhealthy"
        HEALTH_STATUS[$container_name]="unhealthy"
        return 1
    fi

    # Check if port is accessible
    if [ -n "$port" ]; then
        if ! nc -z localhost "$port" &> /dev/null; then
            log_warning "Container '$container_name' port $port is not accessible"
            HEALTH_STATUS[$container_name]="port_issue"
            return 1
        fi
    fi

    # Check HTTP endpoint if provided
    if [ -n "$health_endpoint" ]; then
        if ! curl -sf "$health_endpoint" &> /dev/null; then
            log_warning "Container '$container_name' health endpoint is not responding"
            HEALTH_STATUS[$container_name]="endpoint_issue"
            return 1
        fi
    fi

    log_success "Container '$container_name' is healthy"
    HEALTH_STATUS[$container_name]="healthy"
    return 0
}

# Function to repair container
repair_container() {
    local container_name=$1
    local compose_service=$2
    local compose_file=$3

    log_info "Repairing container: $container_name"

    case ${HEALTH_STATUS[$container_name]} in
        "missing")
            log_info "Creating missing container..."
            if [ -n "$compose_file" ] && [ -n "$compose_service" ]; then
                $COMPOSE_CMD -f "$compose_file" up -d "$compose_service"
            else
                log_error "Cannot create container - no compose configuration"
                return 1
            fi
            ;;
        "stopped")
            log_info "Starting stopped container..."
            docker start "$container_name"
            ;;
        "unhealthy"|"port_issue"|"endpoint_issue")
            log_info "Recreating unhealthy container..."
            docker stop "$container_name" &> /dev/null
            docker rm "$container_name" &> /dev/null
            if [ -n "$compose_file" ] && [ -n "$compose_service" ]; then
                $COMPOSE_CMD -f "$compose_file" up -d "$compose_service"
            fi
            ;;
    esac

    # Wait for container to be ready
    sleep 5
    return 0
}

# Function to check Python environment
check_python_env() {
    log_info "Checking Python environment..."

    # Check Python version
    if ! command -v python3 &> /dev/null; then
        log_error "Python 3 is not installed"
        ISSUES_FOUND["python_missing"]=true
        return 1
    fi

    local python_version=$(python3 --version | cut -d' ' -f2)
    log_verbose "Python version: $python_version"

    # Check virtual environment
    if [ ! -d "venv" ]; then
        log_warning "Virtual environment not found"
        ISSUES_FOUND["venv_missing"]=true
    else
        # Check if venv is activated
        if [ -z "$VIRTUAL_ENV" ]; then
            log_warning "Virtual environment exists but is not activated"
            ISSUES_FOUND["venv_not_active"]=true
        fi
    fi

    # Check requirements
    if [ -f "requirements.txt" ]; then
        if [ "$UPDATE_DEPS" = true ] || [ ! -d "venv" ]; then
            ISSUES_FOUND["deps_need_update"]=true
        fi
    else
        log_error "requirements.txt not found"
        ISSUES_FOUND["requirements_missing"]=true
    fi

    return 0
}

# Function to check Node.js environment
check_node_env() {
    log_info "Checking Node.js environment..."

    # Check Node.js
    if ! command -v node &> /dev/null; then
        log_error "Node.js is not installed"
        ISSUES_FOUND["node_missing"]=true
        return 1
    fi

    local node_version=$(node --version)
    log_verbose "Node.js version: $node_version"

    # Check npm
    if ! command -v npm &> /dev/null; then
        log_error "npm is not installed"
        ISSUES_FOUND["npm_missing"]=true
        return 1
    fi

    # Check frontend dependencies
    if [ -d "autobot-slm-frontend" ]; then
        if [ ! -d "autobot-slm-frontend/node_modules" ]; then
            log_warning "Frontend dependencies not installed"
            ISSUES_FOUND["frontend_deps_missing"]=true
        elif [ "$UPDATE_DEPS" = true ]; then
            ISSUES_FOUND["frontend_deps_need_update"]=true
        fi
    fi

    return 0
}

# Function to check file permissions
check_permissions() {
    log_info "Checking file permissions..."

    # Check if user is in docker group
    if ! groups | grep -q docker; then
        log_warning "User is not in docker group"
        ISSUES_FOUND["docker_group_missing"]=true
    fi

    # Check script permissions
    local scripts=("run_agent.sh" "setup_agent.sh" "start_all_containers.sh")
    for script in "${scripts[@]}"; do
        if [ -f "$script" ] && [ ! -x "$script" ]; then
            log_warning "Script '$script' is not executable"
            ISSUES_FOUND["script_not_executable_$script"]=true
        fi
    done

    # Check critical directories
    local dirs=("data" "logs" "config")
    for dir in "${dirs[@]}"; do
        if [ -d "$dir" ] && [ ! -w "$dir" ]; then
            log_warning "Directory '$dir' is not writable"
            ISSUES_FOUND["dir_not_writable_$dir"]=true
        fi
    done

    return 0
}

# Function to check critical files
check_critical_files() {
    log_info "Checking critical files..."

    # Check playwright-server.js
    if [ ! -f "playwright-server.js" ]; then
        if [ -f "tests/playwright-server.js" ]; then
            log_warning "playwright-server.js missing from root (exists in tests/)"
            ISSUES_FOUND["playwright_server_missing"]=true
        else
            log_error "playwright-server.js not found anywhere"
            ISSUES_FOUND["playwright_server_not_found"]=true
        fi
    fi

    # Check config files
    if [ ! -f "config/config.yaml" ] && [ -f "config/config.yaml.template" ]; then
        log_warning "config.yaml missing (template exists)"
        ISSUES_FOUND["config_missing"]=true
    fi

    return 0
}

# Main diagnostic function
run_diagnostics() {
    echo -e "${CYAN}=== AutoBot System Diagnostics ===${NC}"
    echo ""

    # Check Docker
    check_docker

    # Check containers
    log_info "Checking container health..."
    check_container_health "autobot-redis" "" "6379"
    check_container_health "autobot-npu-worker" "http://localhost:8081/health" "8081"
    check_container_health "autobot-playwright" "http://localhost:3000/health" "3000"

    # Check environments
    check_python_env
    check_node_env

    # Check permissions
    check_permissions

    # Check critical files
    check_critical_files

    # Summary
    echo ""
    echo -e "${CYAN}=== Diagnostic Summary ===${NC}"

    local issue_count=${#ISSUES_FOUND[@]}
    if [ $issue_count -eq 0 ]; then
        log_success "No issues found! System is healthy."
    else
        log_warning "Found $issue_count issue(s) that need attention."

        if [ "$CHECK_ONLY" = true ]; then
            echo ""
            echo "Run with --repair to fix these issues automatically."
        fi
    fi
}

# Main repair function
run_repairs() {
    echo -e "${CYAN}=== AutoBot System Repair ===${NC}"
    echo ""

    # Fix Docker issues
    if [ "${ISSUES_FOUND[docker_not_running]}" = true ]; then
        log_info "Starting Docker daemon..."
        if command -v systemctl &> /dev/null; then
            sudo systemctl start docker
        else
            log_error "Cannot start Docker daemon automatically. Please start it manually."
        fi
    fi

    # Fix containers
    if [ "${HEALTH_STATUS[autobot-redis]}" != "healthy" ]; then
        repair_container "autobot-redis" "autobot-redis" "docker-compose.hybrid.yml"
    fi

    if [ "${HEALTH_STATUS[autobot-npu-worker]}" != "healthy" ]; then
        repair_container "autobot-npu-worker" "autobot-npu-worker" "docker-compose.hybrid.yml"
    fi

    if [ "${HEALTH_STATUS[autobot-playwright]}" != "healthy" ]; then
        # Special handling for Playwright
        if [ "${ISSUES_FOUND[playwright_server_missing]}" = true ]; then
            log_info "Copying playwright-server.js to root..."
            cp tests/playwright-server.js ./playwright-server.js
        fi
        repair_container "autobot-playwright" "playwright-service" "docker-compose.playwright.yml"
    fi

    # Fix Python environment
    if [ "${ISSUES_FOUND[venv_missing]}" = true ]; then
        log_info "Creating Python virtual environment..."
        python3 -m venv venv
    fi

    if [ "${ISSUES_FOUND[deps_need_update]}" = true ] || [ "${ISSUES_FOUND[venv_missing]}" = true ]; then
        log_info "Installing/updating Python dependencies..."
        source venv/bin/activate
        pip install --upgrade pip
        pip install -r requirements.txt
    fi

    # Fix Node.js environment
    if [ "${ISSUES_FOUND[frontend_deps_missing]}" = true ] || [ "${ISSUES_FOUND[frontend_deps_need_update]}" = true ]; then
        log_info "Installing/updating frontend dependencies..."
        cd autobot-slm-frontend
        npm install
        cd ..
    fi

    # Fix permissions
    if [ "$FIX_PERMISSIONS" = true ] || [ "${ISSUES_FOUND[docker_group_missing]}" = true ]; then
        log_info "Adding user to docker group..."
        sudo usermod -aG docker $USER
        log_warning "You need to log out and back in for docker group changes to take effect"
    fi

    # Fix script permissions
    for script in run_agent.sh setup_agent.sh start_all_containers.sh setup_repair.sh; do
        if [ -f "$script" ] && [ ! -x "$script" ]; then
            log_info "Making $script executable..."
            chmod +x "$script"
        fi
    done

    # Fix directory permissions
    for dir in data logs config; do
        if [ -d "$dir" ] && [ ! -w "$dir" ]; then
            log_info "Fixing permissions for $dir..."
            chmod -R u+w "$dir"
        fi
    done

    # Create missing directories
    for dir in data logs config; do
        if [ ! -d "$dir" ]; then
            log_info "Creating directory: $dir"
            mkdir -p "$dir"
        fi
    done

    # Fix config file
    if [ "${ISSUES_FOUND[config_missing]}" = true ]; then
        log_info "Creating config.yaml from template..."
        cp config/config.yaml.template config/config.yaml
    fi

    echo ""
    log_success "Repair process completed!"
}

# Force recreate all containers
force_recreate_containers() {
    echo -e "${CYAN}=== Force Recreating All Containers ===${NC}"
    echo ""

    log_warning "This will stop and recreate all containers. Data will be preserved."

    # Stop and remove containers
    local containers=("autobot-redis" "autobot-npu-worker" "autobot-playwright")
    for container in "${containers[@]}"; do
        if docker ps -a --format '{{.Names}}' | grep -q "^${container}$"; then
            log_info "Removing container: $container"
            docker stop "$container" &> /dev/null
            docker rm "$container" &> /dev/null
        fi
    done

    # Recreate using docker-compose
    log_info "Recreating containers..."
    $COMPOSE_CMD -f docker-compose.hybrid.yml up -d autobot-redis autobot-npu-worker
    $COMPOSE_CMD -f docker-compose.playwright.yml up -d playwright-service

    # Wait for containers to be ready
    sleep 10

    # Verify health
    check_container_health "autobot-redis" "" "6379"
    check_container_health "autobot-npu-worker" "http://localhost:8081/health" "8081"
    check_container_health "autobot-playwright" "http://localhost:3000/health" "3000"

    log_success "Container recreation completed!"
}

# Main execution
main() {
    echo -e "${PURPLE}"
    echo "    _         _        ____        _   "
    echo "   / \  _   _| |_ ___ | __ )  ___ | |_ "
    echo "  / _ \| | | | __/ _ \|  _ \ / _ \| __|"
    echo " / ___ \ |_| | || (_) | |_) | (_) | |_ "
    echo "/_/   \_\__,_|\__\___/|____/ \___/ \__|"
    echo -e "${NC}"
    echo "AutoBot Setup & Repair Utility v1.0"
    echo ""

    # Always run diagnostics first
    run_diagnostics

    # If check only mode, exit here
    if [ "$CHECK_ONLY" = true ]; then
        exit 0
    fi

    # If force recreate mode
    if [ "$FORCE_RECREATE" = true ]; then
        force_recreate_containers
        exit 0
    fi

    # If repair mode or issues found
    if [ "$REPAIR_MODE" = true ] || [ ${#ISSUES_FOUND[@]} -gt 0 ]; then
        if [ "$REPAIR_MODE" = false ]; then
            echo ""
            read -p "Issues found. Would you like to repair them? (y/n) " -n 1 -r
            echo ""
            if [[ ! $REPLY =~ ^[Yy]$ ]]; then
                exit 0
            fi
        fi

        run_repairs
    fi

    echo ""
    echo -e "${GREEN}Setup complete!${NC}"
    echo ""
    echo "To start AutoBot, run: ./run_agent.sh"
    echo "For more options, run: ./setup_repair.sh --help"
}

# Run main function
main
