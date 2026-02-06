#!/bin/bash

# AutoBot Centralized Log Viewer
# Interactive log viewing interface for centralized logs

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
CENTRALIZED_DIR="$PROJECT_ROOT/logs/autobot-centralized"

# Color codes
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

show_menu() {
    clear
    echo -e "${CYAN}═══════════════════════════════════════════════${NC}"
    echo -e "${CYAN}    AutoBot Centralized Log Viewer${NC}"
    echo -e "${CYAN}═══════════════════════════════════════════════${NC}"
    echo ""
    echo -e "${YELLOW}Available VMs:${NC}"
    echo "1. VM1 - Frontend (172.16.168.21)"
    echo "2. VM2 - NPU Worker (172.16.168.22)"
    echo "3. VM3 - Redis (172.16.168.23)"
    echo "4. VM4 - AI Stack (172.16.168.24)"
    echo "5. VM5 - Browser (172.16.168.25)"
    echo "6. Main WSL Machine"
    echo ""
    echo -e "${YELLOW}Log Analysis:${NC}"
    echo "7. View recent errors (all VMs)"
    echo "8. Search all logs"
    echo "9. Show disk usage"
    echo "10. Live tail (follow) logs"
    echo "11. Show log summary"
    echo ""
    echo "0. Exit"
    echo ""
    echo -n "Select option [0-11]: "
}

view_vm_logs() {
    local vm_dir="$1"
    local vm_name="$2"

    if [[ ! -d "$CENTRALIZED_DIR/$vm_dir" ]]; then
        echo -e "${RED}No logs found for $vm_name${NC}"
        return
    fi

    echo -e "${CYAN}Logs for $vm_name:${NC}"
    echo ""
    echo -e "${YELLOW}Log Types:${NC}"
    echo "1. System logs"
    echo "2. Application logs"
    echo "3. Service logs"
    echo "4. All recent logs (last 50 lines each)"
    echo "5. List available log files"
    echo ""
    echo -n "Select log type [1-5]: "
    read -r log_type

    case $log_type in
        1)
            echo -e "${CYAN}System logs for $vm_name:${NC}"
            find "$CENTRALIZED_DIR/$vm_dir/system" -name "*.log" -type f -exec echo -e "${YELLOW}=== {} ===${NC}" \; -exec tail -n 30 {} \; 2>/dev/null | less -R
            ;;
        2)
            echo -e "${CYAN}Application logs for $vm_name:${NC}"
            find "$CENTRALIZED_DIR/$vm_dir/application" -name "*.log" -type f -exec echo -e "${YELLOW}=== {} ===${NC}" \; -exec tail -n 30 {} \; 2>/dev/null | less -R
            ;;
        3)
            echo -e "${CYAN}Service logs for $vm_name:${NC}"
            find "$CENTRALIZED_DIR/$vm_dir/service" -name "*.log" -type f -exec echo -e "${YELLOW}=== {} ===${NC}" \; -exec tail -n 30 {} \; 2>/dev/null | less -R
            ;;
        4)
            echo -e "${CYAN}All recent logs for $vm_name:${NC}"
            find "$CENTRALIZED_DIR/$vm_dir" -name "*.log" -type f -exec echo -e "${YELLOW}=== {} ===${NC}" \; -exec tail -n 20 {} \; 2>/dev/null | less -R
            ;;
        5)
            echo -e "${CYAN}Available log files for $vm_name:${NC}"
            find "$CENTRALIZED_DIR/$vm_dir" -name "*.log" -type f -printf "%TY-%Tm-%Td %TH:%TM  %s bytes  %p\n" | sort -r
            ;;
    esac
}

search_logs() {
    echo -n "Enter search term: "
    read -r search_term

    if [[ -n "$search_term" ]]; then
        echo -e "${CYAN}Searching for '$search_term' in all logs...${NC}"
        echo ""
        grep -r -i -n --color=always "$search_term" "$CENTRALIZED_DIR/" 2>/dev/null | head -50 | while IFS= read -r line; do
            echo -e "${YELLOW}$(echo "$line" | cut -d: -f1):${NC}$(echo "$line" | cut -d: -f2-)"
        done
        echo ""
        echo -e "${CYAN}Showing first 50 matches. Use 'grep -r -i \"$search_term\" \"$CENTRALIZED_DIR/\"' for full results.${NC}"
    fi
}

