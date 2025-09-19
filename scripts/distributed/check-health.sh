#!/bin/bash
# Check health of all distributed AutoBot services

echo "🏥 AutoBot Distributed Services Health Check"
echo "============================================="

declare -A SERVICES=(
    ["Backend (Local)"]="127.0.0.1:8001/api/health"
    ["Redis VM"]="172.16.168.23:6379"
    ["NPU Worker VM"]="172.16.168.22:8081/health" 
    ["Frontend VM"]="172.16.168.21:5173"
    ["AI Stack VM"]="172.16.168.24:8080/health"
    ["Browser VM"]="172.16.168.25:3000/health"
    ["Ollama (Local)"]="127.0.0.1:11434/api/tags"
)

for service_name in "${!SERVICES[@]}"; do
    endpoint="${SERVICES[$service_name]}"
    echo -n "Checking $service_name... "
    
    if [[ $endpoint == *":"*"/api/"* ]] || [[ $endpoint == *":"*"/health"* ]]; then
        # HTTP endpoint
        if curl -s --max-time 5 "http://$endpoint" >/dev/null 2>&1; then
            echo "✅ OK"
        else
            echo "❌ Failed"
        fi
    else
        # TCP port check
        IFS=':' read -r host port <<< "$endpoint"
        if nc -z -w3 "$host" "$port" 2>/dev/null; then
            echo "✅ OK"
        else
            echo "❌ Failed"
        fi
    fi
done

echo ""
echo "🔗 Service URLs:"
echo "  Backend API: http://172.16.168.20:8002"
echo "  Frontend: http://172.16.168.21:5173"  
echo "  Redis Insight: http://172.16.168.23:8002"
echo "  AI Stack: http://172.16.168.24:8080"
echo "  NPU Worker: http://172.16.168.22:8081"
echo "  Browser Service: http://172.16.168.25:3000"
echo "  Ollama: http://127.0.0.1:11434"
echo "  VNC Desktop: http://127.0.0.1:6080"

echo ""
echo "📊 Distributed Architecture Status:"
echo "  Main WSL (172.16.168.20): Backend API + Ollama + VNC"
echo "  Frontend VM (172.16.168.21): Vue.js Web Interface"
echo "  NPU Worker VM (172.16.168.22): Intel OpenVINO + Hardware Acceleration"
echo "  Redis VM (172.16.168.23): Redis Stack + Vector Storage"
echo "  AI Stack VM (172.16.168.24): AI Processing Services"
echo "  Browser VM (172.16.168.25): Playwright Automation"

echo ""
echo "🧪 Testing Distributed Redis Connection:"
cd /home/kali/Desktop/AutoBot
if python src/utils/distributed_redis_client.py 2>/dev/null | grep -q "connection working correctly"; then
    echo "  Redis Connection: ✅ OK"
else
    echo "  Redis Connection: ❌ Failed"
fi