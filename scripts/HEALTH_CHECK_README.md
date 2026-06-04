# AutoBot Daily Health Check

Automated daily health check for the AutoBot stack that monitors 7 critical components and files issues for any anomalies.

## Components Checked

1. **Services Status** - Verifies all required systemd services are running
2. **Backend API** - Tests `/health` endpoint of the backend service
3. **ChromaDB** - Checks ChromaDB heartbeat endpoint
4. **SLM Health** - Verifies SLM backend health
5. **Error Logs** - Monitors error log frequency over last 24 hours
6. **Disk Usage** - Checks root filesystem usage (alerts if >85%)
7. **Redis** - Verifies Redis connectivity

## Usage

### Manual Run

```bash
# Run health check
python3 scripts/daily_health_check.py

# Post results to MVA-12 and file issues
python3 scripts/post_health_check.py

# Or run both in sequence
python3 scripts/daily_health_check.py && python3 scripts/post_health_check.py
```

### Automated Daily Execution

```bash
# Setup cron job (runs daily at 3 AM)
bash scripts/setup_daily_health_check.sh

# View cron schedule
crontab -l | grep autobot-health-check

# View health check logs
tail -f /var/log/autobot/health-check.log
```

## Output

Results are saved to `/tmp/autobot-health-check.md` with:
- Overall health status (✅ HEALTHY / ⚠️ ISSUES DETECTED)
- Detailed checklist results for each component
- List of detected issues

## Issue Filing

When anomalies are detected, the system:

1. Posts a summary comment to MVA-12 (if it exists)
2. Files individual `discovery(health-check)` GitHub issues for each critical failure

## Configuration

Environment variables can be set to customize endpoints:

```bash
export AUTOBOT_BACKEND_URL=http://localhost:8001
export CHROMADB_URL=http://localhost:8100
export SLM_URL=http://localhost:8000
```

## Thresholds

- **Disk Usage Alert**: Triggered when usage > 85%
- **Error Log Alert**: Triggered when > 20 errors in last 24 hours

## Integration with MVA-12

The health check is designed to post daily findings to issue MVA-12. If MVA-12 doesn't exist, it creates a standalone discovery issue instead.

To enable GitHub posting, ensure `gh` CLI is configured:

```bash
gh auth status
```

## Troubleshooting

If health check reports are not posting:

1. Check GitHub CLI auth: `gh auth status`
2. Verify issue number exists: `gh issue view 12`
3. Check logs: `tail /var/log/autobot/health-check.log`
4. Test manually:
   ```bash
   python3 scripts/daily_health_check.py
   cat /tmp/autobot-health-check.md
   python3 scripts/post_health_check.py
   ```

## Files

- `scripts/daily_health_check.py` - Main health check logic
- `scripts/post_health_check.py` - Posts results to GitHub
- `scripts/setup_daily_health_check.sh` - Configures daily cron job
- `/var/log/autobot/health-check.log` - Health check execution logs
