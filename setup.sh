#!/bin/bash
# AutoBot - Unified Setup Script
# Handles all setup tasks from initial deployment to environment configuration

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

print_usage() {
    echo -e "${GREEN}AutoBot - Unified Setup Script${NC}"
    echo "Handles all setup tasks from initial deployment to environment configuration"
    echo ""
    echo "Usage: $0 [setup_type] [options]"
    echo ""
    echo -e "${YELLOW}Setup Types:${NC}"
    echo "  initial         Complete initial deployment (default)"
    echo "  agent           Agent and environment setup only"
    echo "  system          System configuration (passwordless sudo, etc.)"
    echo "  knowledge       Knowledge base setup and population"
    echo "  docker          Docker volumes and configuration"
    echo "  models          Model sharing and Windows models setup"
    echo "  analytics       Seq analytics and authentication setup"
    echo "  network         DNS and network optimization setup"
    echo "  openvino        OpenVINO and NPU setup"
    echo "  desktop         VNC desktop environment setup for headless servers"
    echo "  repair          Repair existing installation"
    echo ""
    echo -e "${YELLOW}Environment Options:${NC}"
    echo "  --native-vm     Setup for native VM deployment (default)"
    echo "  --docker        Setup for Docker deployment"
    echo "  --wsl          Setup for WSL environment"
    echo ""
    echo -e "${YELLOW}General Options:${NC}"
    echo "  --force         Force setup even if already configured"
    echo "  --skip-deps     Skip dependency installation"
    echo "  --help          Show this help"
    echo ""
    echo -e "${BLUE}Examples:${NC}"
    echo "  $0                          # Complete initial setup (native VM)"
    echo "  $0 agent                    # Setup agent environment only"
    echo "  $0 knowledge --force        # Force knowledge base re-setup"
    echo "  $0 initial --docker         # Initial setup for Docker deployment"
}

# Default options
SETUP_TYPE="initial"
DEPLOYMENT_MODE="native-vm"
FORCE_SETUP=false
SKIP_DEPS=false

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        initial|agent|system|knowledge|docker|models|analytics|network|openvino|desktop|repair)
            SETUP_TYPE="$1"
            shift
            ;;
        --native-vm)
            DEPLOYMENT_MODE="native-vm"
            shift
            ;;
        --docker)
            DEPLOYMENT_MODE="docker"
            shift
            ;;
        --wsl)
            DEPLOYMENT_MODE="wsl"
            shift
            ;;
        --force)
            FORCE_SETUP=true
            shift
            ;;
        --skip-deps)
            SKIP_DEPS=true
            shift
            ;;
        --help|-h)
            print_usage
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            print_usage
            exit 1
            ;;
    esac
done

run_setup_script() {
    local script_path="$1"
    local description="$2"
    
    if [ -f "$script_path" ]; then
        echo -e "${CYAN}🔧 $description...${NC}"
        if [ "${script_path##*.}" = "py" ]; then
            python3 "$script_path"
        else
            bash "$script_path"
        fi
    else
        echo -e "${YELLOW}⚠️  Setup script not found: $script_path${NC}"
    fi
}

run_initial_setup() {
    echo -e "${GREEN}🚀 AutoBot Initial Setup - $DEPLOYMENT_MODE Deployment${NC}"
    echo -e "${BLUE}================================================${NC}"
    
    # System setup
    run_setup_script "scripts/setup/system/deploy.sh" "Running initial deployment"
    run_setup_script "scripts/setup/system/setup_passwordless_sudo.sh" "Setting up passwordless sudo"
    
    # Agent setup
    run_setup_script "scripts/setup/setup_agent.sh" "Setting up AutoBot agent"
    
    # Environment setup
    case "$DEPLOYMENT_MODE" in
        "docker")
            run_setup_script "scripts/setup/docker/setup_docker_volumes.sh" "Setting up Docker volumes"
            ;;
        "native-vm")
            echo -e "${BLUE}ℹ️  Native VM deployment selected${NC}"
            ;;
        "wsl")
            echo -e "${BLUE}ℹ️  WSL deployment selected${NC}"
            ;;
    esac
    
    # Knowledge base setup
    run_setup_script "scripts/setup/knowledge/fresh_kb_setup.py" "Setting up knowledge base"
    
    # Analytics setup
    run_setup_script "scripts/setup/analytics/seq_auth_setup.py" "Setting up Seq authentication"
    run_setup_script "scripts/setup/analytics/setup_seq_analytics.py" "Setting up Seq analytics"
    
    echo -e "${GREEN}✅ Initial setup completed for $DEPLOYMENT_MODE deployment!${NC}"
}

# Main execution
echo -e "${GREEN}🔧 AutoBot Setup - $SETUP_TYPE${NC}"
echo -e "${BLUE}Deployment Mode: $DEPLOYMENT_MODE${NC}"
echo ""

case "$SETUP_TYPE" in
    "initial")
        run_initial_setup
        ;;
    "agent")
        run_setup_script "scripts/setup/setup_agent.sh" "Setting up AutoBot agent"
        ;;
    "system")
        run_setup_script "scripts/setup/system/deploy.sh" "Running system deployment"
        run_setup_script "scripts/setup/system/setup_passwordless_sudo.sh" "Setting up passwordless sudo"
        ;;
    "knowledge")
        run_setup_script "scripts/setup/knowledge/fresh_kb_setup.py" "Setting up knowledge base"
        ;;
    "docker")
        run_setup_script "scripts/setup/docker/setup_docker_volumes.sh" "Setting up Docker volumes"
        ;;
    "models")
        run_setup_script "scripts/setup/models/setup_model_sharing.sh" "Setting up model sharing"
        run_setup_script "scripts/setup/models/setup_windows_only_models.sh" "Setting up Windows models"
        ;;
    "analytics")
        run_setup_script "scripts/setup/analytics/seq_auth_setup.py" "Setting up Seq authentication"
        run_setup_script "scripts/setup/analytics/setup_seq_analytics.py" "Setting up Seq analytics"
        ;;
    "network")
        run_setup_script "scripts/network/bidirectional-dns-setup.sh" "Setting up bidirectional DNS"
        run_setup_script "scripts/network/setup-dns-optimization.sh" "Setting up DNS optimization"
        ;;
    "openvino")
        run_setup_script "scripts/setup/setup_openvino.sh" "Setting up OpenVINO"
        run_setup_script "scripts/utilities/verify_npu_setup.py" "Verifying NPU setup"
        ;;
    "desktop")
        run_setup_script "scripts/setup/install-vnc-headless.sh" "Setting up VNC desktop environment"
        ;;
    "repair")
        run_setup_script "scripts/setup/setup_repair.sh" "Running setup repair"
        ;;
    *)
        echo -e "${RED}❌ Unknown setup type: $SETUP_TYPE${NC}"
        print_usage
        exit 1
        ;;
esac

echo ""
echo -e "${GREEN}🎉 AutoBot $SETUP_TYPE setup completed!${NC}"

if [ "$SETUP_TYPE" = "initial" ]; then
    echo ""
    echo -e "${BLUE}📋 Next Steps:${NC}"
    echo -e "${CYAN}  1. Run: ${YELLOW}./run_autobot.sh${CYAN} to start AutoBot${NC}"
    echo -e "${CYAN}  2. For development: ${YELLOW}./run_autobot.sh --dev${NC}"
    echo -e "${CYAN}  3. Check status: ${YELLOW}./scripts/native-vm/status_autobot_native.sh${NC}"
fi