# LLC Adapter Configuration Guide

This guide covers configuration and tuning of LLC (Autonomous Agent) adapters in AutoBot.

## Overview

LLC adapters are the runtime components that execute autonomous agent heartbeats. Each adapter type (Claude Code, Copilot CLI, HTTP webhook, etc.) implements a standard protocol for invoke/status/cancel operations.

## Adapter Timeout Configuration

**Related:** [LLC Timeout Migration Guide](../migration/llc-timeout-configuration.md)

### Environment Variable

| Variable | Default | Description |
|----------|---------|-------------|
| `LLC_DEFAULT_ADAPTER_TIMEOUT_SECONDS` | `120` | Global default for adapter streaming timeouts. Agents that exceed this timeout without producing output are terminated and marked as `timed_out`. |

### Setting the Global Default

**Ansible deployment:**

```yaml
# group_vars/all.yml or host_vars/autobot-server.yml
llc_default_adapter_timeout_seconds: 120

# This variable is templated into /etc/autobot/llc.env
```

**Docker Compose:**

```yaml
# docker-compose.yml
services:
  autobot-backend:
    environment:
      - LLC_DEFAULT_ADAPTER_TIMEOUT_SECONDS=120
```

**systemd service:**

```bash
# /etc/autobot/llc.env
LLC_DEFAULT_ADAPTER_TIMEOUT_SECONDS=120
```

### Per-Agent Timeout Overrides

Individual agents can override the global default via their `adapter_config`:

```json
{
  "agent_id": "long-running-researcher",
  "name": "Deep Research Agent",
  "adapter_type": "claude_code",
  "adapter_config": {
    "timeout_seconds": 1800,  // 30 minutes override
    "model": "claude-sonnet-4",
    "context_mode": "fat"
  }
}
```

**Setting via API:**

```bash
curl -X PATCH "$AUTOBOT_API_URL/api/agents/$AGENT_ID" \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "adapter_config": {
      "timeout_seconds": 600
    }
  }'
```

**Setting via LLC Board UI:**

1. Navigate to **LLC Dashboard** → **Agents**
2. Select the agent to configure
3. Click **Edit** → **Adapter Config**
4. Set `timeout_seconds` field
5. Click **Save**

### Timeout Resolution Order

1. **Per-agent `adapter_config.timeout_seconds`** (highest priority)
2. **Global `LLC_DEFAULT_ADAPTER_TIMEOUT_SECONDS`** env var
3. **Hard-coded fallback** (120 seconds)

## Adapter Types

### Claude Code Adapter

Runs agents using Claude Code CLI sessions.

**Configuration:**

```json
{
  "adapter_type": "claude_code",
  "adapter_config": {
    "model": "claude-sonnet-4",
    "timeout_seconds": 300,
    "context_mode": "thin",  // or "fat" for full RAG context
    "max_retries": 3
  }
}
```

**Environment Requirements:**

- `claude` CLI installed and authenticated
- API key in `~/.claude/credentials`

### Copilot Local Adapter

Runs agents using GitHub Copilot CLI.

**Configuration:**

```json
{
  "adapter_type": "copilot_local",
  "adapter_config": {
    "timeout_seconds": 180,
    "context_mode": "thin"
  }
}
```

**Environment Requirements:**

- `gh copilot` CLI installed and authenticated
- GitHub token with Copilot access

### HTTP Adapter

Webhook-based adapter for external agent systems.

**Configuration:**

```json
{
  "adapter_type": "http",
  "adapter_config": {
    "endpoint": "https://external-agent.example.com/webhook",
    "timeout_seconds": 60,
    "auth_token": "secret-webhook-token",
    "retry_on_timeout": true
  }
}
```

### Process Adapter

Executes arbitrary shell commands as agents.

**Configuration:**

```json
{
  "adapter_type": "process",
  "adapter_config": {
    "command": "/usr/local/bin/my-custom-agent",
    "args": ["--mode", "heartbeat"],
    "timeout_seconds": 120,
    "env": {
      "CUSTOM_VAR": "value"
    }
  }
}
```

## Timeout Behavior

### What Happens When a Run Times Out

1. **SIGTERM sent** to adapter process (graceful shutdown)
2. **10-second grace period** for cleanup
3. **SIGKILL sent** if process still running
4. **Run marked as `timed_out`** in `llc_heartbeat_runs`
5. **Checkout lock released** (`DEL llc:checkout:{work_item_id}`)
6. **Work item set to `blocked`** status
7. **Recovery work item created** and assigned to agent's manager
8. **Activity log entry written** with `event_type=HEARTBEAT_FAILED`

### Budget Implications

- **Budget stops** at the timeout timestamp (no charges for post-timeout duration)
- Operators can configure `retry_on_timeout` per agent to automatically retry failed runs once

### Monitoring Timeouts

**Database query:**

```sql
-- Recent timeouts by agent
SELECT 
  agent_id,
  COUNT(*) as timeout_count,
  MAX(finished_at) as last_timeout,
  AVG(EXTRACT(EPOCH FROM (finished_at - started_at))) as avg_duration_seconds
FROM llc_heartbeat_runs
WHERE status = 'timed_out'
  AND finished_at > NOW() - INTERVAL '7 days'
GROUP BY agent_id
ORDER BY timeout_count DESC;
```

