#!/bin/bash
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
################################################################################
# AutoBot Interactive Setup Wizard
#
# Purpose: Guide new users through AutoBot setup in < 30 minutes
# Usage: ./scripts/setup_wizard.sh
#
# Features:
# - Interactive menu-driven setup
# - Automated health checks
# - Clear VM count clarification (5 VMs)
# - Prerequisites verification
# - Step-by-step guidance
#
# Related Issue: #166 - Architecture Roadmap Phase 1 - Critical Fixes
################################################################################

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/lib/ssot-config.sh" 2>/dev/null || true

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
MAGENTA='\033[0;35m'
BOLD='\033[1m'
NC='\033[0m' # No Color

# Configuration
AUTOBOT_ROOT=$(cd "$(dirname "$0")/.." && pwd)
MAIN_HOST_IP="${AUTOBOT_BACKEND_HOST:-172.16.168.20}"
VM1_IP="${AUTOBOT_FRONTEND_HOST:-172.16.168.21}"
VM2_IP="${AUTOBOT_NPU_WORKER_HOST:-172.16.168.22}"
VM3_IP="${AUTOBOT_REDIS_HOST:-172.16.168.23}"
VM4_IP="${AUTOBOT_AI_STACK_HOST:-172.16.168.24}"
VM5_IP="${AUTOBOT_BROWSER_SERVICE_HOST:-172.16.168.25}"

# Logging functions
print_banner() {
    clear
    echo -e "${BLUE}"
    echo "╔═══════════════════════════════════════════════════════════════════════════╗"
    echo "║                                                                           ║"
    echo "║     █████╗ ██╗   ██╗████████╗ ██████╗ ██████╗  ██████╗ ████████╗         ║"
    echo "║    ██╔══██╗██║   ██║╚══██╔══╝██╔═══██╗██╔══██╗██╔═══██╗╚══██╔══╝         ║"
    echo "║    ███████║██║   ██║   ██║   ██║   ██║██████╔╝██║   ██║   ██║            ║"
    echo "║    ██╔══██║██║   ██║   ██║   ██║   ██║██╔══██╗██║   ██║   ██║            ║"
    echo "║    ██║  ██║╚██████╔╝   ██║   ╚██████╔╝██████╔╝╚██████╔╝   ██║            ║"
    echo "║    ╚═╝  ╚═╝ ╚═════╝    ╚═╝    ╚═════╝ ╚═════╝  ╚═════╝    ╚═╝            ║"
    echo "║                                                                           ║"
    echo "║              AI-Powered Automation Platform - Setup Wizard                ║"
    echo "║                                                                           ║"
    echo "╚═══════════════════════════════════════════════════════════════════════════╝"
    echo -e "${NC}"
    echo ""
}

print_step() {
    echo -e "${CYAN}[STEP]${NC} $1"
}

print_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[✓]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[✗]${NC} $1"
}

print_divider() {
    echo -e "${BLUE}────────────────────────────────────────────────────────────────────────────${NC}"
}

# Pause and wait for user
pause() {
    echo ""
    read -p "Press Enter to continue..."
}

# Ask yes/no question
ask_yes_no() {
    local prompt="$1"
    local default="${2:-y}"

    if [ "$default" = "y" ]; then
        prompt="$prompt [Y/n]: "
    else
        prompt="$prompt [y/N]: "
    fi

    read -p "$prompt" response
    response=${response:-$default}

    case "$response" in
        [yY][eE][sS]|[yY]) return 0 ;;
        *) return 1 ;;
    esac
}

