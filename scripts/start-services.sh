#!/bin/bash
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
#
# Simple service management wrapper for AutoBot
# This is a convenience CLI wrapper around systemctl
#
# For full control, use:
#   - SLM GUI: https://172.16.168.19/orchestration
#   - systemctl commands directly

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Services
BACKEND_SERVICE="autobot-backend"
CELERY_SERVICE="autobot-celery"
REDIS_SERVICE="redis-stack-server"
OLLAMA_SERVICE="ollama"

show_usage() {
    cat << EOF
${GREEN}AutoBot Service Management${NC}

Usage: $0 <command> [service]

Commands:
  start [service]    Start service(s)
  stop [service]     Stop service(s)
  restart [service]  Restart service(s)
  status [service]   Show service status
  logs [service]     Show service logs (follow mode)
  gui                Open SLM orchestration GUI

Services:
  backend            AutoBot backend API
  celery             Celery worker (background tasks)
  redis              Redis Stack
  ollama             Ollama LLM service
  all                All local services (default)

Examples:
  $0 start           # Start all services
  $0 start backend   # Start backend only
  $0 status          # Show status of all services
  $0 logs backend    # Follow backend logs
  $0 gui             # Open SLM GUI in browser

${YELLOW}For production deployment, use:${NC}
  - SLM GUI: https://172.16.168.19/orchestration
  - Ansible playbooks in autobot-slm-backend/ansible/

${BLUE}Documentation:${NC} docs/developer/SERVICE_MANAGEMENT.md
EOF
}

get_services() {
    local target="${1:-all}"
    case "$target" in
        backend)
            echo "$BACKEND_SERVICE"
            ;;
        celery)
            echo "$CELERY_SERVICE"
            ;;
        redis)
            echo "$REDIS_SERVICE"
            ;;
        ollama)
            echo "$OLLAMA_SERVICE"
            ;;
        all)
            echo "$BACKEND_SERVICE $CELERY_SERVICE $REDIS_SERVICE $OLLAMA_SERVICE"
            ;;
        *)
            echo -e "${RED}Unknown service: $target${NC}" >&2
            echo "Valid services: backend, celery, redis, ollama, all" >&2
            return 1
            ;;
    esac
}

start_services() {
    local services
    services=$(get_services "$1") || return 1

    echo -e "${GREEN}Starting services...${NC}"
    for service in $services; do
        echo -e "${BLUE}  Starting $service...${NC}"
        if sudo systemctl start "$service"; then
            echo -e "${GREEN}  ✓ $service started${NC}"
        else
            echo -e "${RED}  ✗ Failed to start $service${NC}"
        fi
    done
}

stop_services() {
    local services
    services=$(get_services "$1") || return 1

    echo -e "${YELLOW}Stopping services...${NC}"
    for service in $services; do
        echo -e "${BLUE}  Stopping $service...${NC}"
        if sudo systemctl stop "$service"; then
            echo -e "${GREEN}  ✓ $service stopped${NC}"
        else
            echo -e "${RED}  ✗ Failed to stop $service${NC}"
        fi
    done
}

restart_services() {
    local services
    services=$(get_services "$1") || return 1

    echo -e "${GREEN}Restarting services...${NC}"
    for service in $services; do
        echo -e "${BLUE}  Restarting $service...${NC}"
        if sudo systemctl restart "$service"; then
            echo -e "${GREEN}  ✓ $service restarted${NC}"
        else
            echo -e "${RED}  ✗ Failed to restart $service${NC}"
        fi
    done
}

show_status() {
    local services
    services=$(get_services "$1") || return 1

    echo -e "${GREEN}Service Status:${NC}"
    echo ""
    for service in $services; do
        systemctl status "$service" --no-pager || true
        echo ""
    done
}

show_logs() {
    local service="${1:-backend}"

    case "$service" in
        backend)
            service="$BACKEND_SERVICE"
            ;;
        celery)
            service="$CELERY_SERVICE"
            ;;
        redis)
            service="$REDIS_SERVICE"
            ;;
        ollama)
            service="$OLLAMA_SERVICE"
            ;;
    esac

    echo -e "${GREEN}Following logs for $service (Ctrl+C to exit)${NC}"
    echo ""
    journalctl -u "$service" -f
}

open_gui() {
    local url="https://172.16.168.19/orchestration"
    echo -e "${GREEN}Opening SLM Orchestration GUI...${NC}"
    echo -e "${BLUE}URL: $url${NC}"

    # Try to open in browser
    if command -v xdg-open &> /dev/null; then
        xdg-open "$url" &
    elif command -v open &> /dev/null; then
        open "$url" &
    else
        echo -e "${YELLOW}Could not auto-open browser. Please visit:${NC}"
        echo "$url"
    fi
}

# Main
case "${1:-}" in
    start)
        start_services "$2"
        ;;
    stop)
        stop_services "$2"
        ;;
    restart)
        restart_services "$2"
        ;;
    status)
        show_status "$2"
        ;;
    logs)
        show_logs "$2"
        ;;
    gui)
        open_gui
        ;;
    -h|--help|help)
        show_usage
        ;;
    "")
        show_usage
        ;;
    *)
        echo -e "${RED}Unknown command: $1${NC}" >&2
        echo ""
        show_usage
        exit 1
        ;;
esac
