#!/bin/bash
# AutoBot Quick Deployment Script
# This script provides easy deployment commands for different modes

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Print colored output
print_color() {
    local color=$1
    local message=$2
    echo -e "${color}${message}${NC}"
}

print_header() {
    echo
    print_color $BLUE "================================================"
    print_color $BLUE "  $1"
    print_color $BLUE "================================================"
}

print_success() {
    print_color $GREEN "✅ $1"
}

print_warning() {
    print_color $YELLOW "⚠️  $1"
}

print_error() {
    print_color $RED "❌ $1"
}

print_info() {
    print_color $BLUE "ℹ️  $1"
}

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Default values
MODE="local"
BUILD=false
CLEANUP=false
CONFIG=""
NAMESPACE="autobot"

# Help function
show_help() {
    echo "AutoBot Deployment Script"
    echo
    echo "Usage: $0 [OPTIONS]"
    echo
    echo "Options:"
    echo "  -m, --mode MODE        Deployment mode (local|docker_local|distributed|kubernetes)"
    echo "  -c, --config FILE      Configuration file path"
    echo "  -n, --namespace NAME   Kubernetes namespace (default: autobot)"
    echo "  -b, --build            Build Docker images before deployment"
    echo "  -C, --cleanup          Clean up existing deployment"
    echo "  -h, --help             Show this help message"
    echo
    echo "Examples:"
    echo "  $0                                    # Deploy in local mode (default)"
    echo "  $0 --mode docker_local --build       # Full Docker deployment with build"
    echo "  $0 --mode distributed --config production.yml"
    echo "  $0 --mode kubernetes --namespace prod --build"
    echo "  $0 --cleanup                         # Clean up deployment"
    echo
    echo "Deployment Modes:"
    echo "  local        - Hybrid: Docker services + host backend/frontend (default)"
    echo "  docker_local - Full Docker deployment on single machine"
    echo "  distributed  - Services across multiple machines"
    echo "  kubernetes   - Kubernetes cluster deployment"
}

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        -m|--mode)
            MODE="$2"
            shift 2
            ;;
        -c|--config)
            CONFIG="$2"
            shift 2
            ;;
        -n|--namespace)
            NAMESPACE="$2"
            shift 2
            ;;
        -b|--build)
            BUILD=true
            shift
            ;;
        -C|--cleanup)
            CLEANUP=true
            shift
            ;;
        -h|--help)
            show_help
            exit 0
            ;;
        *)
            print_error "Unknown option: $1"
            echo
            show_help
            exit 1
            ;;
    esac
done

# Validate mode
case $MODE in
    local|docker_local|distributed|kubernetes)
        # Valid mode
        ;;
    *)
        print_error "Invalid deployment mode: $MODE"
        echo "Valid modes: local, docker_local, distributed, kubernetes"
        exit 1
        ;;
esac

print_header "AutoBot Deployment"

# Show deployment info
print_info "Deployment Mode: $MODE"
if [[ -n "$CONFIG" ]]; then
    print_info "Config File: $CONFIG"
fi
if [[ "$MODE" == "kubernetes" ]]; then
    print_info "Namespace: $NAMESPACE"
fi
if [[ "$BUILD" == "true" ]]; then
    print_info "Build Images: Yes"
fi
if [[ "$CLEANUP" == "true" ]]; then
    print_info "Operation: Cleanup"
fi

# Check if Python script exists
DEPLOY_SCRIPT="$SCRIPT_DIR/scripts/deploy_autobot.py"
if [[ ! -f "$DEPLOY_SCRIPT" ]]; then
    print_error "Deployment script not found: $DEPLOY_SCRIPT"
    exit 1
fi

# Build command
DEPLOY_CMD="python3 $DEPLOY_SCRIPT --mode $MODE"

if [[ -n "$CONFIG" ]]; then
    DEPLOY_CMD="$DEPLOY_CMD --config $CONFIG"
fi

if [[ "$MODE" == "kubernetes" ]]; then
    DEPLOY_CMD="$DEPLOY_CMD --namespace $NAMESPACE"
fi

if [[ "$BUILD" == "true" ]]; then
    DEPLOY_CMD="$DEPLOY_CMD --build"
fi

if [[ "$CLEANUP" == "true" ]]; then
    DEPLOY_CMD="$DEPLOY_CMD --cleanup"
fi

# Run deployment
echo
print_info "Running: $DEPLOY_CMD"
echo

if python3 "$DEPLOY_SCRIPT" --mode "$MODE" \
    $([ -n "$CONFIG" ] && echo "--config $CONFIG") \
    $([ "$MODE" == "kubernetes" ] && echo "--namespace $NAMESPACE") \
    $([ "$BUILD" == "true" ] && echo "--build") \
    $([ "$CLEANUP" == "true" ] && echo "--cleanup"); then

    echo
    if [[ "$CLEANUP" == "true" ]]; then
        print_success "Cleanup completed successfully!"
    else
        print_success "Deployment completed successfully!"
        echo
        print_info "Next steps:"
        case $MODE in
            local)
                print_info "• Run './run_agent.sh' to start backend and frontend"
                print_info "• Access AutoBot at: http://localhost:3000"
                ;;
            docker_local)
                print_info "• All services are running in Docker"
                print_info "• Access AutoBot at: http://localhost:3000"
                ;;
            distributed)
                print_info "• Check service health: python -m src.utils.service_registry_cli health"
                print_info "• Configure remote services as needed"
                ;;
            kubernetes)
                print_info "• Check pods: kubectl get pods -n $NAMESPACE"
                print_info "• Port forward: kubectl port-forward -n $NAMESPACE service/autobot-backend-service 8001:8001"
                ;;
        esac

        echo
        print_info "Useful commands:"
        print_info "• Service status: python -m src.utils.service_registry_cli status"
        print_info "• Health check: python -m src.utils.service_registry_cli health"
        print_info "• Cleanup: $0 --cleanup --mode $MODE"
    fi

else
    echo
    print_error "Deployment failed!"
    exit 1
fi