# Show architecture overview
show_architecture() {
    print_divider
    echo -e "${BOLD}${MAGENTA}AutoBot Distributed Architecture - 5 VMs + 1 Host${NC}"
    print_divider
    echo ""
    echo -e "  ${CYAN}┌─────────────────────────────────────────────────────────────────┐${NC}"
    echo -e "  ${CYAN}│${NC}  ${BOLD}Main Host (WSL/Linux)${NC}         ${GREEN}${MAIN_HOST_IP}${NC}                   ${CYAN}│${NC}"
    echo -e "  ${CYAN}│${NC}  └── Backend API Server (FastAPI on port ${AUTOBOT_BACKEND_PORT:-8001})               ${CYAN}│${NC}"
    echo -e "  ${CYAN}│${NC}  └── VNC Desktop (noVNC on port ${AUTOBOT_VNC_PORT:-6080})                        ${CYAN}│${NC}"
    echo -e "  ${CYAN}├─────────────────────────────────────────────────────────────────┤${NC}"
    echo -e "  ${CYAN}│${NC}  ${BOLD}VM1 - Frontend${NC}                ${GREEN}${VM1_IP}${NC}                   ${CYAN}│${NC}"
    echo -e "  ${CYAN}│${NC}  └── Vue.js Web Interface (Vite on port ${AUTOBOT_FRONTEND_PORT:-5173})                ${CYAN}│${NC}"
    echo -e "  ${CYAN}├─────────────────────────────────────────────────────────────────┤${NC}"
    echo -e "  ${CYAN}│${NC}  ${BOLD}VM2 - NPU Worker${NC}              ${GREEN}${VM2_IP}${NC}                   ${CYAN}│${NC}"
    echo -e "  ${CYAN}│${NC}  └── Hardware AI Acceleration (Intel NPU/OpenVINO)           ${CYAN}│${NC}"
    echo -e "  ${CYAN}├─────────────────────────────────────────────────────────────────┤${NC}"
    echo -e "  ${CYAN}│${NC}  ${BOLD}VM3 - Redis${NC}                   ${GREEN}${VM3_IP}${NC}                   ${CYAN}│${NC}"
    echo -e "  ${CYAN}│${NC}  └── Redis Stack (Cache, Queues, Vector Search)              ${CYAN}│${NC}"
    echo -e "  ${CYAN}├─────────────────────────────────────────────────────────────────┤${NC}"
    echo -e "  ${CYAN}│${NC}  ${BOLD}VM4 - AI Stack${NC}                ${GREEN}${VM4_IP}${NC}                   ${CYAN}│${NC}"
    echo -e "  ${CYAN}│${NC}  └── AI Processing (Ollama, vLLM, Model Inference)           ${CYAN}│${NC}"
    echo -e "  ${CYAN}├─────────────────────────────────────────────────────────────────┤${NC}"
    echo -e "  ${CYAN}│${NC}  ${BOLD}VM5 - Browser${NC}                 ${GREEN}${VM5_IP}${NC}                   ${CYAN}│${NC}"
    echo -e "  ${CYAN}│${NC}  └── Web Automation (Playwright MCP Server)                  ${CYAN}│${NC}"
    echo -e "  ${CYAN}└─────────────────────────────────────────────────────────────────┘${NC}"
    echo ""
    echo -e "  ${YELLOW}Total: 1 Main Host + 5 Virtual Machines${NC}"
    echo ""
}

# Check prerequisites
check_prerequisites() {
    print_divider
    echo -e "${BOLD}Checking Prerequisites${NC}"
    print_divider
    echo ""

    local all_pass=true

    # Check Python
    print_step "Checking Python 3.10+..."
    if command -v python3 &> /dev/null; then
        local py_version=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
        if [ "$(echo "$py_version >= 3.10" | bc)" -eq 1 ]; then
            print_success "Python $py_version installed"
        else
            print_warning "Python $py_version found (3.10+ recommended)"
        fi
    else
        print_error "Python 3 not found"
        all_pass=false
    fi

    # Check Node.js
    print_step "Checking Node.js 18+..."
    if command -v node &> /dev/null; then
        local node_version=$(node -v | cut -d'v' -f2 | cut -d'.' -f1)
        if [ "$node_version" -ge 18 ]; then
            print_success "Node.js v$(node -v | cut -d'v' -f2) installed"
        else
            print_warning "Node.js v$(node -v | cut -d'v' -f2) found (18+ recommended)"
        fi
    else
        print_warning "Node.js not found (needed for frontend VM)"
    fi

    # Check Git
    print_step "Checking Git..."
    if command -v git &> /dev/null; then
        print_success "Git $(git --version | cut -d' ' -f3) installed"
    else
        print_error "Git not found"
        all_pass=false
    fi

    # Check SSH key
    print_step "Checking SSH key for VM access..."
    if [ -f "$HOME/.ssh/autobot_key" ]; then
        print_success "AutoBot SSH key found"
    else
        print_warning "AutoBot SSH key not found (will be generated during setup)"
    fi

    # Check if running from correct directory
    print_step "Checking AutoBot directory..."
    if [ -d "$AUTOBOT_ROOT/backend" ] && [ -d "$AUTOBOT_ROOT/autobot-vue" ]; then
        print_success "AutoBot directory structure valid"
    else
        print_error "Invalid AutoBot directory structure"
        all_pass=false
    fi

    echo ""

    if [ "$all_pass" = true ]; then
        print_success "All prerequisites met!"
        return 0
    else
        print_warning "Some prerequisites are missing"
        return 1
    fi
}

