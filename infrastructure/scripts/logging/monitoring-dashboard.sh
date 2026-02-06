#!/bin/bash

# AutoBot Centralized Logging Monitoring Dashboard
# Real-time monitoring interface for distributed AutoBot infrastructure

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
CENTRALIZED_DIR="$PROJECT_ROOT/logs/autobot-centralized"
SSH_KEY="$HOME/.ssh/autobot_key"

# Color codes
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
PURPLE='\033[0;35m'
NC='\033[0m'

# VM Configuration
declare -A VMS=(
    ["vm1-frontend"]="172.16.168.21"
    ["vm2-npu-worker"]="172.16.168.22"
    ["vm3-redis"]="172.16.168.23"
    ["vm4-ai-stack"]="172.16.168.24"
    ["vm5-browser"]="172.16.168.25"
)

show_header() {
    clear
    echo -e "${CYAN}╔══════════════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${CYAN}║                    AutoBot Infrastructure Monitor                     ║${NC}"
    echo -e "${CYAN}║                      Centralized Logging Dashboard                   ║${NC}"
    echo -e "${CYAN}╚══════════════════════════════════════════════════════════════════════╝${NC}"
    echo ""
    echo -e "${YELLOW}Last Update: $(date)${NC}"
    echo ""
}

check_vm_health() {
    local vm_name="$1"
    local vm_ip="$2"

    # Test SSH connectivity
    if ssh -i "$SSH_KEY" -o ConnectTimeout=3 -o BatchMode=yes autobot@"$vm_ip" "echo 'test'" &>/dev/null; then
        echo -e "${GREEN}✓${NC}"
    else
        echo -e "${RED}✗${NC}"
    fi
}

get_service_status() {
    local vm_name="$1"
    local vm_ip="$2"

    case "$vm_name" in
        "vm1-frontend")
            ssh -i "$SSH_KEY" autobot@"$vm_ip" "ps aux | grep -c 'npm run dev\|node.*vite'" 2>/dev/null || echo "0"
            ;;
        "vm3-redis")
            ssh -i "$SSH_KEY" autobot@"$vm_ip" "redis-cli ping 2>/dev/null | grep -c PONG" 2>/dev/null || echo "0"
            ;;
        "vm5-browser")
            ssh -i "$SSH_KEY" autobot@"$vm_ip" "docker ps | grep -c autobot-playwright" 2>/dev/null || echo "0"
            ;;
        *)
            ssh -i "$SSH_KEY" autobot@"$vm_ip" "ps aux | grep -c python | head -1" 2>/dev/null || echo "0"
            ;;
    esac
}

show_vm_status() {
    echo -e "${PURPLE}┌─────────────────────────────────────────────────────────────────────┐${NC}"
    echo -e "${PURPLE}│                           VM Health Status                          │${NC}"
    echo -e "${PURPLE}├─────────────────────────────────────────────────────────────────────┤${NC}"

    printf "${PURPLE}│${NC} %-15s %-16s %-8s %-8s %-15s ${PURPLE}│${NC}\n" "VM" "IP Address" "SSH" "Service" "Description"
    echo -e "${PURPLE}├─────────────────────────────────────────────────────────────────────┤${NC}"

    for vm_name in "${!VMS[@]}"; do
        vm_ip="${VMS[$vm_name]}"
        ssh_status=$(check_vm_health "$vm_name" "$vm_ip")
        service_count=$(get_service_status "$vm_name" "$vm_ip")

        if [[ "$service_count" -gt "0" ]]; then
            service_status="${GREEN}✓${NC}"
        else
            service_status="${YELLOW}?${NC}"
        fi

        case "$vm_name" in
            "vm1-frontend") description="Vue.js Frontend" ;;
            "vm2-npu-worker") description="NPU AI Worker" ;;
            "vm3-redis") description="Redis Database" ;;
            "vm4-ai-stack") description="AI Processing" ;;
            "vm5-browser") description="Browser Automation" ;;
        esac

        printf "${PURPLE}│${NC} %-15s %-16s %-14s %-14s %-15s ${PURPLE}│${NC}\n" \
               "$vm_name" "$vm_ip" "$ssh_status" "$service_status" "$description"
    done

    echo -e "${PURPLE}└─────────────────────────────────────────────────────────────────────┘${NC}"
}

show_log_summary() {
    echo ""
    echo -e "${PURPLE}┌─────────────────────────────────────────────────────────────────────┐${NC}"
    echo -e "${PURPLE}│                        Log Collection Summary                       │${NC}"
    echo -e "${PURPLE}├─────────────────────────────────────────────────────────────────────┤${NC}"

    printf "${PURPLE}│${NC} %-15s %-10s %-8s %-20s ${PURPLE}│${NC}\n" "VM" "Files" "Size" "Latest Collection"
    echo -e "${PURPLE}├─────────────────────────────────────────────────────────────────────┤${NC}"

    for vm_dir in vm1-frontend vm2-npu-worker vm3-redis vm4-ai-stack vm5-browser main-wsl; do
        if [[ -d "$CENTRALIZED_DIR/$vm_dir" ]]; then
            log_count=$(find "$CENTRALIZED_DIR/$vm_dir" -name "*.log" -type f | wc -l)
            size=$(du -sh "$CENTRALIZED_DIR/$vm_dir" 2>/dev/null | cut -f1)
            latest=$(find "$CENTRALIZED_DIR/$vm_dir" -name "*.log" -type f -printf "%TY-%Tm-%Td %TH:%TM\n" | sort | tail -1)
            [[ -z "$latest" ]] && latest="No logs"

            printf "${PURPLE}│${NC} %-15s %-10s %-8s %-20s ${PURPLE}│${NC}\n" "$vm_dir" "$log_count" "$size" "$latest"
        else
            printf "${PURPLE}│${NC} %-15s %-10s %-8s %-20s ${PURPLE}│${NC}\n" "$vm_dir" "0" "0" "No directory"
        fi
    done

    total_size=$(du -sh "$CENTRALIZED_DIR" 2>/dev/null | cut -f1)
    total_files=$(find "$CENTRALIZED_DIR" -name "*.log" -type f | wc -l)
    echo -e "${PURPLE}├─────────────────────────────────────────────────────────────────────┤${NC}"
    printf "${PURPLE}│${NC} %-15s %-10s %-8s %-20s ${PURPLE}│${NC}\n" "TOTAL" "$total_files" "$total_size" ""
    echo -e "${PURPLE}└─────────────────────────────────────────────────────────────────────┘${NC}"
}

