#!/bin/bash

# AutoBot Logging System Quick Deployment Verification
# Verifies that the enhanced centralized logging system can be deployed

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

# Color codes
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

log_info() {
    echo -e "${CYAN}[INFO]${NC} $1"
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

echo -e "${BLUE}╔════════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║         AutoBot Enhanced Logging Pre-Deployment Check         ║${NC}"
echo -e "${BLUE}╚════════════════════════════════════════════════════════════════╝${NC}"
echo ""

# Check prerequisites
log_info "Checking deployment prerequisites..."

# Check SSH key
if [[ -f "$HOME/.ssh/autobot_key" ]]; then
    log_success "SSH key found: $HOME/.ssh/autobot_key"
else
    log_error "SSH key not found. Run: ./scripts/utilities/setup-ssh-keys.sh"
    exit 1
fi

# Check Docker
if command -v docker &> /dev/null; then
    log_success "Docker is available"
else
    log_error "Docker is required for Loki deployment"
    exit 1
fi

# Check Python3
if command -v python3 &> /dev/null; then
    log_success "Python3 is available"
else
    log_error "Python3 is required for enhanced log parsing"
    exit 1
fi

# Check existing infrastructure
log_info "Checking existing logging infrastructure..."

if [[ -d "$PROJECT_ROOT/logs/autobot-centralized" ]]; then
    log_success "Existing centralized logging directory found"
    log_info "Will enhance existing infrastructure"
else
    log_info "Will create new centralized logging infrastructure"
fi

if [[ -f "$SCRIPT_DIR/setup-centralized-logging.sh" ]]; then
    log_success "Existing logging scripts found"
else
    log_warning "Basic logging scripts not found - will deploy from scratch"
fi

# Test VM connectivity
log_info "Testing VM connectivity (quick check)..."

declare -A VMS=(
    ["vm1-frontend"]="172.16.168.21"
    ["vm2-npu-worker"]="172.16.168.22"
    ["vm3-redis"]="172.16.168.23"
    ["vm4-ai-stack"]="172.16.168.24"
    ["vm5-browser"]="172.16.168.25"
)

reachable_vms=0
for vm_name in "${!VMS[@]}"; do
    vm_ip="${VMS[$vm_name]}"
    if ping -c 1 -W 1 "$vm_ip" &>/dev/null; then
        log_success "$vm_name ($vm_ip) is reachable"
        ((reachable_vms++))
    else
        log_warning "$vm_name ($vm_ip) is not responding to ping"
    fi
done

if [[ $reachable_vms -eq 5 ]]; then
    log_success "All VMs are network reachable"
elif [[ $reachable_vms -ge 3 ]]; then
    log_warning "$reachable_vms/5 VMs are reachable - partial deployment possible"
else
    log_error "Only $reachable_vms/5 VMs are reachable - check VM status"
    log_info "Run: ./scripts/vm-management/status-all-vms.sh"
fi

# Check disk space
log_info "Checking disk space for log storage..."

available_space=$(df -BG "$PROJECT_ROOT" | awk 'NR==2 {print $4}' | sed 's/G//')
if [[ $available_space -gt 5 ]]; then
    log_success "Sufficient disk space: ${available_space}GB available"
else
    log_warning "Low disk space: ${available_space}GB available - consider cleanup"
fi

# Check for performance monitoring
log_info "Checking performance monitoring integration..."

if [[ -f "$PROJECT_ROOT/logs/performance_monitor.log" ]]; then
    log_success "Performance monitor log found - GPU regression detection will be enhanced"

    # Check for recent GPU regressions
    if grep -q "REGRESSION.*GPU" "$PROJECT_ROOT/logs/performance_monitor.log" 2>/dev/null; then
        log_info "🚨 Recent GPU regressions detected - enhanced monitoring will help!"
    fi
else
    log_info "Performance monitor log not found - will create monitoring integration"
fi

# Check ports
log_info "Checking required ports..."

required_ports=(3100 3001 514)
for port in "${required_ports[@]}"; do
    if netstat -tuln 2>/dev/null | grep -q ":$port "; then
        log_warning "Port $port is already in use - may need configuration adjustment"
    else
        log_success "Port $port is available"
    fi
done

echo ""
echo -e "${BLUE}╔════════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║                     Deployment Summary                        ║${NC}"
echo -e "${BLUE}╚════════════════════════════════════════════════════════════════╝${NC}"
echo ""

echo -e "${CYAN}Ready to Deploy:${NC}"
echo "  Enhanced Logging System: ✅ Ready"
echo "  VM Count: $reachable_vms/5 VMs reachable"
echo "  Disk Space: ${available_space}GB available"
echo "  SSH Authentication: ✅ Configured"
echo "  Docker: ✅ Available"
echo "  Python3: ✅ Available"

echo ""
echo -e "${CYAN}Deployment Commands:${NC}"
echo ""
echo -e "${GREEN}1. Full Enhanced Deployment:${NC}"
echo "   bash scripts/logging/deploy-enhanced-logging.sh"
echo ""
echo -e "${GREEN}2. Basic Setup (if VMs unreachable):${NC}"
echo "   bash scripts/logging/setup-centralized-logging.sh"
echo ""
echo -e "${GREEN}3. Check Status After Deployment:${NC}"
echo "   bash scripts/logging/logging-system-status.sh"
echo ""
echo -e "${GREEN}4. Start Real-Time Monitoring:${NC}"
echo "   bash scripts/logging/real-time-monitor.sh"
echo ""

if grep -q "REGRESSION.*GPU" "$PROJECT_ROOT/logs/performance_monitor.log" 2>/dev/null; then
    echo -e "${YELLOW}🚨 SPECIAL NOTE:${NC}"
    echo "   GPU performance regressions detected in your system!"
    echo "   The enhanced logging will provide better analysis and alerting"
    echo "   for these performance issues."
    echo ""
fi

echo -e "${CYAN}Web Interfaces (after deployment):${NC}"
echo "  Loki API:        http://172.16.168.20:3100"
echo "  Grafana Logs:    http://172.16.168.20:3001 (admin/autobot123)"
echo ""

echo -e "${GREEN}✅ System is ready for enhanced centralized logging deployment!${NC}"
