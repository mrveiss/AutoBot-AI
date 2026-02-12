#!/bin/bash
# AutoBot Grafana Health Check
# Usage: ./check-grafana-health.sh [grafana_host] [grafana_port]
#
# Examples:
#   ./check-grafana-health.sh                    # Local (127.0.0.1:3000)
#   ./check-grafana-health.sh 172.16.168.28      # External VM
#   ./check-grafana-health.sh 172.16.168.28 3000 # External with port

GRAFANA_HOST="${1:-127.0.0.1}"
GRAFANA_PORT="${2:-3000}"
GRAFANA_URL="http://${GRAFANA_HOST}:${GRAFANA_PORT}"

echo "=== AutoBot Grafana Health Check ==="
echo "Target: ${GRAFANA_URL}"
echo ""

# 1. Service Status (only if checking local)
if [ "$GRAFANA_HOST" = "127.0.0.1" ] || [ "$GRAFANA_HOST" = "localhost" ]; then
    echo "1. Service Status:"
    if systemctl is-active --quiet grafana-server; then
        echo "✅ Grafana service is running"
    else
        echo "❌ Grafana service is stopped"
        exit 1
    fi
    echo ""
fi

# 2. API Health
echo "2. API Health:"
HEALTH_RESPONSE=$(curl -s "${GRAFANA_URL}/api/health")
if echo "$HEALTH_RESPONSE" | jq -e . >/dev/null 2>&1; then
    echo "$HEALTH_RESPONSE" | jq
    if echo "$HEALTH_RESPONSE" | jq -e '.database == "ok"' >/dev/null 2>&1; then
        echo "✅ API is healthy"
    else
        echo "⚠️ API responding but database may have issues"
    fi
else
    echo "❌ API health check failed"
    echo "Response: $HEALTH_RESPONSE"
    exit 1
fi
echo ""

# 3. Dashboard Count
echo "3. Dashboards:"
DASH_COUNT=$(curl -s "${GRAFANA_URL}/api/search" | jq '. | length' 2>/dev/null)
if [ -n "$DASH_COUNT" ] && [ "$DASH_COUNT" -gt 0 ]; then
    echo "✅ Found $DASH_COUNT dashboards"
    curl -s "${GRAFANA_URL}/api/search" | jq -r '.[] | "  - \(.title) (uid: \(.uid))"'
else
    echo "⚠️ No dashboards found or unable to retrieve"
fi
echo ""

# 4. Data Sources
echo "4. Data Sources:"
DATASOURCES=$(curl -s "${GRAFANA_URL}/api/datasources")
if echo "$DATASOURCES" | jq -e '. | length > 0' >/dev/null 2>&1; then
    echo "$DATASOURCES" | jq -r '.[] | "✅ \(.name): \(.url) (type: \(.type))"'
else
    echo "⚠️ No data sources configured"
fi
echo ""

# 5. Test Dashboard Access (via proxy if available)
echo "5. Dashboard Access (via nginx proxy):"
PROXY_BASE="https://172.16.168.19/grafana"
for dash in autobot-system autobot-overview autobot-performance autobot-multi-machine autobot-redis autobot-api-health; do
    STATUS=$(curl -k -s -o /dev/null -w "%{http_code}" "${PROXY_BASE}/d/${dash}?kiosk=tv" 2>/dev/null)
    if [ "$STATUS" = "200" ]; then
        echo "✅ ${dash}"
    elif [ "$STATUS" = "000" ]; then
        echo "⚠️ ${dash} (proxy not accessible from this host)"
    else
        echo "❌ ${dash} (HTTP ${STATUS})"
    fi
done
echo ""

# 6. Configuration Check (only if checking local)
if [ "$GRAFANA_HOST" = "127.0.0.1" ] || [ "$GRAFANA_HOST" = "localhost" ]; then
    echo "6. Configuration:"
    if [ -f /etc/grafana/grafana.ini ]; then
        echo "Checking critical settings..."

        if grep -q "^serve_from_sub_path = true" /etc/grafana/grafana.ini 2>/dev/null; then
            echo "✅ serve_from_sub_path = true"
        else
            echo "❌ serve_from_sub_path not enabled (required for /grafana/ subpath)"
        fi

        if grep -A2 "\[auth.anonymous\]" /etc/grafana/grafana.ini | grep -q "^enabled = true" 2>/dev/null; then
            echo "✅ Anonymous auth enabled"
        else
            echo "⚠️ Anonymous auth disabled (may require login)"
        fi

        if grep -A5 "\[security\]" /etc/grafana/grafana.ini | grep -q "^allow_embedding = true" 2>/dev/null; then
            echo "✅ Iframe embedding allowed"
        else
            echo "⚠️ Iframe embedding not enabled (required for dashboard embedding)"
        fi
    else
        echo "⚠️ Cannot access /etc/grafana/grafana.ini"
    fi
    echo ""
fi

echo "=== Health Check Complete ==="
echo ""
echo "For troubleshooting, see:"
echo "  - docs/infrastructure/GRAFANA_EXTERNAL_HOST_SETUP.md"
echo "  - docs/infrastructure/GRAFANA_QUICK_REFERENCE.md"
