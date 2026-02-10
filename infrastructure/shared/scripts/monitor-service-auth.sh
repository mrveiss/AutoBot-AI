#!/bin/bash
# Service Authentication Monitoring Script
# Monitors authentication patterns during 24-hour logging phase

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/lib/ssot-config.sh" 2>/dev/null || true
PROJECT_ROOT="${PROJECT_ROOT:-$(cd "$SCRIPT_DIR/../../.." && pwd)}"
LOG_FILE="$PROJECT_ROOT/logs/backend.log"
REPORT_DIR="$PROJECT_ROOT/reports/service-auth"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Create report directory
mkdir -p "$REPORT_DIR"

echo -e "${GREEN}═══════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}  AutoBot Service Authentication Monitor${NC}"
echo -e "${GREEN}  Monitoring Period: 24 hours (Day 2-3 transition)${NC}"
echo -e "${GREEN}═══════════════════════════════════════════════════════${NC}"
echo ""

# Function to analyze authentication logs
analyze_auth_logs() {
    local report_file="$REPORT_DIR/auth-analysis-$TIMESTAMP.md"

    echo "# Service Authentication Analysis Report" > "$report_file"
    echo "**Generated**: $(date)" >> "$report_file"
    echo "**Mode**: LOGGING (Day 2)" >> "$report_file"
    echo "" >> "$report_file"

    echo "## 1. Authentication Success Rate" >> "$report_file"
    echo "" >> "$report_file"

    # Count successful authentications
    local success_count=$(grep "Service authentication successful" "$LOG_FILE" 2>/dev/null | wc -l || echo "0")
    local failure_count=$(grep "Service auth validation error\|Missing authentication headers\|Invalid signature" "$LOG_FILE" 2>/dev/null | wc -l || echo "0")
    local total=$((success_count + failure_count))

    if [ $total -gt 0 ]; then
        local success_rate=$(awk "BEGIN {printf \"%.2f\", ($success_count / $total) * 100}")
        echo "- **Total Requests**: $total" >> "$report_file"
        echo "- **Successful**: $success_count" >> "$report_file"
        echo "- **Failed**: $failure_count" >> "$report_file"
        echo "- **Success Rate**: ${success_rate}%" >> "$report_file"
    else
        echo "- **Status**: No service-to-service authentication attempts detected" >> "$report_file"
        echo "- **Note**: This is expected if no distributed services are making API calls yet" >> "$report_file"
    fi

    echo "" >> "$report_file"
    echo "## 2. Service Activity Breakdown" >> "$report_file"
    echo "" >> "$report_file"

    # Analyze by service ID
    echo "### Authenticated Services" >> "$report_file"
    grep "Service authentication successful" "$LOG_FILE" 2>/dev/null | \
        grep -oP 'service_id=\K[^ ]+' | sort | uniq -c | \
        awk '{print "- **" $2 "**: " $1 " requests"}' >> "$report_file" || \
        echo "- No authenticated service calls detected" >> "$report_file"

    echo "" >> "$report_file"
    echo "### Failed Authentication Attempts" >> "$report_file"
    local failed_services=$(grep "Invalid signature\|Unknown service" "$LOG_FILE" 2>/dev/null | \
        grep -oP 'service_id=\K[^ ]+' | sort | uniq -c || echo "")

    if [ -n "$failed_services" ]; then
        echo "$failed_services" | awk '{print "- **" $2 "**: " $1 " failures"}' >> "$report_file"
    else
        echo "- No failed authentication attempts (✅ Good sign)" >> "$report_file"
    fi

    echo "" >> "$report_file"
    echo "## 3. Authentication Errors Analysis" >> "$report_file"
    echo "" >> "$report_file"

    # Analyze error types
    echo "### Error Distribution" >> "$report_file"
    local missing_headers=$(grep "Missing authentication headers" "$LOG_FILE" 2>/dev/null | wc -l || echo "0")
    local invalid_sig=$(grep "Invalid signature" "$LOG_FILE" 2>/dev/null | wc -l || echo "0")
    local invalid_ts=$(grep "Timestamp outside allowed window" "$LOG_FILE" 2>/dev/null | wc -l || echo "0")
    local unknown_service=$(grep "Unknown service" "$LOG_FILE" 2>/dev/null | wc -l || echo "0")

    echo "- **Missing Headers**: $missing_headers" >> "$report_file"
    echo "- **Invalid Signature**: $invalid_sig" >> "$report_file"
    echo "- **Timestamp Issues**: $invalid_ts" >> "$report_file"
    echo "- **Unknown Service**: $unknown_service" >> "$report_file"

    echo "" >> "$report_file"
    echo "## 4. Endpoint Access Patterns" >> "$report_file"
    echo "" >> "$report_file"

    # Analyze which endpoints are being called
    grep "Service authentication successful" "$LOG_FILE" 2>/dev/null | \
        grep -oP 'path=[^ ]+' | sort | uniq -c | \
        awk '{print "- **" $2 "**: " $1 " calls"}' >> "$report_file" || \
        echo "- No endpoint access data available" >> "$report_file"

    echo "" >> "$report_file"
    echo "## 5. Recommendations" >> "$report_file"
    echo "" >> "$report_file"

    # Generate recommendations based on analysis
    if [ $failure_count -eq 0 ]; then
        echo "✅ **No authentication failures detected - Ready for enforcement mode**" >> "$report_file"
        echo "" >> "$report_file"
        echo "The logging phase shows clean authentication with no failures. System is ready for Day 3 enforcement deployment." >> "$report_file"
    elif [ $total -gt 0 ] && [ $(awk "BEGIN {print ($failure_count / $total) < 0.05}") -eq 1 ]; then
        echo "⚠️ **Low failure rate detected - Review failures before enforcement**" >> "$report_file"
        echo "" >> "$report_file"
        echo "Failure rate is below 5%. Review failure logs to ensure they are not legitimate services." >> "$report_file"
    else
        echo "❌ **High failure rate - DO NOT proceed to enforcement mode**" >> "$report_file"
        echo "" >> "$report_file"
        echo "Investigate authentication failures before enabling enforcement. Check:" >> "$report_file"
        echo "- Service key distribution" >> "$report_file"
        echo "- Clock synchronization across VMs" >> "$report_file"
        echo "- Network connectivity" >> "$report_file"
    fi

    echo "" >> "$report_file"
    echo "---" >> "$report_file"
    echo "*Report generated by AutoBot Service Auth Monitor*" >> "$report_file"

    echo -e "${GREEN}✅ Analysis report saved: $report_file${NC}"
    cat "$report_file"
}

