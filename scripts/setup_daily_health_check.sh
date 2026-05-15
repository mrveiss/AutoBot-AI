#!/bin/bash
# Setup daily health check via cron job
# Run once to configure: bash scripts/setup_daily_health_check.sh

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HEALTH_CHECK="$SCRIPT_DIR/daily_health_check.py"
POST_CHECK="$SCRIPT_DIR/post_health_check.py"

# Make scripts executable
chmod +x "$HEALTH_CHECK" "$POST_CHECK"

# Create a wrapper script for cron
CRON_WRAPPER="/tmp/autobot-health-check-cron.sh"
cat > "$CRON_WRAPPER" <<'EOF'
#!/bin/bash
export PATH=/usr/local/sbin:/usr/local/sbin:/usr/bin:/bin
cd /home/martins/AutoBot-Ai/AutoBot-AI

# Run health check and post results
python3 scripts/daily_health_check.py 2>&1 | tee -a /var/log/autobot/health-check.log
python3 scripts/post_health_check.py 2>&1 | tee -a /var/log/autobot/health-check.log
EOF

chmod +x "$CRON_WRAPPER"

# Setup cron job: run daily at 3 AM
CRON_JOB="0 3 * * * $CRON_WRAPPER"
(crontab -l 2>/dev/null; echo "$CRON_JOB") | crontab - 2>/dev/null

if [ $? -eq 0 ]; then
    echo "✅ Daily health check configured to run at 3 AM daily"
    echo "   Wrapper script: $CRON_WRAPPER"
    echo "   Logs: /var/log/autobot/health-check.log"
else
    echo "❌ Failed to setup cron job"
    exit 1
fi

# Show current cron schedule
echo ""
echo "Current cron jobs:"
crontab -l 2>/dev/null | grep autobot-health-check || echo "  (no health-check job found - check crontab manually)"
