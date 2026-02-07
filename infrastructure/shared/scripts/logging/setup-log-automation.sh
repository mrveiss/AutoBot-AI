#!/bin/bash

# AutoBot Log Automation Setup
# Sets up cron jobs and log rotation for centralized logging

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"

# Color codes
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

echo -e "${CYAN}Setting up AutoBot log automation...${NC}"

# Setup cron jobs for automated log collection
echo -e "${YELLOW}Configuring cron jobs...${NC}"

# Create temporary cron file
TEMP_CRON=$(mktemp)

# Get existing crontab (if any)
crontab -l 2>/dev/null > "$TEMP_CRON" || touch "$TEMP_CRON"

# Remove any existing AutoBot logging entries
grep -v "AutoBot.*[Ll]og" "$TEMP_CRON" > "${TEMP_CRON}.clean" || touch "${TEMP_CRON}.clean"
mv "${TEMP_CRON}.clean" "$TEMP_CRON"

# Add AutoBot centralized logging cron jobs
cat >> "$TEMP_CRON" << EOF

# AutoBot Centralized Logging (Added $(date))
# Collect service logs every 15 minutes
*/15 * * * * $SCRIPT_DIR/collect-service-logs.sh >> $PROJECT_ROOT/logs/log-collection.log 2>&1

# Collect application logs every hour
0 * * * * $SCRIPT_DIR/collect-application-logs.sh >> $PROJECT_ROOT/logs/log-collection.log 2>&1

# Clean old logs daily at 2 AM
0 2 * * * find $PROJECT_ROOT/logs/autobot-centralized -name "*.log" -mtime +7 -delete >> $PROJECT_ROOT/logs/log-collection.log 2>&1
EOF

# Install the new crontab
crontab "$TEMP_CRON"
rm "$TEMP_CRON"

echo -e "${GREEN}Cron jobs configured:${NC}"
echo "  - Service logs: Every 15 minutes"
echo "  - Application logs: Every hour"
echo "  - Log cleanup: Daily at 2 AM (keeps 7 days)"

# Create log rotation configuration
echo -e "${YELLOW}Setting up log rotation...${NC}"

cat > /tmp/autobot-logrotate << EOF
# AutoBot Centralized Logging Rotation
$PROJECT_ROOT/logs/autobot-centralized/*/*.log $PROJECT_ROOT/logs/autobot-centralized/*/*/*.log {
    daily
    rotate 7
    compress
    delaycompress
    missingok
    notifempty
    create 644 $(whoami) $(whoami)
    copytruncate
}

$PROJECT_ROOT/logs/*.log {
    daily
    rotate 14
    compress
    delaycompress
    missingok
    notifempty
    create 644 $(whoami) $(whoami)
    copytruncate
}
EOF

# Test logrotate configuration
if logrotate -d /tmp/autobot-logrotate &>/dev/null; then
    echo -e "${GREEN}Log rotation configuration validated${NC}"
    if command -v sudo &>/dev/null; then
        echo "To install log rotation, run: sudo cp /tmp/autobot-logrotate /etc/logrotate.d/autobot"
    fi
else
    echo -e "${YELLOW}Log rotation validation failed, but configuration created${NC}"
fi

# Create log collection status script
cat > "$SCRIPT_DIR/log-collection-status.sh" << 'EOF'
#!/bin/bash

# AutoBot Log Collection Status
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
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
EOF

chmod +x "$SCRIPT_DIR/log-collection-status.sh"

echo ""
echo -e "${GREEN}AutoBot log automation setup complete!${NC}"
echo ""
echo -e "${CYAN}Available commands:${NC}"
echo "  View logs:         $SCRIPT_DIR/view-centralized-logs.sh"
echo "  Collect now:       $SCRIPT_DIR/collect-service-logs.sh"
echo "  Collect apps:      $SCRIPT_DIR/collect-application-logs.sh"
echo "  Check status:      $SCRIPT_DIR/log-collection-status.sh"
echo ""
echo -e "${CYAN}Automation configured:${NC}"
echo "  Automated collection every 15 minutes and hourly"
echo "  Log cleanup after 7 days"
echo "  Collection logs: $PROJECT_ROOT/logs/log-collection.log"