**Redis monitoring:**

```bash
# Check active runs
redis-cli KEYS "llc:run:*:status"

# Check checkout locks
redis-cli KEYS "llc:checkout:*"
```

**Prometheus metrics:**

```promql
# Timeout rate (5-minute window)
rate(autobot_llc_heartbeat_timeouts_total[5m])

# Average timeout duration by agent
avg by (agent_id) (autobot_llc_heartbeat_duration_seconds{status="timed_out"})
```

## Tuning Guidelines

### Short-Running Agents (< 2 minutes)

Use the default 120-second timeout or lower:

```json
{
  "adapter_config": {
    "timeout_seconds": 60  // 1 minute
  }
}
```

**Use cases:**
- Quick task completion agents
- Status check agents
- Simple data retrieval agents

### Medium-Running Agents (2-10 minutes)

Set timeout to 300-600 seconds:

```json
{
  "adapter_config": {
    "timeout_seconds": 300  // 5 minutes
  }
}
```

**Use cases:**
- Code review agents
- Document generation agents
- Light research agents

### Long-Running Agents (10+ minutes)

Set timeout to 600-1800 seconds or higher:

```json
{
  "adapter_config": {
    "timeout_seconds": 1800  // 30 minutes
  }
}
```

**Use cases:**
- Deep research agents
- Large codebase analysis
- Multi-step workflow agents

### Warning: Very Long Timeouts

Timeouts above 1 hour are discouraged unless absolutely necessary:

- Increases budget exposure from stuck runs
- May indicate the task should be decomposed into smaller work items
- Consider using multiple shorter heartbeats instead

## Troubleshooting

### Agent Times Out Despite Finishing on Time

**Symptom:** Run completes successfully locally but times out in production.

**Possible causes:**
1. Network latency to external APIs (LLM providers, GitHub, etc.)
2. Redis/database connection overhead
3. Cold-start penalties (first run after idle period)

**Solution:**
- Increase per-agent timeout by 50-100%
- Enable debug logging: `AUTOBOT_LOG_LEVEL=debug`
- Check for rate limiting in external APIs

### Timeout Too Aggressive (False Positives)

**Symptom:** Legitimate long-running agents get killed frequently.

**Solution:**
```bash
# Option 1: Raise global default
export LLC_DEFAULT_ADAPTER_TIMEOUT_SECONDS=300

# Option 2: Set per-agent override
curl -X PATCH "$API_URL/api/agents/$AGENT_ID" \
  -d '{"adapter_config": {"timeout_seconds": 600}}'
```

### Timeout Too Lenient (Budget Waste)

**Symptom:** Hung runs consume budget for extended periods.

**Solution:**
```bash
# Lower global default
export LLC_DEFAULT_ADAPTER_TIMEOUT_SECONDS=90

# Audit agent performance (see Migration Guide Step 1)
# Set aggressive per-agent timeouts for quick tasks
```

### Recovery Work Items Not Created

**Symptom:** Timed-out runs don't generate recovery tasks.

**Possible causes:**
1. Agent has no manager assigned
2. LLC activity log service not running
3. Database permissions issue

**Check logs:**
```bash
tail -f /var/log/autobot/llc-scheduler.log | grep "recovery"
```

## Advanced Configuration

### Retry on Timeout

Enable automatic retry for agents that may timeout due to transient issues:

```json
{
  "adapter_config": {
    "timeout_seconds": 120,
    "retry_on_timeout": true,
    "max_retries": 1  // Retry once, then mark as failed
  }
}
```

### Graceful Shutdown Period

The default 10-second grace period can be adjusted (requires code change in `liveness_monitor.py`):

```python
# autobot-backend/llc/scheduler/liveness_monitor.py
_GRACEFUL_SHUTDOWN_SECONDS = 10  # Increase if agents need more cleanup time
```

### Custom Timeout Metrics

Export custom Prometheus metrics for timeout analysis:

```python
from prometheus_client import Counter

timeout_counter = Counter(
    'llc_custom_timeout_reason',
    'Custom timeout reason tracking',
    ['agent_id', 'reason']
)

# Usage in adapter code
timeout_counter.labels(agent_id=agent_id, reason='api_rate_limit').inc()
```

## Best Practices

1. **Start conservative:** Use the default 120s timeout initially
2. **Monitor for 1 week:** Collect timeout data before tuning
3. **Increase incrementally:** Add 50-100s at a time, not 10x jumps
4. **Document overrides:** Note why specific agents need longer timeouts
5. **Review quarterly:** Timeout requirements change as agent code evolves
6. **Alert on spikes:** Set up alerts for sudden increases in timeout rates

## Related Documentation

- [LLC Timeout Migration Guide](../migration/llc-timeout-configuration.md)
- [Environment Variables Reference](../configuration/environment-variables.md)
- [LLC Monitoring & Observability](llc-monitoring.md)
- [Scaling Strategy](scaling-strategy.md)

## Support

For LLC adapter configuration issues:

- **Logs:** `/var/log/autobot/llc-scheduler.log`
- **Database:** `SELECT * FROM llc_heartbeat_runs ORDER BY started_at DESC LIMIT 50;`
- **GitHub Issues:** https://github.com/mrveiss/AutoBot-AI/issues
- **Enterprise Support:** support@autobot.dev
