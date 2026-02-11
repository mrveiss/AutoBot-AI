#!/bin/bash
"""
AutoBot Comprehensive Monitoring Startup Script
Launches all monitoring components for the distributed system.
"""

# Set up script directory and paths
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
_PROJECT_ROOT="$SCRIPT_DIR"
while [ "$_PROJECT_ROOT" != "/" ] && [ ! -f "$_PROJECT_ROOT/.env" ]; do
    _PROJECT_ROOT="$(dirname "$_PROJECT_ROOT")"
done
source "$_PROJECT_ROOT/infrastructure/shared/scripts/lib/ssot-config.sh" 2>/dev/null || true
AUTOBOT_ROOT="$(dirname "$SCRIPT_DIR")"
LOGS_DIR="$AUTOBOT_ROOT/logs"
MONITORING_DIR="$AUTOBOT_ROOT/monitoring"

# Ensure log directories exist
mkdir -p "$LOGS_DIR"
mkdir -p "$LOGS_DIR/performance"
mkdir -p "$LOGS_DIR/ai_performance"
mkdir -p "$LOGS_DIR/apm"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${BLUE}🤖 AutoBot Comprehensive Monitoring System${NC}"
echo -e "${BLUE}=========================================${NC}"

# Function to print status messages
print_status() {
    echo -e "${GREEN}[$(date '+%H:%M:%S')] $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}[$(date '+%H:%M:%S')] $1${NC}"
}

print_error() {
    echo -e "${RED}[$(date '+%H:%M:%S')] $1${NC}"
}

# Function to check if a process is running
check_process() {
    pgrep -f "$1" > /dev/null 2>&1
}

# Function to check if Redis is accessible
check_redis() {
    python3 -c "
import redis
try:
    r = redis.Redis(host='${AUTOBOT_REDIS_HOST:-172.16.168.23}', port=${AUTOBOT_REDIS_PORT:-6379}, socket_timeout=3)
    r.ping()
    print('Redis connection successful')
    exit(0)
except Exception as e:
    print(f'Redis connection failed: {e}')
    exit(1)
" 2>/dev/null
}

# Function to check VM connectivity
check_vm_connectivity() {
    print_status "Checking VM connectivity..."

    VMS=("${AUTOBOT_FRONTEND_HOST:-172.16.168.21}" "${AUTOBOT_NPU_WORKER_HOST:-172.16.168.22}" "${AUTOBOT_REDIS_HOST:-172.16.168.23}" "${AUTOBOT_AI_STACK_HOST:-172.16.168.24}" "${AUTOBOT_BROWSER_SERVICE_HOST:-172.16.168.25}")
    VM_NAMES=("Frontend" "NPU-Worker" "Redis" "AI-Stack" "Browser")

    for i in "${!VMS[@]}"; do
        VM_IP="${VMS[$i]}"
        VM_NAME="${VM_NAMES[$i]}"

        if ping -c 1 -W 3 "$VM_IP" > /dev/null 2>&1; then
            print_status "✅ $VM_NAME ($VM_IP) - reachable"
        else
            print_warning "⚠️  $VM_NAME ($VM_IP) - unreachable"
        fi
    done
}

# Function to start individual monitoring component
start_monitoring_component() {
    local component="$1"
    local script="$2"
    local args="$3"
    local log_file="$LOGS_DIR/monitoring_${component}.log"

    if check_process "$script"; then
        print_warning "$component monitoring already running"
        return 0
    fi

    print_status "Starting $component monitoring..."
    cd "$MONITORING_DIR"
    nohup python3 "$script" $args > "$log_file" 2>&1 &

    # Give it a moment to start
    sleep 2

    if check_process "$script"; then
        print_status "✅ $component monitoring started (PID: $(pgrep -f "$script"))"
        echo "   Log: $log_file"
        return 0
    else
        print_error "❌ Failed to start $component monitoring"
        echo "   Check log: $log_file"
        return 1
    fi
}

# Function to stop monitoring components
stop_monitoring() {
    print_status "Stopping all monitoring components..."

    # Kill monitoring processes
    pkill -f "performance_monitor.py" 2>/dev/null
    pkill -f "ai_performance_analytics.py" 2>/dev/null
    pkill -f "business_intelligence_dashboard.py" 2>/dev/null
    pkill -f "advanced_apm_system.py" 2>/dev/null
    pkill -f "comprehensive_monitoring_controller.py" 2>/dev/null

    print_status "✅ All monitoring components stopped"
}

