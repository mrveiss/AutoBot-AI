# NPU Worker Pool API

**Issue**: #168
**Status**: Implemented
**Version**: 1.0.0

## Overview

The NPU Worker Pool provides health-aware load balancing across multiple NPU workers with automatic failover and circuit breaker protection. It extends the existing `NPUWorkerClient` and `NPUTaskQueue` to transparently support multiple workers.

## Architecture

```
NPUTaskQueue → NPUWorkerPool → NPUWorkerClient instances
```

**Key Features**:
- Priority-first + least-connections load balancing
- Hybrid health monitoring (background + on-demand)
- Conservative circuit breaker (5 failures, 60s cooldown)
- Automatic retry with worker exclusion (max 3 attempts)
- Zero breaking changes to existing code

## Configuration

**Location**: `config/npu_workers.yaml`

```yaml
npu:
  workers:
    - id: npu-worker-vm2
      host: 172.16.168.22
      port: 8081
      priority: 10
      enabled: true
      max_concurrent_tasks: 4

    - id: windows-npu-worker
      host: 172.16.168.20
      port: 8082
      priority: 5
      enabled: true
      max_concurrent_tasks: 4
```

**Field Descriptions**:

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `id` | string | Yes | Unique worker identifier |
| `host` | string | Yes | Worker hostname or IP |
| `port` | int | Yes | Worker port |
| `priority` | int (1-10) | No | Higher = preferred (default: 5) |
| `enabled` | boolean | Yes | Enable/disable worker |
| `max_concurrent_tasks` | int | No | Worker capacity limit |

## API Endpoints

All endpoints require admin authentication (Issue #744).

### GET /api/npu/pool/stats

Get pool-level statistics.

**Response**:
```json
{
  "total_workers": 2,
  "healthy_workers": 2,
  "total_tasks_processed": 1523,
  "active_tasks": 12,
  "success_rate": 0.997
}
```

### GET /api/npu/pool/workers

Get per-worker health states.

**Response**:
```json
{
  "workers": [
    {
      "id": "npu-worker-vm2",
      "url": "http://172.16.168.22:8081",
      "priority": 10,
      "enabled": true,
      "healthy": true,
      "circuit_state": "closed",
      "active_tasks": 8,
      "total_requests": 1023,
      "failures": 0,
      "last_health_check": 1738713245.32
    }
  ]
}
```

### POST /api/npu/pool/reload

Hot-reload configuration from YAML without restarting.

**Response**:
```json
{
  "success": true,
  "workers_loaded": 2,
  "message": "Configuration reloaded successfully"
}
```

## Python API

### Using the Pool Transparently

Existing code automatically gets load balancing:

```python
from src.npu_integration import get_npu_queue

# Get queue (automatically uses pool)
queue = await get_npu_queue()

# Submit task (automatically load balanced)
result = await queue.submit_task("text_analysis", {
    "text": "Analyze this text",
    "model_id": "default"
})
```

### Direct Pool Access

```python
from src.npu_integration import get_npu_pool

# Get pool
pool = await get_npu_pool()

# Execute task directly with load balancing
result = await pool.execute_task("text_analysis", {
    "text": "Analyze this text",
    "model_id": "default"
})

# Get pool statistics
stats = await pool.get_pool_stats()

# Reload configuration
await pool.reload_config()
```

## Load Balancing Algorithm

**Priority-First + Least-Connections**:

1. Filter workers: `enabled=true`, `circuit != OPEN`, not excluded
2. Group by priority (higher = better)
3. Select highest priority group
4. Within group, select worker with fewest `active_tasks`
5. Ties broken by worker ID (alphabetical)

**Example**:
- Worker A: priority=10, active_tasks=5
- Worker B: priority=10, active_tasks=2
- Worker C: priority=5, active_tasks=0

Result: Worker B selected (same priority as A, but less loaded)

If Worker A and B both fail, Worker C is selected via failover.

## Circuit Breaker

**States**:
- **CLOSED**: Normal operation, worker accepts tasks
- **OPEN**: Worker blocked after 5 consecutive failures
- **HALF_OPEN**: Testing recovery after 60s cooldown

**Transitions**:
```
CLOSED --[5 failures]--> OPEN
OPEN --[60s timeout]--> HALF_OPEN
HALF_OPEN --[success]--> CLOSED
HALF_OPEN --[failure]--> OPEN (another 60s)
```

## Health Monitoring

**Hybrid Approach**:
1. **Background checks**: Every 30s for all workers
2. **On-demand checks**: Before routing if last check >30s ago

**Health Check Endpoint**: `GET /health` on each worker

## Retry Policy

**Failover with Exclusion**:
- Max 3 retry attempts
- Failed worker excluded from subsequent attempts
- Different worker selected for each retry
- Return error with `fallback: true` after all retries exhausted

## Backward Compatibility

**Fallback Behavior**:
- If `npu_workers.yaml` missing → uses single worker from service registry
- If no enabled workers → uses single worker from service registry
- Existing code using `get_npu_client()` works unchanged

## Performance Targets

From issue #168:

| Metric | Target | Status |
|--------|--------|--------|
| Worker selection | <50ms | Implemented |
| Load balancing overhead | <100ms | Implemented |
| Concurrent tasks | 1000+ | Implemented |
| Success rate with retry | 99.9% | Implemented |
| Routing errors | <1% | Implemented |

## Monitoring

**Metrics to Track**:
- Pool-level: total workers, healthy workers, task counts, success rate
- Per-worker: active tasks, total requests, failure count, circuit state
- Performance: avg task duration, selection time, routing overhead

**Log Levels**:

| Event | Level | Rationale |
|-------|-------|-----------|
| Worker selection | DEBUG | High frequency |
| Health check failures | DEBUG | NPU is optional |
| Circuit breaker opens | ERROR | Critical event |
| Task failure (first) | INFO | Retry will handle |
| Task failure (final) | ERROR | Needs investigation |
| Config reload | INFO | Admin action |

## Troubleshooting

**All workers unhealthy**:
- Check worker processes are running
- Verify network connectivity
- Check worker `/health` endpoints directly
- Review circuit breaker states via API

**Circuit breaker constantly opening**:
- Check worker logs for errors
- Verify worker capacity (`max_concurrent_tasks`)
- Consider increasing cooldown period

**Tasks timing out**:
- Check `timeout_seconds` in config
- Verify workers aren't overloaded
- Check network latency

**New workers not appearing**:
- Verify `npu_workers.yaml` syntax is valid
- Call `POST /api/npu/pool/reload` to load new config
- Check new worker has `enabled: true`

## Files

**Implementation**:
- `src/npu_integration.py` - Core pool logic
- `autobot-user-backend/api/npu_workers.py` - API endpoints

**Tests**:
- `tests/test_npu_worker_pool.py` - Unit tests (30 tests)
- `tests/integration/test_npu_pool_integration.py` - Integration tests (13 tests)

**Configuration**:
- `config/npu_workers.yaml` - Worker definitions

## References

- [Design Document](../plans/2026-02-05-npu-worker-pool-design.md)
- [Implementation Plan](../plans/2026-02-05-npu-worker-pool-implementation.md)
- [GitHub Issue #168](https://github.com/mrveiss/AutoBot-AI/issues/168)