# Check VM connectivity
check_vm_connectivity() {
    print_divider
    echo -e "${BOLD}Checking VM Connectivity${NC}"
    print_divider
    echo ""

    local vms=(
        "Main Host:$MAIN_HOST_IP"
        "VM1 Frontend:$VM1_IP"
        "VM2 NPU Worker:$VM2_IP"
        "VM3 Redis:$VM3_IP"
        "VM4 AI Stack:$VM4_IP"
        "VM5 Browser:$VM5_IP"
    )

    local connected=0
    local total=${#vms[@]}

    for vm in "${vms[@]}"; do
        local name=$(echo "$vm" | cut -d':' -f1)
        local ip=$(echo "$vm" | cut -d':' -f2)

        print_step "Checking $name ($ip)..."

        if ping -c 1 -W 2 "$ip" &> /dev/null; then
            print_success "$name is reachable"
            ((connected++))
        else
            print_warning "$name is not reachable"
        fi
    done

    echo ""
    echo -e "  ${BOLD}Connectivity Summary: $connected/$total VMs reachable${NC}"

    if [ $connected -lt $total ]; then
        echo ""
        print_info "Some VMs are not reachable. You can still proceed with setup,"
        print_info "but ensure all VMs are running before starting AutoBot."
    fi

    return 0
}

# Run health checks
run_health_checks() {
    print_divider
    echo -e "${BOLD}Running Health Checks${NC}"
    print_divider
    echo ""

    # Check Backend API
    print_step "Checking Backend API (http://$MAIN_HOST_IP:8001/api/health)..."
    if curl -s --connect-timeout 5 "http://$MAIN_HOST_IP:8001/api/health" &> /dev/null; then
        print_success "Backend API is healthy"
    else
        print_warning "Backend API not responding (start with ./run_autobot.sh)"
    fi

    # Check Frontend
    print_step "Checking Frontend (http://$VM1_IP:5173)..."
    if curl -s --connect-timeout 5 "http://$VM1_IP:5173" &> /dev/null; then
        print_success "Frontend is healthy"
    else
        print_warning "Frontend not responding"
    fi

    # Check Redis
    print_step "Checking Redis ($VM3_IP:6379)..."
    if command -v redis-cli &> /dev/null; then
        if redis-cli -h "$VM3_IP" ping 2>/dev/null | grep -q PONG; then
            print_success "Redis is healthy"
        else
            print_warning "Redis not responding"
        fi
    else
        print_info "redis-cli not installed, skipping Redis check"
    fi

    # Check VNC Desktop
    print_step "Checking VNC Desktop (http://$MAIN_HOST_IP:6080)..."
    if curl -s --connect-timeout 5 "http://$MAIN_HOST_IP:6080" &> /dev/null; then
        print_success "VNC Desktop is healthy"
    else
        print_warning "VNC Desktop not responding"
    fi

    echo ""
}

# Show main menu
show_main_menu() {
    print_banner

    echo -e "${BOLD}Welcome to the AutoBot Setup Wizard!${NC}"
    echo ""
    echo "This wizard will guide you through setting up AutoBot, the AI-powered"
    echo "automation platform. The setup takes approximately 20-30 minutes."
    echo ""
    print_divider
    echo ""
    echo -e "${BOLD}Select an option:${NC}"
    echo ""
    echo "  1) ${GREEN}Full Setup${NC}        - Complete AutoBot installation (recommended)"
    echo "  2) ${CYAN}View Architecture${NC} - Understand the 5-VM architecture"
    echo "  3) ${CYAN}Prerequisites${NC}     - Check system requirements"
    echo "  4) ${CYAN}VM Connectivity${NC}   - Test network connectivity to VMs"
    echo "  5) ${CYAN}Health Check${NC}      - Verify running services"
    echo "  6) ${YELLOW}Backend Only${NC}     - Install only on main host (no VMs)"
    echo "  7) ${YELLOW}SSH Key Setup${NC}    - Generate/distribute SSH keys"
    echo "  8) ${YELLOW}Knowledge Base${NC}   - Setup knowledge base"
    echo "  9) ${MAGENTA}Documentation${NC}    - View setup documentation"
    echo "  0) ${RED}Exit${NC}             - Exit setup wizard"
    echo ""

    read -p "Enter your choice [1-9, 0]: " choice

    case $choice in
        1) run_full_setup ;;
        2) show_architecture; pause; show_main_menu ;;
        3) check_prerequisites; pause; show_main_menu ;;
        4) check_vm_connectivity; pause; show_main_menu ;;
        5) run_health_checks; pause; show_main_menu ;;
        6) run_backend_only_setup ;;
        7) run_ssh_key_setup ;;
        8) run_knowledge_base_setup ;;
        9) show_documentation; pause; show_main_menu ;;
        0) echo ""; print_info "Exiting setup wizard. Goodbye!"; exit 0 ;;
        *) print_error "Invalid choice"; pause; show_main_menu ;;
    esac
}