show_recent_activity() {
    echo ""
    echo -e "${PURPLE}┌─────────────────────────────────────────────────────────────────────┐${NC}"
    echo -e "${PURPLE}│                         Recent Activity                             │${NC}"
    echo -e "${PURPLE}├─────────────────────────────────────────────────────────────────────┤${NC}"

    # Show recent errors from all VMs
    echo -e "${RED}Recent Errors (last hour):${NC}"
    find "$CENTRALIZED_DIR" -name "*.log" -type f -mmin -60 2>/dev/null | xargs grep -i -h "error\|failed\|exception" | head -5 | while IFS= read -r line; do
        echo "  ${RED}•${NC} ${line:0:60}..."
    done || echo "  ${GREEN}No recent errors found${NC}"

    echo ""
    echo -e "${YELLOW}Recent Log Files (last 2 hours):${NC}"
    find "$CENTRALIZED_DIR" -name "*.log" -type f -mmin -120 -printf "%TY-%Tm-%Td %TH:%TM  %f\n" | sort -r | head -8 | while IFS= read -r line; do
        echo "  ${CYAN}•${NC} $line"
    done || echo "  ${YELLOW}No recent log files${NC}"

    echo -e "${PURPLE}└─────────────────────────────────────────────────────────────────────┘${NC}"
}

show_automation_status() {
    echo ""
    echo -e "${PURPLE}┌─────────────────────────────────────────────────────────────────────┐${NC}"
    echo -e "${PURPLE}│                        Automation Status                           │${NC}"
    echo -e "${PURPLE}├─────────────────────────────────────────────────────────────────────┤${NC}"

    # Check cron jobs
    cron_count=$(crontab -l 2>/dev/null | grep -c "AutoBot.*[Ll]og" || echo "0")
    if [[ "$cron_count" -gt "0" ]]; then
        echo -e "  ${GREEN}✓${NC} Automated collection: $cron_count cron jobs active"
    else
        echo -e "  ${RED}✗${NC} No automated collection configured"
    fi

    # Check last collection
    if [[ -f "$PROJECT_ROOT/logs/log-collection.log" ]]; then
        last_collection=$(tail -1 "$PROJECT_ROOT/logs/log-collection.log" 2>/dev/null | grep -o '[0-9][0-9]:[0-9][0-9]' | tail -1)
        echo -e "  ${CYAN}•${NC} Last collection: $last_collection"
    else
        echo -e "  ${YELLOW}•${NC} Collection log not found"
    fi

    echo -e "${PURPLE}└─────────────────────────────────────────────────────────────────────┘${NC}"
}

show_actions() {
    echo ""
    echo -e "${CYAN}Available Actions:${NC}"
    echo "  [1] Collect logs now     [2] View specific VM     [3] Search logs"
    echo "  [4] Show disk usage      [5] Live tail logs       [6] Export summary"
    echo "  [r] Refresh dashboard    [q] Quit"
    echo ""
    echo -n "Select action: "
}

handle_action() {
    local action="$1"

    case "$action" in
        "1")
            echo -e "${CYAN}Collecting logs from all VMs...${NC}"
            "$SCRIPT_DIR/collect-service-logs.sh" && "$SCRIPT_DIR/collect-application-logs.sh"
            ;;
        "2")
            "$SCRIPT_DIR/view-centralized-logs.sh"
            ;;
        "3")
            echo -n "Enter search term: "
            read -r search_term
            if [[ -n "$search_term" ]]; then
                grep -r -i -n --color=always "$search_term" "$CENTRALIZED_DIR/" | head -20
            fi
            ;;
        "4")
            du -h -d 2 "$CENTRALIZED_DIR" | sort -hr
            ;;
        "5")
            echo -e "${CYAN}Live tail of all logs (Ctrl+C to stop):${NC}"
            sleep 2
            tail -f "$CENTRALIZED_DIR"/**/*.log 2>/dev/null
            ;;
        "6")
            local report_file="$PROJECT_ROOT/logs/monitoring-report-$(date +%Y%m%d_%H%M%S).txt"
            {
                echo "AutoBot Infrastructure Monitoring Report"
                echo "Generated: $(date)"
                echo "=========================================="
                echo ""
                "$SCRIPT_DIR/log-collection-status.sh"
            } > "$report_file"
            echo -e "${GREEN}Report exported to: $report_file${NC}"
            ;;
        "r"|"")
            return 0
            ;;
        "q")
            exit 0
            ;;
        *)
            echo -e "${RED}Invalid action${NC}"
            sleep 1
            ;;
    esac

    if [[ "$action" != "r" && "$action" != "" ]]; then
        echo ""
        echo "Press Enter to continue..."
        read -r
    fi
}

# Main monitoring loop
while true; do
    show_header
    show_vm_status
    show_log_summary
    show_recent_activity
    show_automation_status
    show_actions

    read -r action
    handle_action "$action"
done
