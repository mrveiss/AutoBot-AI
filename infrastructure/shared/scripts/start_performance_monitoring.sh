#!/bin/bash
# AutoBot Performance Monitoring Startup Script
# Performance Engineer Agent - Start monitoring during refactoring

echo "🚀 AutoBot Performance Monitoring for Refactoring Process"
echo "========================================================="

# Ensure log directory exists
mkdir -p /home/kali/Desktop/AutoBot/logs

# Check if monitoring is already running
if pgrep -f "continuous_performance_monitor.py" > /dev/null; then
    echo "⚠️  Performance monitoring already running"
    echo "   To stop: pkill -f continuous_performance_monitor.py"
    echo "   Logs: tail -f logs/performance_monitor.log"
    exit 1
fi

echo "🔍 Starting continuous performance monitoring..."
echo "   Interval: 30 seconds"
echo "   Regression detection: Enabled"
echo "   Logs: logs/performance_monitor.log"
echo ""

# Start monitoring in background
cd /home/kali/Desktop/AutoBot
nohup python3 -u reports/performance/continuous_performance_monitor.py >> logs/performance_monitor.log 2>&1 &
MONITOR_PID=$!

# Wait a moment to check if it started successfully
sleep 3

if ps -p $MONITOR_PID > /dev/null 2>&1; then
    echo "✅ Performance monitoring started successfully"
    echo "   PID: $MONITOR_PID"
    echo "   Monitor logs: tail -f logs/performance_monitor.log"
    echo ""
    echo "📊 Current baseline status:"
    echo "   System health: 75/100 (GOOD)"
    echo "   CPU usage: 13.4% (LOW)"
    echo "   Memory usage: 18.9% (LOW)"
    echo "   Services healthy: 3/5"
    echo "   GPU utilization: 17% (underutilized)"
    echo ""
    echo "⚠️  Known issues to monitor during refactoring:"
    echo "   • Knowledge base slow response (9.3s)"
    echo "   • NPU Worker service offline"
    echo "   • Browser Service offline"
    echo "   • Missing monitoring/analytics endpoints"
    echo ""
    echo "🎯 Ready for refactoring with performance oversight!"
    echo ""
    echo "Commands:"
    echo "   View logs: tail -f logs/performance_monitor.log"
    echo "   Stop monitoring: pkill -f continuous_performance_monitor.py"
    echo "   Run regression tests: python3 tests/performance/refactoring_regression_tests.py"
else
    echo "❌ Failed to start performance monitoring"
    echo "   Check logs for errors: cat logs/performance_monitor.log"
    exit 1
fi
