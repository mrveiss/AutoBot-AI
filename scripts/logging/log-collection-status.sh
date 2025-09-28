#!/bin/bash

# AutoBot Log Collection Status
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
CENTRALIZED_DIR="$PROJECT_ROOT/logs/autobot-centralized"

echo "AutoBot Centralized Logging Status - $(date)"
echo "=============================================="

echo ""
echo "Cron Jobs Status:"
crontab -l | grep -i autobot || echo "No AutoBot cron jobs found"

echo ""
echo "Log Collection Summary:"
for vm_dir in vm1-frontend vm2-npu-worker vm3-redis vm4-ai-stack vm5-browser main-wsl; do
    if [[ -d "$CENTRALIZED_DIR/$vm_dir" ]]; then
        log_count=$(find "$CENTRALIZED_DIR/$vm_dir" -name "*.log" -type f | wc -l)
        size=$(du -sh "$CENTRALIZED_DIR/$vm_dir" 2>/dev/null | cut -f1)
        latest=$(find "$CENTRALIZED_DIR/$vm_dir" -name "*.log" -type f -printf "%TY-%Tm-%Td %TH:%TM\n" | sort | tail -1)
        echo "  $vm_dir: $log_count files, $size, latest: $latest"
    else
        echo "  $vm_dir: No logs directory"
    fi
done

echo ""
echo "Recent Log Collection Activity:"
tail -20 "$PROJECT_ROOT/logs/log-collection.log" 2>/dev/null || echo "No collection log found"

echo ""
echo "Disk Usage:"
du -sh "$CENTRALIZED_DIR" 2>/dev/null || echo "Centralized logs directory not found"
