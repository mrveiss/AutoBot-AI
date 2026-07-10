# Runbook: KB Redis Unreachable (Knowledge Base Degradation)

**Issue #5408** | Last updated: 2026-04-24

---

## Overview

This runbook describes how to detect, diagnose, and recover from the condition where the
AutoBot Knowledge Base (KB) cannot reach its Redis backend. When Redis is unreachable the KB
serves a degraded response: category counts are omitted, RAG feedback writes fail, and the
frontend shows an error banner.

**Related:** `docs/runbooks/SINGLE_HOST_DEPLOYMENT.md` (Redis setup, lines 282–304) |
`docs/operations/REDIS_SERVICE_RUNBOOK.md` (Redis service operations)

---

## Symptoms

| Signal | Details |
|--------|---------|
| Frontend error banner | `/knowledge/browser` shows "Knowledge base is unreachable" |
| Empty knowledge search | RAG queries return zero results; category counts show 0 |
| Prometheus counter | `autobot_kb_degradation_total{reason="redis_down"}` rate > 0 |
| Backend log line | `KB categories returning kb_connected=false - Redis unreachable` at WARNING level |
| Health endpoint | `GET /api/v1/system/health/detailed` returns `"redis": "unavailable"` |

Users may also report:
- "knowledge search returns nothing"
- "categories page shows error"
- RAG feedback submissions silently dropped

---

## Detection

### 1. Check the Prometheus alert

The `KBRedisUnreachable` alert fires when the counter rate exceeds 0 for 2 consecutive minutes:

```promql
rate(autobot_kb_degradation_total{reason="redis_down"}[5m]) > 0
```

If Alertmanager is configured, a `severity: warning` alert named `KBRedisUnreachable` routes to
the `redis-alerts` receiver.

### 2. Check backend logs

```bash
# Real-time: watch for the kb_connected=false warning
journalctl -u autobot-backend -f | grep "kb_connected"

# Historical: last 30 minutes
journalctl -u autobot-backend --since "30 minutes ago" | grep "kb_connected=false"

# All KB-related errors in the last hour
journalctl -u autobot-backend --since "1 hour ago" | grep -i "knowledge\|kb\|redis"
```

Expected log line when Redis is down:

```
WARNING knowledge.api - KB categories returning kb_connected=false - Redis unreachable
```

### 3. Check the health endpoint

```bash
# Requires admin token
curl -sk https://127.0.0.3:8001/api/v1/system/health/detailed \
  -H "Authorization: Bearer <admin-token>" | python3 -m json.tool
```

Look for `"redis": "unavailable"` in the `components` object. The `knowledge_base` component
shows `"available"` even when Redis is down (the KB module loads; only Redis connectivity fails).

### 4. Check Redis reachability directly

```bash
# Ping the KB Redis instance (loopback alias 127.0.0.7)
redis-cli -h 127.0.0.7 ping
# Expected: PONG

# Confirm the service is running
sudo systemctl status autobot-redis
```

---

## Immediate Mitigation

Work through these steps in order. Stop at the first step that restores Redis connectivity.

### Step 1: Restart Redis if it has crashed

```bash
sudo systemctl restart autobot-redis
# Wait ~5 seconds, then verify
redis-cli -h 127.0.0.7 ping
```

Check for OOM or crash signals in the Redis log:

```bash
journalctl -u autobot-redis --since "30 minutes ago" | tail -40
```

### Step 2: Check disk space (AOF / RDB overflow)

Redis stops accepting writes (and may fail to start) when the disk is full.

```bash
df -h /
df -h /var/lib/redis/  # or wherever the Redis data directory lives

# If disk is full, clear old logs (safe) to free space
sudo journalctl --vacuum-size=200M
sudo find /var/log/autobot/ -name "*.log" -mtime +7 -delete
```

If the AOF file is corrupted:

```bash
sudo redis-check-aof --fix /var/lib/redis/appendonly.aof
sudo systemctl restart autobot-redis
```

### Step 3: Check the loopback alias (127.0.0.7)

AutoBot single-host deployments bind Redis to a loopback alias (`127.0.0.7`). If the alias
is missing (e.g., after a reboot without persistent network config), Redis is unreachable even
though `autobot-redis.service` reports active.

```bash
ip addr show lo | grep 127.0.0.7
# Expected: inet 127.0.0.7/8 scope host lo

# If missing, re-add it:
sudo ip addr add 127.0.0.7/8 dev lo
```

To make the alias persistent after reboots, see `SINGLE_HOST_DEPLOYMENT.md` section 4
(network configuration).

### Step 4: Check iptables / firewall rules

```bash
# Verify nothing is blocking port 6379 on loopback
sudo iptables -L INPUT -n | grep 6379

# If a DROP rule exists for 127.0.0.7:6379, remove it:
sudo iptables -D INPUT -d 127.0.0.7 -p tcp --dport 6379 -j DROP
```

### Step 5: Run Ansible to restore config drift

If the Redis service config has drifted (wrong bind address, wrong port, missing password):

```bash
# From the AutoBot control node / SLM manager
ansible-playbook playbooks/deploy-redis.yml -i inventory/production.yml
```

This re-renders the Redis config from Ansible templates and restarts the service.

### Step 6: Restart the backend after Redis is restored

