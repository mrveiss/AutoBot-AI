#!/bin/bash
# Service Authentication Monitoring Dashboard
# Day 3 Phase 5 - Baseline Monitoring
# Tracks service auth metrics in logging-only mode

LOG_FILE="/home/kali/Desktop/AutoBot/logs/backend.log"
REPORT_DIR="/home/kali/Desktop/AutoBot/reports/monitoring"
TIMESTAMP=$(date +"%Y-%m-%d_%H-%M-%S")

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Create report directory
mkdir -p "$REPORT_DIR"

echo -e "${BLUE}═══════════════════════════════════════════════════════${NC}"
echo -e "${BLUE}   Service Authentication Monitoring Dashboard${NC}"
echo -e "${BLUE}   Generated: $(date)${NC}"
echo -e "${BLUE}═══════════════════════════════════════════════════════${NC}"
echo ""

# 1. Total Authentication Failures
echo -e "${YELLOW}📊 AUTHENTICATION FAILURE METRICS${NC}"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
TOTAL_FAILURES=$(grep -c "Service auth failed" "$LOG_FILE" 2>/dev/null || echo "0")
echo -e "Total auth failures logged: ${RED}$TOTAL_FAILURES${NC}"

# 2. Failure Rate (last hour)
HOUR_AGO=$(date -d '1 hour ago' '+%Y-%m-%d %H:%M')
RECENT_FAILURES=$(grep "Service auth failed" "$LOG_FILE" | grep -c "$HOUR_AGO" || echo "0")
echo -e "Failures in last hour: ${RED}$RECENT_FAILURES${NC}"
echo ""

# 3. Top Endpoints Without Auth
echo -e "${YELLOW}🎯 TOP ENDPOINTS WITHOUT AUTHENTICATION${NC}"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
grep "Service auth failed" "$LOG_FILE" | grep -oP "path=[^ ]+" | sort | uniq -c | sort -rn | head -10 | while read count path; do
    endpoint=$(echo "$path" | sed 's/path=//')
    echo -e "  ${count} times: ${BLUE}${endpoint}${NC}"
done
echo ""

# 4. Missing Header Analysis
echo -e "${YELLOW}🔍 MISSING HEADER ANALYSIS${NC}"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
SERVICE_ID_MISSING=$(grep "has_service_id=False" "$LOG_FILE" | wc -l)
SIGNATURE_MISSING=$(grep "has_signature=False" "$LOG_FILE" | wc -l)
TIMESTAMP_MISSING=$(grep "has_timestamp=False" "$LOG_FILE" | wc -l)

echo -e "Missing X-Service-ID header: ${RED}$SERVICE_ID_MISSING${NC} requests"
echo -e "Missing X-Service-Signature header: ${RED}$SIGNATURE_MISSING${NC} requests"
echo -e "Missing X-Service-Timestamp header: ${RED}$TIMESTAMP_MISSING${NC} requests"
echo ""

# 5. HTTP Method Distribution
echo -e "${YELLOW}📈 HTTP METHOD DISTRIBUTION${NC}"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
grep "Service auth failed" "$LOG_FILE" | grep -oP "method=[^ ]+" | sort | uniq -c | sort -rn | while read count method; do
    method_name=$(echo "$method" | sed 's/method=//')
    echo -e "  ${BLUE}${method_name}${NC}: $count requests"
done
echo ""

# 6. Error Pattern Analysis
echo -e "${YELLOW}⚠️  ERROR PATTERNS${NC}"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
grep "Service auth failed" "$LOG_FILE" | grep -oP "error='[^']+'" | sort | uniq -c | sort -rn | head -5 | while read count error; do
    error_msg=$(echo "$error" | sed "s/error='//; s/'//")
    echo -e "  ${count} times: ${RED}${error_msg}${NC}"
done
echo ""

# 7. Timeline Analysis (last 10 entries)
echo -e "${YELLOW}📅 RECENT AUTHENTICATION FAILURES (Last 10)${NC}"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
grep "Service auth failed" "$LOG_FILE" | tail -10 | while read line; do
    timestamp=$(echo "$line" | grep -oP '^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}')
    path=$(echo "$line" | grep -oP "path=[^ ]+" | sed 's/path=//')
    method=$(echo "$line" | grep -oP "method=[^ ]+" | sed 's/method=//')
    echo -e "  ${timestamp} - ${BLUE}${method}${NC} ${path}"
done
echo ""

# 8. Baseline Recommendations
echo -e "${YELLOW}💡 BASELINE & RECOMMENDATIONS${NC}"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

if [ "$TOTAL_FAILURES" -gt 100 ]; then
    echo -e "${RED}⚠️  HIGH FAILURE RATE DETECTED${NC}"
    echo -e "   Current: $TOTAL_FAILURES failures"
    echo -e "   Action: Investigate why so many requests lack authentication"
    echo ""
fi

if [ "$RECENT_FAILURES" -gt 50 ]; then
    echo -e "${RED}⚠️  RECENT SPIKE IN FAILURES${NC}"
    echo -e "   Last hour: $RECENT_FAILURES failures"
    echo -e "   Action: Check if frontend is missing auth headers"
    echo ""
fi

echo -e "${GREEN}✅ BASELINE ESTABLISHED${NC}"
echo -e "   Total failures: $TOTAL_FAILURES"
echo -e "   Monitoring mode: ${YELLOW}LOGGING ONLY${NC} (not blocking)"
echo -e "   Next steps:"
echo -e "   1. Monitor for 24-48 hours"
echo -e "   2. Update frontend to send auth headers"
echo -e "   3. Switch to enforcement mode when ready"
echo ""

# 9. Save detailed report
REPORT_FILE="$REPORT_DIR/service_auth_baseline_$TIMESTAMP.json"
cat > "$REPORT_FILE" << EOF
{
  "timestamp": "$(date -Iseconds)",
  "monitoring_mode": "logging_only",
  "metrics": {
    "total_failures": $TOTAL_FAILURES,
    "recent_failures_1h": $RECENT_FAILURES,
    "missing_service_id": $SERVICE_ID_MISSING,
    "missing_signature": $SIGNATURE_MISSING,
    "missing_timestamp": $TIMESTAMP_MISSING
  },
  "top_endpoints": $(grep "Service auth failed" "$LOG_FILE" | grep -oP "path=[^ ]+" | sort | uniq -c | sort -rn | head -5 | awk '{print "{\"path\":\""$2"\",\"count\":"$1"}"}' | jq -s '.' 2>/dev/null || echo '[]'),
  "recommendations": [
    "Monitor for 24-48 hours to establish baseline",
    "Update frontend to include service authentication headers",
    "Prepare enforcement mode after frontend updates"
  ]
}
EOF

echo -e "${BLUE}═══════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}✅ Baseline report saved to:${NC}"
echo -e "   $REPORT_FILE"
echo -e "${BLUE}═══════════════════════════════════════════════════════${NC}"
