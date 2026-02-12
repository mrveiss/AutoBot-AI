#!/bin/bash
# AutoBot Grafana Configuration Verification
# Tests that Grafana is properly configured for iframe embedding

set -e

HOST="${1:-localhost}"
PORT="${2:-3000}"

echo "=== AutoBot Grafana Configuration Verification ==="
echo "Target: ${HOST}"
echo ""

# Color codes
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

FAILED=0

# Function to check setting
check_setting() {
    local setting="$1"
    local expected="$2"
    local section="$3"

    if ssh "autobot@${HOST}" "grep -A 10 '\\[${section}\\]' /etc/grafana/grafana.ini | grep -q '^${setting} = ${expected}'" 2>/dev/null; then
        echo -e "${GREEN}✓${NC} ${section}: ${setting} = ${expected}"
        return 0
    else
        echo -e "${RED}✗${NC} ${section}: ${setting} = ${expected} (NOT FOUND)"
        FAILED=1
        return 1
    fi
}

echo "1. Critical Settings Check:"
echo "----------------------------"

# Check serve_from_sub_path
check_setting "serve_from_sub_path" "true" "server"

# Check allow_embedding
check_setting "allow_embedding" "true" "security"

# Check cookie_samesite
check_setting "cookie_samesite" "none" "security"

# Check anonymous auth
check_setting "enabled" "true" "auth.anonymous"

echo ""

# Check API health
echo "2. API Health Check:"
echo "----------------------------"
if curl -s "http://${HOST}:${PORT}/api/health" | jq -e '.database == "ok"' > /dev/null 2>&1; then
    echo -e "${GREEN}✓${NC} API is healthy"
else
    echo -e "${RED}✗${NC} API health check failed"
    FAILED=1
fi

echo ""

# Check dashboards exist
echo "3. Dashboard Files Check:"
echo "----------------------------"
DASH_COUNT=$(ssh "autobot@${HOST}" "ls /var/lib/grafana/dashboards/*.json 2>/dev/null | wc -l" 2>/dev/null || echo "0")
if [ "$DASH_COUNT" -ge 6 ]; then
    echo -e "${GREEN}✓${NC} Found ${DASH_COUNT} dashboard files"
else
    echo -e "${YELLOW}⚠${NC} Only found ${DASH_COUNT} dashboard files (expected at least 6)"
fi

echo ""

# Check dashboard provisioning
echo "4. Dashboard Provisioning Check:"
echo "----------------------------"
if ssh "autobot@${HOST}" "test -f /etc/grafana/provisioning/dashboards/default.yml" 2>/dev/null; then
    echo -e "${GREEN}✓${NC} Dashboard provisioning configured"
else
    echo -e "${RED}✗${NC} Dashboard provisioning not configured"
    FAILED=1
fi

echo ""

# Summary
echo "==================================="
if [ $FAILED -eq 0 ]; then
    echo -e "${GREEN}✓ All checks passed!${NC}"
    echo "Grafana is properly configured for iframe embedding."
    exit 0
else
    echo -e "${RED}✗ Some checks failed${NC}"
    echo ""
    echo "To fix, run:"
    echo "  cd autobot-slm-backend/ansible"
    echo "  ansible-playbook playbooks/deploy-slm-manager.yml -i inventory.ini --tags grafana"
    exit 1
fi