The backend holds its Redis client in memory. After Redis recovers, the client reconnects
automatically on the next request. If the banner persists for more than 30 seconds after Redis
is confirmed reachable, restart the backend to force client re-initialization:

```bash
sudo systemctl restart autobot-backend
# Verify recovery
journalctl -u autobot-backend -f | grep "KB\|Redis" | head -20
```

---

## Root Cause Investigation

### Common causes

| Cause | Indicator |
|-------|-----------|
| Redis OOM / crash | `journalctl -u autobot-redis` shows `SIGKILL` or `OOM` |
| Disk full (AOF) | `df -h` shows 100% on Redis data volume |
| Loopback alias missing | `ip addr show lo` lacks `127.0.0.7` |
| iptables DROP rule | `iptables -L` shows block on port 6379 |
| Config drift | `redis-cli -h 127.0.0.7 ping` fails but `systemctl status` is active |
| Redis password mismatch | Redis log shows `WRONGPASS` or `ERR Client sent AUTH` |
| Memory limit hit (maxmemory) | `redis-cli -h 127.0.0.7 info memory` shows `maxmemory_human` near limit |

### Useful queries

```bash
# Check Redis memory usage
redis-cli -h 127.0.0.7 info memory | grep -E "used_memory_human|maxmemory_human|mem_fragmentation"

# Check connected clients and keyspace
redis-cli -h 127.0.0.7 info clients
redis-cli -h 127.0.0.7 info keyspace

# Check slow log for latency spikes
redis-cli -h 127.0.0.7 slowlog get 10

# Count KB-specific keys
redis-cli -h 127.0.0.7 -n 1 dbsize  # KB uses database index 1 (DATABASE_MAPPING["knowledge"])

# Tail Redis log for error patterns
journalctl -u autobot-redis --since "1 hour ago" | grep -iE "error|warn|oom|killed"
```

### Backend log queries

```bash
# Count Redis-down events in the last hour
journalctl -u autobot-backend --since "1 hour ago" | grep -c "kb_connected=false"

# Full context around each event (5 lines of context)
journalctl -u autobot-backend --since "1 hour ago" | grep -A5 -B5 "kb_connected=false"

# Check if the issue recurs after restart (indicates persistent root cause)
journalctl -u autobot-backend --since "30 minutes ago" | grep -E "KB.*Redis|redis.*KB|degradation"
```

---

## Alert Routing

The `KBRedisUnreachable` Prometheus alert is defined in
`autobot-infrastructure/shared/config/prometheus/alertmanager_rules.yml` under the
`autobot_kb_degradation` group.

| Property | Value |
|----------|-------|
| Alert name | `KBRedisUnreachable` |
| Prometheus metric | `autobot_kb_degradation_total{reason="redis_down"}` |
| Expression | `rate(autobot_kb_degradation_total{reason="redis_down"}[5m]) > 0` |
| Pending period | 2 minutes |
| Severity | `warning` |
| Component label | `knowledge_base` |
| Alertmanager receiver | `redis-alerts` |
| Repeat interval | 30 minutes |

Alertmanager routes all `component: redis` and `component: knowledge_base` alerts to the
`redis-alerts` receiver, which forwards to the AutoBot webhook at
`http://localhost:8001/api/webhook/alertmanager`. The webhook broadcasts the alert to the
frontend via WebSocket.

The alert resolves automatically when `rate(autobot_kb_degradation_total{reason="redis_down"}[5m])`
returns to 0 (no new Redis-down events for the 5-minute window).

---

## Escalation

Page the on-call engineer if **any** of the following are true:

- Redis has not recovered within **15 minutes** of following this runbook
- Redis crashes repeatedly (3+ restarts in 1 hour)
- Disk space cannot be freed without data loss
- The loopback alias cannot be restored without rebooting the host
- Multiple components are degraded simultaneously (Redis + backend + ChromaDB)
- Any security alert fires concurrently with this alert

Provide the following to on-call:
1. Output of `sudo systemctl status autobot-redis`
2. Last 50 lines: `journalctl -u autobot-redis --since "1 hour ago" | tail -50`
3. Redis info: `redis-cli -h 127.0.0.7 info all 2>&1`
4. Backend log window: `journalctl -u autobot-backend --since "30 minutes ago" | grep -i redis`

---

## Post-Incident Actions

After service is restored:

1. **Confirm recovery** — verify `redis-cli -h 127.0.0.7 ping` returns `PONG` and the frontend
   no longer shows the error banner.

2. **Verify counter reset** — check Prometheus:
   ```promql
   rate(autobot_kb_degradation_total{reason="redis_down"}[5m])
   ```
   Should return 0.

3. **Write an incident note** — record in `docs/developer/audits/` if the outage reveals a
   systemic issue (e.g., Redis memory limit too low, loopback alias not persistent, AOF growing
   unbounded). File a GitHub issue with the `tech-debt` label if configuration changes are needed.

4. **Consider Ansible remediation** — if config drift caused the outage, run the deploy playbook
   immediately and verify idempotent re-runs do not break the loopback alias or service:
   ```bash
   ansible-playbook playbooks/deploy-redis.yml -i inventory/production.yml --check
   ansible-playbook playbooks/deploy-redis.yml -i inventory/production.yml
   ```
