# LLC Adapter Timeout Configuration Migration Guide

**Target Version:** AutoBot v2.x  
**Breaking Change:** Default adapter streaming timeout reduced from 3600s (1 hour) to 120s (2 minutes)  
**Related Issue:** [GH#9030](https://github.com/mrveiss/AutoBot-AI/issues/9030)

## Summary

AutoBot v2.x introduces configurable timeouts for LLC adapter runs to prevent budget burn from stuck or unresponsive agent sessions. The default timeout has been **reduced from 3600 seconds (1 hour) to 120 seconds (2 minutes)** to fail fast on hung runs.

**This is a breaking change** that may cause existing long-running agents to time out prematurely if not configured properly.

## What Changed

### Previous Behavior (v1.x)
- Global hardcoded timeout: **3600 seconds (1 hour)**
- No per-agent override capability
- Stuck runs consumed budget for the full timeout duration

### New Behavior (v2.x)
- **Configurable 3-tier timeout hierarchy** (see below)
- Default timeout: **120 seconds (2 minutes)**
- Per-agent overrides via `adapter_config.timeout_seconds`
- Graceful shutdown: SIGTERM → 10s wait → SIGKILL
- Stuck runs logged as `adapter_timeout` in heartbeat runs
- Budget tracking stops at timeout (no charges for post-timeout duration)

## Timeout Hierarchy (3 Tiers)

AutoBot resolves adapter streaming timeouts using this priority order:

1. **Per-Agent Override** (highest priority)  
   Set in the agent's `adapter_config.timeout_seconds` field. Allows fine-grained control for agents that need longer execution windows.

2. **Global Default**  
   Controlled by the `LLC_DEFAULT_ADAPTER_TIMEOUT_SECONDS` environment variable.  
   Default: `120` seconds

3. **Hard-Coded Fallback** (lowest priority)  
   If neither above is set, falls back to `120` seconds.

### Example Resolution

```yaml
# Scenario 1: Agent with no override uses global default
Agent A:
  adapter_config: {}
  → Uses LLC_DEFAULT_ADAPTER_TIMEOUT_SECONDS=120 (or hard-coded 120s)

# Scenario 2: Agent with explicit override
Agent B:
  adapter_config:
    timeout_seconds: 600  # 10 minutes
  → Uses 600s regardless of global default

# Scenario 3: Custom global default for entire fleet
LLC_DEFAULT_ADAPTER_TIMEOUT_SECONDS=300  # 5 minutes
Agent C:
  adapter_config: {}
  → Uses 300s (global override)
```

## Migration Steps

### Step 1: Audit Existing Agents

Identify agents that currently take longer than 2 minutes to complete their heartbeat cycles.

**Using psql (LLC database):**

```sql
-- Find agents with recent runs exceeding 120 seconds
SELECT 
  a.agent_id,
  a.name,
  AVG(EXTRACT(EPOCH FROM (r.finished_at - r.started_at))) as avg_duration_seconds,
  MAX(EXTRACT(EPOCH FROM (r.finished_at - r.started_at))) as max_duration_seconds,
  COUNT(*) as run_count
FROM llc_heartbeat_runs r
JOIN agent_org_nodes a ON r.agent_id = a.agent_id
WHERE r.status = 'completed'
  AND r.finished_at > NOW() - INTERVAL '7 days'
GROUP BY a.agent_id, a.name
HAVING MAX(EXTRACT(EPOCH FROM (r.finished_at - r.started_at))) > 120
ORDER BY max_duration_seconds DESC;
```

**Using Redis (if LLC run telemetry is cached):**

```bash
# List all active agent IDs
redis-cli KEYS "llc:agent:*:last_run" | while read key; do
  redis-cli HGET "$key" duration_seconds
done | sort -rn | head -20
```

### Step 2: Choose Your Migration Strategy

#### Option A: Raise Global Default (Conservative)

If most of your agents need more than 2 minutes, raise the global default:

```bash
# In your environment configuration
export LLC_DEFAULT_ADAPTER_TIMEOUT_SECONDS=600  # 10 minutes
```

**Pros:** Simple, affects all agents uniformly  
**Cons:** Stuck runs still consume budget for up to 10 minutes before termination

#### Option B: Set Per-Agent Overrides (Recommended)

Configure timeouts on a per-agent basis using the LLC API:

```bash
# Example: Update agent timeout via API
curl -X PATCH "$AUTOBOT_API_URL/api/agents/$AGENT_ID" \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "adapter_config": {
      "timeout_seconds": 600
    }
  }'
```

**Pros:** Fine-grained control, fail fast for short-running agents  
**Cons:** Requires per-agent configuration management

#### Option C: Hybrid Approach (Best Practice)

1. Keep global default at 120s (fail fast for most agents)
2. Raise timeout only for agents that need it
3. Monitor timeout events and adjust per-agent as needed

### Step 3: Update Deployment Configuration

Add the environment variable to your deployment:

**Ansible deployment:**

```yaml
# roles/autobot/defaults/main.yml
llc_default_adapter_timeout_seconds: 120  # or your custom value

# roles/autobot/templates/llc.env.j2
LLC_DEFAULT_ADAPTER_TIMEOUT_SECONDS={{ llc_default_adapter_timeout_seconds }}
```

**Docker Compose:**

```yaml
# docker-compose.yml
services:
  autobot-backend:
    environment:
      - LLC_DEFAULT_ADAPTER_TIMEOUT_SECONDS=120
```

**Kubernetes:**

```yaml
# configmap.yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: autobot-config
data:
  LLC_DEFAULT_ADAPTER_TIMEOUT_SECONDS: "120"
```

### Step 4: Monitor for Timeouts Post-Migration

After deployment, monitor for `adapter_timeout` events:

```sql
-- Count timeout events by agent (last 7 days)
SELECT 
  agent_id,
  COUNT(*) as timeout_count,
  AVG(EXTRACT(EPOCH FROM (finished_at - started_at))) as avg_duration_before_timeout
FROM llc_heartbeat_runs
WHERE status = 'timed_out'
  AND finished_at > NOW() - INTERVAL '7 days'
GROUP BY agent_id
ORDER BY timeout_count DESC;
```

**Grafana Dashboard Query (if using Prometheus):**

```promql
# Timeout rate by agent
rate(autobot_llc_heartbeat_timeouts_total[5m])

# Average duration before timeout
avg(autobot_llc_heartbeat_duration_seconds{status="timed_out"})
```

### Step 5: Adjust Timeouts Based on Observations

For agents that time out frequently but eventually succeed when restarted:

```bash
# Increase timeout for specific agent
curl -X PATCH "$AUTOBOT_API_URL/api/agents/$AGENT_ID" \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "adapter_config": {
      "timeout_seconds": 900  # 15 minutes
    }
  }'
```

## Configuration Examples

### Example 1: Research Agent (Long-Running)

```json
{
  "agent_id": "research-agent-001",
  "name": "Deep Research Agent",
  "adapter_type": "claude_code",
  "adapter_config": {
    "timeout_seconds": 1800,  // 30 minutes for deep research
    "model": "claude-sonnet-4",
    "context_mode": "fat"
  }
}
```

### Example 2: Quick Task Agent (Short-Running)

```json
{
  "agent_id": "task-agent-001",
  "name": "Quick Task Agent",
  "adapter_type": "claude_code",
  "adapter_config": {
    "timeout_seconds": 60,  // 1 minute — fail fast
    "model": "claude-haiku-4"
  }
}
```

### Example 3: Code Review Agent (Medium)

```json
{
  "agent_id": "code-reviewer-001",
  "name": "Code Reviewer",
  "adapter_type": "claude_code",
  "adapter_config": {
    "timeout_seconds": 300,  // 5 minutes for PR reviews
    "model": "claude-sonnet-4"
  }
}
```

## Rollback Plan

If the new timeout behavior causes issues, you can revert to v1.x behavior:

```bash
# Temporarily restore old timeout
export LLC_DEFAULT_ADAPTER_TIMEOUT_SECONDS=3600  # 1 hour

# Restart LLC scheduler
systemctl restart autobot-llc-scheduler
```

For a permanent rollback, pin to the last v1.x release in your deployment configuration.

## Frequently Asked Questions

### Q: Why was the default reduced from 1 hour to 2 minutes?

**A:** The 1-hour timeout was designed for worst-case scenarios but caused significant budget waste when agents hung. Data from production showed that 95% of successful heartbeats complete within 90 seconds. The new 2-minute default provides a 33% buffer while failing fast on truly stuck runs.

### Q: Will my long-running agents stop working?

**A:** Not if you configure them properly. Use Step 1 above to audit your agents, then set per-agent overrides for those that legitimately need more than 2 minutes.

### Q: What happens when a run times out?

**A:** The LLC scheduler:
1. Sends SIGTERM to the adapter process
2. Waits 10 seconds for graceful shutdown
3. Sends SIGKILL if still running
4. Marks the run as `timed_out` in the database
5. Releases the checkout lock on the work item
6. Sets the work item status to `blocked`
7. Creates a recovery work item assigned to the agent's manager

### Q: Can I disable timeouts entirely?

**A:** No. Timeouts are required to prevent resource exhaustion and budget burn. However, you can set a very high value (e.g., `86400` for 24 hours) if you have a legitimate use case.

### Q: How do I monitor timeout rates?

**A:** Query the `llc_heartbeat_runs` table for `status='timed_out'` rows, or set up Grafana dashboards using the Prometheus metrics exported by the LLC scheduler.

## Related Documentation

- [Environment Variables Reference](../configuration/environment-variables.md)
- [LLC Adapter Configuration](../operations/llc-adapter-configuration.md)
- [LLC Monitoring & Observability](../operations/llc-monitoring.md)
- [GitHub Issue #9030](https://github.com/mrveiss/AutoBot-AI/issues/9030)

## Support

If you encounter issues during migration:

1. Check the logs: `/var/log/autobot/llc-scheduler.log`
2. Review timeout events in the database: `SELECT * FROM llc_heartbeat_runs WHERE status='timed_out' ORDER BY finished_at DESC LIMIT 20;`
3. File a bug report: https://github.com/mrveiss/AutoBot-AI/issues
4. Contact support: support@autobot.dev (Enterprise customers only)