# Function to show monitoring status
show_status() {
    echo -e "${BLUE}📊 Monitoring System Status${NC}"
    echo "================================"

    # Check individual components
    components=(
        "performance_monitor.py:Performance Monitor"
        "ai_performance_analytics.py:AI Analytics"
        "business_intelligence_dashboard.py:BI Dashboard"
        "advanced_apm_system.py:APM System"
        "comprehensive_monitoring_controller.py:Controller"
    )

    for component in "${components[@]}"; do
        IFS=':' read -r script name <<< "$component"
        if check_process "$script"; then
            echo -e "  ✅ $name - ${GREEN}Running${NC} (PID: $(pgrep -f "$script"))"
        else
            echo -e "  ❌ $name - ${RED}Stopped${NC}"
        fi
    done

    echo ""
    echo "Redis Connection:"
    if check_redis; then
        echo -e "  ✅ Redis - ${GREEN}Connected${NC}"
    else
        echo -e "  ❌ Redis - ${RED}Disconnected${NC}"
    fi
}

# Function to start comprehensive monitoring
start_comprehensive_monitoring() {
    print_status "🚀 Starting AutoBot Comprehensive Monitoring..."

    # Check prerequisites
    print_status "Checking prerequisites..."

    # Check Redis connection
    if ! check_redis; then
        print_error "❌ Redis connection failed - monitoring requires Redis"
        print_warning "Please ensure Redis is running on ${AUTOBOT_REDIS_HOST:-172.16.168.23}:${AUTOBOT_REDIS_PORT:-6379}"
        exit 1
    fi
    print_status "✅ Redis connection verified"

    # Check VM connectivity
    check_vm_connectivity

    # Stop any existing monitoring
    stop_monitoring
    sleep 2

    # Start monitoring components
    print_status "Starting monitoring components..."

    # Start comprehensive controller (this manages all other components)
    cd "$MONITORING_DIR"
    python3 comprehensive_monitoring_controller.py --start &
    CONTROLLER_PID=$!

    print_status "✅ Comprehensive monitoring controller started (PID: $CONTROLLER_PID)"
    print_status "📊 Monitoring dashboard will be available in reports/performance/"

    # Set up signal handling for graceful shutdown
    trap 'print_status "Shutting down monitoring..."; kill $CONTROLLER_PID 2>/dev/null; stop_monitoring; exit 0' INT TERM

    # Wait for controller or handle shutdown
    wait $CONTROLLER_PID
}

# Function to generate instant report
generate_instant_report() {
    print_status "⚡ Generating instant monitoring report..."

    cd "$MONITORING_DIR"
    python3 comprehensive_monitoring_controller.py --instant-report

    print_status "📋 Report generated in reports/performance/"
}

# Function to start individual monitoring for testing
start_individual_monitoring() {
    print_status "🧪 Starting individual monitoring components for testing..."

    # Check Redis
    if ! check_redis; then
        print_error "❌ Redis connection failed"
        exit 1
    fi

    # Start components individually
    start_monitoring_component "Performance" "performance_monitor.py" "--interval 60"
    start_monitoring_component "AI Analytics" "ai_performance_analytics.py" "--test"
    start_monitoring_component "BI Dashboard" "business_intelligence_dashboard.py" "--generate"
    start_monitoring_component "APM System" "advanced_apm_system.py" "--monitor"

    print_status "✅ Individual monitoring components started"
    print_status "Use './start_monitoring.sh --status' to check status"
    print_status "Use './start_monitoring.sh --stop' to stop all components"
}

# Main script logic
case "${1:-}" in
    --start|start)
        start_comprehensive_monitoring
        ;;
    --stop|stop)
        stop_monitoring
        ;;
    --status|status)
        show_status
        ;;
    --report|report)
        generate_instant_report
        ;;
    --individual|individual)
        start_individual_monitoring
        ;;
    --connectivity|connectivity)
        check_vm_connectivity
        ;;
    --help|help|-h)
        echo "AutoBot Comprehensive Monitoring System"
        echo ""
        echo "Usage: $0 [OPTION]"
        echo ""
        echo "Options:"
        echo "  --start        Start comprehensive monitoring system"
        echo "  --stop         Stop all monitoring components"
        echo "  --status       Show monitoring system status"
        echo "  --report       Generate instant monitoring report"
        echo "  --individual   Start individual components for testing"
        echo "  --connectivity Check VM connectivity"
        echo "  --help         Show this help message"
        echo ""
        echo "Examples:"
        echo "  $0 --start                # Start monitoring"
        echo "  $0 --status               # Check status"
        echo "  $0 --report               # Generate instant report"
        echo ""
        ;;
    *)
        print_status "🚀 AutoBot Comprehensive Monitoring System"
        echo ""
        echo "Choose an option:"
        echo "  1) Start comprehensive monitoring"
        echo "  2) Check monitoring status"
        echo "  3) Generate instant report"
        echo "  4) Stop monitoring"
        echo "  5) Check VM connectivity"
        echo "  6) Start individual components (testing)"
        echo ""
        read -p "Enter choice [1-6]: " choice

        case $choice in
            1) start_comprehensive_monitoring ;;
            2) show_status ;;
            3) generate_instant_report ;;
            4) stop_monitoring ;;
            5) check_vm_connectivity ;;
            6) start_individual_monitoring ;;
            *) echo "Invalid choice" ;;
        esac
        ;;
esac