# Function to monitor in real-time
monitor_realtime() {
    echo -e "${YELLOW}📊 Real-time Authentication Monitoring${NC}"
    echo -e "${YELLOW}Press Ctrl+C to stop${NC}"
    echo ""

    # Tail the log and filter for service auth events
    tail -f "$LOG_FILE" | grep --line-buffered -E "Service authentication|service_id=|auth" | while read -r line; do
        if echo "$line" | grep -q "successful"; then
            echo -e "${GREEN}✅ $line${NC}"
        elif echo "$line" | grep -q "failed\|error\|Invalid"; then
            echo -e "${RED}❌ $line${NC}"
        else
            echo "$line"
        fi
    done
}

# Function to check Redis for service keys
check_service_keys() {
    echo -e "${YELLOW}🔑 Checking Service Keys in Redis${NC}"
    echo ""

    # Check if Redis is accessible
    if ! redis-cli -h "${AUTOBOT_REDIS_HOST:-172.16.168.23}" -p "${AUTOBOT_REDIS_PORT:-6379}" ping > /dev/null 2>&1; then
        echo -e "${RED}❌ Cannot connect to Redis at ${AUTOBOT_REDIS_HOST:-172.16.168.23}:${AUTOBOT_REDIS_PORT:-6379}${NC}"
        return 1
    fi

    # List all service keys
    local services=("main-backend" "frontend" "npu-worker" "redis-stack" "ai-stack" "browser-service")

    for service in "${services[@]}"; do
        local key_exists=$(redis-cli -h "${AUTOBOT_REDIS_HOST:-172.16.168.23}" -p "${AUTOBOT_REDIS_PORT:-6379}" exists "service:key:$service")
        if [ "$key_exists" -eq 1 ]; then
            echo -e "${GREEN}✅ $service: Key exists${NC}"
        else
            echo -e "${RED}❌ $service: Key missing${NC}"
        fi
    done
}

# Main menu
echo "Select monitoring mode:"
echo "  1) Generate analysis report (recommended)"
echo "  2) Real-time monitoring"
echo "  3) Check service keys in Redis"
echo "  4) Run all checks"
echo ""
read -p "Enter choice [1-4]: " choice

case $choice in
    1)
        analyze_auth_logs
        ;;
    2)
        monitor_realtime
        ;;
    3)
        check_service_keys
        ;;
    4)
        check_service_keys
        echo ""
        analyze_auth_logs
        echo ""
        echo -e "${YELLOW}Starting real-time monitoring...${NC}"
        monitor_realtime
        ;;
    *)
        echo -e "${RED}Invalid choice${NC}"
        exit 1
        ;;
esac
