#!/bin/bash
# Start Seq with Comprehensive AutoBot Analytics
# ============================================
# Starts Seq with proper configuration and starts log forwarding.

set -e

echo "🚀 Starting Seq with AutoBot Analytics Configuration"

# Check if Seq container exists and is running
if ! docker ps | grep -q autobot-log-viewer; then
    echo "❌ Seq container (autobot-log-viewer) is not running"
    echo "Please start it with: docker-compose up -d"
    exit 1
fi

echo "✅ Seq container is running"

# Wait for Seq to be ready
echo "⏳ Waiting for Seq to be ready..."
timeout 30 bash -c '
    while ! curl -s http://localhost:5341/api >/dev/null; do
        sleep 1
    done
'

if [ $? -eq 0 ]; then
    echo "✅ Seq is ready at http://localhost:5341"
else
    echo "❌ Seq failed to start properly"
    exit 1
fi

# Check Seq version and status
SEQ_INFO=$(curl -s http://localhost:5341/api)
SEQ_VERSION=$(echo "$SEQ_INFO" | grep -o '"Version":"[^"]*"' | cut -d'"' -f4)
echo "📊 Seq Version: $SEQ_VERSION"

# Start log forwarder in background
echo "🔄 Starting AutoBot log forwarder..."
python scripts/simple_docker_log_forwarder.py &
LOG_FORWARDER_PID=$!
echo "✅ Log forwarder started (PID: $LOG_FORWARDER_PID)"

# Wait a bit for logs to start flowing
sleep 3

# Test log ingestion
echo "🧪 Testing log ingestion..."
curl -s -X POST http://localhost:5341/api/events/raw \
  -H "Content-Type: application/vnd.serilog.clef" \
  -d '{"@t":"'"$(date -u +%Y-%m-%dT%H:%M:%S.%3NZ)"'","@l":"Information","@mt":"AutoBot Seq Analytics Test - System Ready","Source":"AutoBot-Analytics","Application":"AutoBot","TestEvent":true}'

if [ $? -eq 0 ]; then
    echo "✅ Test log sent successfully"
else
    echo "⚠️  Test log failed"
fi

echo ""
echo "🎉 AutoBot Seq Analytics Started!"
echo "   🌐 Seq Dashboard: http://localhost:5341"
echo "   📊 Default Login: admin / Autobot123! (if required)"
echo "   🔄 Log Forwarder PID: $LOG_FORWARDER_PID"
echo ""
echo "📋 To stop log forwarder: kill $LOG_FORWARDER_PID"
echo "📋 To view logs in real-time: tail -f /dev/null (or use Seq dashboard)"

# Save PID for cleanup
echo $LOG_FORWARDER_PID > /tmp/autobot_log_forwarder.pid
echo "💾 Forwarder PID saved to /tmp/autobot_log_forwarder.pid"

echo ""
echo "🔍 Manual Seq Analytics Setup:"
echo "   1. Open http://localhost:5341 in browser"
echo "   2. Create queries using config/seq-basic-queries.json"
echo "   3. Create dashboards for system monitoring"
echo "   4. Set up alerts for critical errors"

wait $LOG_FORWARDER_PID