# Run full setup
run_full_setup() {
    print_banner
    echo -e "${BOLD}Full AutoBot Setup${NC}"
    print_divider
    echo ""

    # Show architecture first
    show_architecture
    pause

    # Check prerequisites
    if ! check_prerequisites; then
        echo ""
        if ! ask_yes_no "Some prerequisites are missing. Continue anyway?"; then
            show_main_menu
            return
        fi
    fi
    pause

    # Check VM connectivity
    check_vm_connectivity
    pause

    # Confirm setup
    echo ""
    print_divider
    echo -e "${BOLD}Ready to begin setup?${NC}"
    echo ""
    echo "This will:"
    echo "  • Install Python dependencies"
    echo "  • Setup Node.js for frontend"
    echo "  • Configure environment files"
    echo "  • Generate SSH keys for VM access"
    echo "  • Initialize databases"
    echo ""

    if ask_yes_no "Proceed with full setup?"; then
        echo ""
        print_step "Starting full setup..."

        # Run the actual setup script
        cd "$AUTOBOT_ROOT"
        bash setup.sh initial --distributed

        echo ""
        print_success "Setup complete!"
        print_divider
        echo ""
        echo -e "${BOLD}Next Steps:${NC}"
        echo "  1. Start AutoBot: ${GREEN}./run_autobot.sh --dev${NC}"
        echo "  2. Access the UI: ${CYAN}http://${VM1_IP}:${AUTOBOT_FRONTEND_PORT:-5173}${NC}"
        echo "  3. Access VNC:    ${CYAN}http://127.0.0.1:6080/vnc.html${NC}"
        echo ""
        echo "For help, run: ${CYAN}/help${NC} in the chat interface"
        echo ""
    else
        show_main_menu
    fi
}

# Run backend-only setup
run_backend_only_setup() {
    print_banner
    echo -e "${BOLD}Backend-Only Setup${NC}"
    print_divider
    echo ""

    echo "This will install AutoBot backend on the main host only."
    echo "Use this if you don't need the full distributed VM setup."
    echo ""

    if ask_yes_no "Proceed with backend-only setup?"; then
        cd "$AUTOBOT_ROOT"
        bash setup.sh backend-only

        print_success "Backend setup complete!"
        pause
    fi

    show_main_menu
}

# Run SSH key setup
run_ssh_key_setup() {
    print_banner
    echo -e "${BOLD}SSH Key Setup${NC}"
    print_divider
    echo ""

    echo "This will generate SSH keys for secure VM communication."
    echo ""

    if ask_yes_no "Generate SSH keys?"; then
        cd "$AUTOBOT_ROOT"
        bash setup.sh ssh-keys

        print_success "SSH key setup complete!"
        pause
    fi

    show_main_menu
}

# Run knowledge base setup
run_knowledge_base_setup() {
    print_banner
    echo -e "${BOLD}Knowledge Base Setup${NC}"
    print_divider
    echo ""

    echo "This will setup and populate the knowledge base."
    echo ""

    if ask_yes_no "Setup knowledge base?"; then
        cd "$AUTOBOT_ROOT"
        bash setup.sh knowledge

        print_success "Knowledge base setup complete!"
        pause
    fi

    show_main_menu
}

# Show documentation
show_documentation() {
    print_divider
    echo -e "${BOLD}AutoBot Documentation${NC}"
    print_divider
    echo ""
    echo -e "${CYAN}Key Documentation Files:${NC}"
    echo ""
    echo "  📖 Getting Started:      docs/GETTING_STARTED_COMPLETE.md"
    echo "  📖 Developer Guide:      docs/developer/PHASE_5_DEVELOPER_SETUP.md"
    echo "  📖 Architecture:         docs/architecture/VISUAL_ARCHITECTURE.md"
    echo "  📖 API Reference:        docs/api/COMPREHENSIVE_API_DOCUMENTATION.md"
    echo "  📖 System State:         docs/system-state.md"
    echo ""
    echo -e "${CYAN}Quick Commands:${NC}"
    echo ""
    echo "  • Start AutoBot:         ./run_autobot.sh --dev"
    echo "  • Stop AutoBot:          ./run_autobot.sh --stop"
    echo "  • Check Status:          ./run_autobot.sh --status"
    echo "  • View Logs:             tail -f logs/backend.log"
    echo ""
    echo -e "${CYAN}In-Chat Commands:${NC}"
    echo ""
    echo "  • /docs                  List documentation categories"
    echo "  • /docs <topic>          Search documentation"
    echo "  • /help                  Show available commands"
    echo "  • /status                Show system status"
    echo ""
}

# Entry point
main() {
    cd "$AUTOBOT_ROOT"
    show_main_menu
}

# Run main
main "$@"
