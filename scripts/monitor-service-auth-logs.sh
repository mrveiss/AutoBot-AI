#!/bin/bash
# Monitor service authentication logs across all VMs

echo "🔍 Service Authentication Log Monitor"
echo "===================================="
echo "Monitoring mode: LOGGING (Day 2)"
echo "Press Ctrl+C to stop"
echo ""

# Color codes
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Monitor local backend logs
echo -e "${BLUE}=== Main Backend (172.16.168.20) ===${NC}"
if [ -f /var/log/autobot/backend.log ]; then
    tail -20 /var/log/autobot/backend.log | grep -i "auth" || echo "No auth logs yet"
elif [ -f logs/backend.log ]; then
    tail -20 logs/backend.log | grep -i "auth" || echo "No auth logs yet"
else
    echo "No backend logs found"
fi
echo ""

# Monitor each VM
for vm in frontend:172.16.168.21 npu:172.16.168.22 redis:172.16.168.23 aiml:172.16.168.24 browser:172.16.168.25; do
    IFS=':' read -r name ip <<< "$vm"
    echo -e "${BLUE}=== ${name^} ($ip) ===${NC}"

    ssh -i ~/.ssh/autobot_key autobot@$ip \
        "tail -20 /var/log/autobot/*.log 2>/dev/null | grep -i auth || echo 'No auth logs yet'" 2>/dev/null || echo "Cannot connect to $name"

    echo ""
done

echo ""
echo -e "${GREEN}=== Live Monitoring (Ctrl+C to stop) ===${NC}"
echo ""

# Follow backend logs in real-time
if [ -f logs/backend.log ]; then
    tail -f logs/backend.log | grep --line-buffered -i "auth\|service.*key\|x-service"
elif [ -f /var/log/autobot/backend.log ]; then
    tail -f /var/log/autobot/backend.log | grep --line-buffered -i "auth\|service.*key\|x-service"
else
    echo "No logs to monitor - start backend first"
fi