show_disk_usage() {
    echo -e "${CYAN}Centralized Logging Disk Usage:${NC}"
    echo ""
    du -h -d 2 "$CENTRALIZED_DIR" | sort -hr
    echo ""
    echo -e "${YELLOW}Log file count by VM:${NC}"
    for vm_dir in "$CENTRALIZED_DIR"/*/; do
        if [[ -d "$vm_dir" ]]; then
            vm_name=$(basename "$vm_dir")
            log_count=$(find "$vm_dir" -name "*.log" -type f | wc -l)
            echo "  $vm_name: $log_count log files"
        fi
    done
}

show_recent_errors() {
    echo -e "${CYAN}Recent errors from all VMs (last 24 hours):${NC}"
    echo ""

    # Search for error patterns in all logs
    find "$CENTRALIZED_DIR" -name "*.log" -type f -mtime -1 2>/dev/null | while read -r log_file; do
        grep -i -n -C 2 'error\|failed\|exception\|critical\|fatal' "$log_file" 2>/dev/null | head -10 | while IFS= read -r line; do
            echo -e "${RED}$log_file:${NC} $line"
        done
    done | head -30

    echo ""
    echo -e "${YELLOW}Note: Showing first 30 error occurrences${NC}"
}

live_tail_logs() {
    echo -e "${CYAN}Live tail of recent logs (Ctrl+C to stop):${NC}"
    echo ""
    echo -n "Enter VM number (1-6) or 'all' for all VMs: "
    read -r vm_choice

    case $vm_choice in
        1) tail -f "$CENTRALIZED_DIR/vm1-frontend"/**/*.log 2>/dev/null ;;
        2) tail -f "$CENTRALIZED_DIR/vm2-npu-worker"/**/*.log 2>/dev/null ;;
        3) tail -f "$CENTRALIZED_DIR/vm3-redis"/**/*.log 2>/dev/null ;;
        4) tail -f "$CENTRALIZED_DIR/vm4-ai-stack"/**/*.log 2>/dev/null ;;
        5) tail -f "$CENTRALIZED_DIR/vm5-browser"/**/*.log 2>/dev/null ;;
        6) tail -f "$CENTRALIZED_DIR/main-wsl"/**/*.log 2>/dev/null ;;
        all|ALL) tail -f "$CENTRALIZED_DIR"/**/*.log 2>/dev/null ;;
        *) echo -e "${RED}Invalid choice${NC}" ;;
    esac
}

show_log_summary() {
    echo -e "${CYAN}AutoBot Centralized Logging Summary:${NC}"
    echo ""
    echo -e "${YELLOW}Collection Status:${NC}"

    for vm_dir in vm1-frontend vm2-npu-worker vm3-redis vm4-ai-stack vm5-browser main-wsl; do
        if [[ -d "$CENTRALIZED_DIR/$vm_dir" ]]; then
            log_count=$(find "$CENTRALIZED_DIR/$vm_dir" -name "*.log" -type f | wc -l)
            latest_log=$(find "$CENTRALIZED_DIR/$vm_dir" -name "*.log" -type f -printf "%TY-%Tm-%Td %TH:%TM %p\n" | sort -r | head -1)
            echo "  $vm_dir: $log_count files, latest: $latest_log"
        else
            echo "  $vm_dir: No logs collected"
        fi
    done

    echo ""
    echo -e "${YELLOW}Total Storage:${NC}"
    total_size=$(du -sh "$CENTRALIZED_DIR" | cut -f1)
    total_files=$(find "$CENTRALIZED_DIR" -name "*.log" -type f | wc -l)
    echo "  Total size: $total_size"
    echo "  Total log files: $total_files"

    echo ""
    echo -e "${YELLOW}Recent Activity (last hour):${NC}"
    find "$CENTRALIZED_DIR" -name "*.log" -type f -mmin -60 -printf "%TY-%Tm-%Td %TH:%TM  %p\n" | sort -r | head -10
}

# Main loop
while true; do
    show_menu
    read -r choice

    case $choice in
        1)
            view_vm_logs "vm1-frontend" "Frontend VM"
            ;;
        2)
            view_vm_logs "vm2-npu-worker" "NPU Worker VM"
            ;;
        3)
            view_vm_logs "vm3-redis" "Redis VM"
            ;;
        4)
            view_vm_logs "vm4-ai-stack" "AI Stack VM"
            ;;
        5)
            view_vm_logs "vm5-browser" "Browser VM"
            ;;
        6)
            view_vm_logs "main-wsl" "Main WSL Machine"
            ;;
        7)
            show_recent_errors
            ;;
        8)
            search_logs
            ;;
        9)
            show_disk_usage
            ;;
        10)
            live_tail_logs
            ;;
        11)
            show_log_summary
            ;;
        0)
            echo "Exiting..."
            exit 0
            ;;
        *)
            echo -e "${RED}Invalid option${NC}"
            sleep 1
            ;;
    esac

    echo ""
    echo -n "Press Enter to continue..."
    read -r
done
