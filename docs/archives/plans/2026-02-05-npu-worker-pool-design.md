# NPU Multi-Worker Load Balancing & Pool Management

**Issue**: #168
**Date**: 2026-02-05
**Status**: Design Approved
**Priority**: Low (Optimization for future scale)

## Overview

Implement health-aware load balancing across multiple NPU workers for improved throughput and reliability. This design extends the existing `NPUWorkerClient` and `NPUTaskQueue` pattern to transparently support multiple workers with intelligent routing, health monitoring, and automatic failover.

## Current State

- Single `NPUWorkerClient` at `172.16.168.22:8081`
- Basic task queue via `NPUTaskQueue` with Redis backing
- No load balancing or failover capabilities
- Existing YAML configuration structure in `config/npu_workers.yaml`

## Goals

- Support 2+ NPU workers simultaneously
- Automatic failover with <100ms routing overhead
- 99.9% task success rate with retry mechanism
- Handle 1000+ concurrent tasks
- Zero breaking changes to existing API consumers

## Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| **Architecture** | Extend existing pattern | Maintains consistency, leverages existing infrastructure |
| **Integration** | Transparent upgrade | Existing code gets load balancing automatically |
| **Load Balancing** | Priority-first + least-connections | Respects config priorities, optimal for variable-duration tasks |
| **Health Monitoring** | Hybrid (background + on-demand) | Maximum reliability without sacrificing performance |
| **Circuit Breaker** | Conservative (5 failures, 60s cooldown) | Prevents cascading failures, industry-standard pattern |
| **Retry Policy** | Failover with exclusion, max 3 attempts | Clean stateless design, matches issue spec |

---

## Architecture

### Component Hierarchy

```
NPUTaskQueue (existing, unchanged)
    ↓ submits tasks to
NPUWorkerPool (new - manages multiple workers)
    ↓ routes to
NPUWorkerClient instances (existing, one per worker)
```

### Singleton Pattern

- `get_npu_client()` returns a pool-aware "virtual client" backed by the pool
- `get_npu_queue()` creates `NPUTaskQueue` using the pool instead of single client
- Existing code using `queue.submit_task()` automatically gets load balancing

### Configuration

**Source**: `config/npu_workers.yaml` (already exists)

**Key fields per worker**:
- `id`: Unique worker identifier (e.g., `npu-worker-vm2`)
- `url`: Worker endpoint (e.g., `http://172.16.168.22:8081`)
- `priority`: 1-10 (higher = preferred, used for failover ordering)
- `enabled`: Boolean to enable/disable workers
- `max_concurrent_tasks`: Worker capacity limit

**Runtime reload**: New API endpoint `/api/npu/pool/reload` for hot-reloading config

### Backward Compatibility

- If `npu_workers.yaml` doesn't exist or has no enabled workers, falls back to single worker from `service_registry.get_service_url("npu-worker")`
- Zero breaking changes to existing callers

---

## Core Components

### 1. NPUWorkerPool (new class)

**Location**: `src/npu_integration.py`

**Responsibilities**:
- Worker lifecycle management
- Load balancing with priority-first + least-connections algorithm
- Health monitoring (background + on-demand)
- Circuit breaker management

**Key Methods**:

```python
class NPUWorkerPool:
    async def execute_task(self, task_type: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """Main entry point - selects worker and executes task with retry"""

    async def _select_worker(self, excluded_workers: Set[str]) -> Optional[NPUWorkerClient]:
        """Priority-first + least-connections selection algorithm"""

    async def _start_health_monitor(self):
        """Background task for periodic health checks (every 30s)"""

    async def reload_config(self):
        """Hot-reload worker configuration from YAML"""

    async def get_pool_stats(self) -> Dict[str, Any]:
        """Return pool metrics for monitoring"""
```

**State Tracking**:
- Active task count per worker
- Circuit breaker states (CLOSED/OPEN/HALF_OPEN)
- Health check timestamps and results
- Failure counts per worker

### 2. WorkerState (new dataclass)

**Purpose**: Track per-worker metrics and health status

```python
@dataclass
class WorkerState:
    worker_id: str
    client: NPUWorkerClient
    active_tasks: int = 0
    total_requests: int = 0
    failures: int = 0
    last_health_check: float = 0
    healthy: bool = True
    circuit_state: CircuitState = CircuitState.CLOSED
    circuit_open_until: float = 0
```

**Thread Safety**: All updates use asyncio locks

### 3. Modified NPUTaskQueue

**Changes**:
- Constructor accepts `NPUWorkerPool` instead of `NPUWorkerClient`
- `_worker()` method calls `pool.execute_task()` instead of `client.offload_heavy_processing()`

**Unchanged**:
- Worker count management
- Task queueing logic
- Timeout handling
- Future-based result pattern

### 4. Configuration Loader (new function)

```python
def load_worker_config(config_path: str = "config/npu_workers.yaml") -> List[Dict]:
    """Parse and validate worker configuration"""
```

**Validation**:
- Required fields present (`id`, `url`, `priority`, `enabled`)
- URL format valid
- Priority in range 1-10
- No duplicate worker IDs

---

## Task Execution Flow

### Normal Execution Path

1. Caller invokes `queue.submit_task(task_type, data)`
2. Queue worker picks up task, calls `pool.execute_task(task_type, data)`
3. Pool acquires worker selection lock (prevents race conditions)
4. Pool filters workers: `enabled=true` AND `circuit_state != OPEN`
5. Pool groups by priority, selects highest priority group
6. Within priority group, selects worker with fewest `active_tasks`
7. Pool performs on-demand health check if `last_check > 30s ago`
8. If healthy, increment worker's `active_tasks` counter
9. Pool calls `worker_client.offload_heavy_processing(task_type, data)`
10. On success: decrement `active_tasks`, reset failure count, return result
11. On failure: proceed to retry flow

### Retry Flow (Failover with Exclusion)

1. Mark failed worker in exclusion set for this task
2. If `retry_count < 3`, go back to step 3 (select different worker)
3. If `retry_count >= 3`, return error to caller
4. Increment worker's failure count
5. If `failure_count >= 5`, open circuit breaker for 60s

### Background Health Monitoring

- Asyncio task runs every 30s (configurable via `health_check_interval`)
- Checks `/health` endpoint on all enabled workers
- Updates `last_health_check` timestamp and health status
- Runs independently of task execution flow

---

## Load Balancing Algorithm

### Priority-First with Least-Connections

**Step 1: Filter workers**
- `enabled = true`
- `circuit_state != OPEN`
- Not in exclusion set (for retries)

**Step 2: Group by priority**
- Workers with priority 10 = Group A
- Workers with priority 5 = Group B
- Workers with priority 1 = Group C

**Step 3: Select highest priority group**
- If Group A has healthy workers, use only Group A
- Else if Group B has healthy workers, use only Group B
- Else use Group C

**Step 4: Within group, select least-loaded**
- Sort by `active_tasks` ascending
- Return worker with minimum active tasks
- Ties broken by worker ID (alphabetical)

**Example**:
```
Workers:
- vm2-npu: priority=10, active_tasks=3
- windows-npu: priority=5, active_tasks=0

Result: vm2-npu selected (higher priority, even though more loaded)

If vm2-npu circuit opens:
Result: windows-npu selected (automatic failover to lower priority)
```

---

## Error Handling & Circuit Breaker

### Circuit Breaker States

| State | Description | Transitions |
|-------|-------------|-------------|
| **CLOSED** | Normal operation, worker accepts tasks | → OPEN after 5 consecutive failures |
| **OPEN** | Worker blocked, no tasks routed | → HALF_OPEN after 60s cooldown |
| **HALF_OPEN** | Testing recovery, allows 1 test request | → CLOSED on success, → OPEN on failure |

### State Transitions

```
CLOSED --[5 failures]--> OPEN
OPEN --[60s timeout]--> HALF_OPEN
HALF_OPEN --[success]--> CLOSED
HALF_OPEN --[failure]--> OPEN (another 60s)
```

### Edge Cases

**1. All workers unhealthy**
- Return error with `{"success": false, "fallback": true}`
- Caller can use CPU fallback via `process_with_npu_fallback()`

**2. No enabled workers in config**
- Fall back to single worker from `service_registry.get_service_url("npu-worker")`
- Log warning: "No NPU workers configured, using single worker mode"

**3. Worker fails mid-task**
- Count as failure for circuit breaker
- Task retried on different worker (up to 3 total attempts)
- Worker's failure count incremented

**4. Health check timeout**
- Mark worker as unhealthy
- Increment failure count
- Don't open circuit on health checks alone - only on task failures

**5. Config reload during active tasks**
- New config takes effect immediately for new tasks
- Active tasks complete on their originally assigned workers
- Worker removal waits for active tasks to drain (graceful shutdown)

### Logging Strategy

| Event | Level | Rationale |
|-------|-------|-----------|
| Worker selection | DEBUG | High frequency, low importance |
| Health check failures | DEBUG | NPU is optional per issue #699 |
| Circuit breaker opens | ERROR | Critical event requiring attention |
| Task failure (first attempt) | INFO | Expected, retry will handle |
| Task failure (final after retries) | ERROR | Permanent failure needs investigation |
| Pool configuration reload | INFO | Administrative action tracking |

---

## Testing Strategy

### Unit Tests (`tests/test_npu_worker_pool.py`)

**Coverage**:
- Worker selection algorithm (priority + least-connections)
- Circuit breaker state transitions
- Configuration loading and validation
- Active task counting (increment/decrement)
- Failure exclusion during retries
- Edge case handling

**Key Test Cases**:
```python
def test_priority_selection():
    """Higher priority worker selected even if more loaded"""

def test_least_connections_tiebreaker():
    """Within same priority, least loaded worker selected"""

def test_circuit_breaker_opens_after_5_failures():
    """Circuit opens and blocks worker after threshold"""

def test_circuit_breaker_half_open_recovery():
    """Half-open state allows test request after cooldown"""

def test_failover_excludes_failed_worker():
    """Retry attempts exclude the failed worker"""
```

### Integration Tests (`tests/integration/test_npu_pool_integration.py`)

**Coverage**:
- Multi-worker task execution with mock HTTP responses
- Failover when primary worker fails
- Health monitoring background task
- Config hot-reload during active tasks
- Backward compatibility (single worker mode)

**Test Setup**:
- Mock 2 NPU workers with different priorities
- Simulate worker failures via HTTP error responses
- Verify task distribution and failover behavior

### Performance Tests (`tests/performance/test_npu_pool_performance.py`)

**Requirements from Issue #168**:
- Worker selection time: <50ms
- Load balancing overhead: <100ms
- Concurrent task capacity: 1000+ tasks
- Task routing error rate: <1%

**Test Scenarios**:
```python
async def test_worker_selection_performance():
    """Measure worker selection time under load"""
    # Target: <50ms average

async def test_concurrent_task_throughput():
    """Handle 1000+ concurrent tasks"""
    # Verify no deadlocks or resource exhaustion

async def test_routing_accuracy():
    """Measure task routing error rate"""
    # Target: <1% errors
```

### Manual Testing Scenarios

1. **Basic load balancing**: Start with 2 workers enabled, submit 100 tasks, verify distribution
2. **Failover testing**: Disable primary worker mid-execution, verify failover to secondary
3. **Circuit breaker**: Simulate worker failure (kill NPU worker process), verify circuit opens
4. **Recovery testing**: Wait 60s after circuit opens, verify half-open state and recovery
5. **Hot reload**: Reload config with new worker, verify it joins pool without restart

---

## Monitoring & Observability

### New API Endpoints

**GET `/api/npu/pool/stats`** - Pool-level metrics
```json
{
  "total_workers": 2,
  "healthy_workers": 2,
  "total_tasks_processed": 1523,
  "active_tasks": 12,
  "avg_task_duration_ms": 245.3,
  "success_rate": 0.997
}
```

**GET `/api/npu/pool/workers`** - Per-worker health states
```json
{
  "workers": [
    {
      "id": "npu-worker-vm2",
      "url": "http://172.16.168.22:8081",
      "priority": 10,
      "enabled": true,
      "healthy": true,
      "circuit_state": "CLOSED",
      "active_tasks": 8,
      "total_requests": 1023,
      "failures": 0,
      "last_health_check": 1738713245.32
    },
    {
      "id": "windows-npu-worker-main",
      "url": "http://172.16.168.20:8082",
      "priority": 5,
      "enabled": true,
      "healthy": true,
      "circuit_state": "CLOSED",
      "active_tasks": 4,
      "total_requests": 500,
      "failures": 0,
      "last_health_check": 1738713245.18
    }
  ]
}
```

**POST `/api/npu/pool/reload`** - Hot-reload configuration
```json
{
  "success": true,
  "workers_loaded": 2,
  "message": "Configuration reloaded successfully"
}
```

### Metrics to Track

- **Pool-level**: total workers, healthy workers, total tasks, success rate
- **Per-worker**: active tasks, total requests, failure count, circuit state
- **Performance**: avg task duration, worker selection time, routing overhead
- **Reliability**: circuit breaker events, failover count, health check failures

---

## Implementation Phases

### Phase 1: Core Pool Implementation
- [ ] Create `NPUWorkerPool` class with worker management
- [ ] Implement configuration loader for `npu_workers.yaml`
- [ ] Add worker selection algorithm (priority + least-connections)
- [ ] Modify `get_npu_client()` and `get_npu_queue()` for transparent integration
- [ ] Unit tests for pool logic

### Phase 2: Health Monitoring & Circuit Breaker
- [ ] Implement background health monitoring task
- [ ] Add on-demand health checks before routing
- [ ] Implement circuit breaker state machine
- [ ] Add logging for health events and circuit state changes
- [ ] Integration tests for health monitoring

### Phase 3: Retry & Failover
- [ ] Implement retry logic with worker exclusion
- [ ] Add task failure tracking per worker
- [ ] Handle edge cases (all workers down, no config, etc.)
- [ ] Integration tests for failover scenarios

### Phase 4: Observability & API
- [ ] Add `/api/npu/pool/stats` endpoint
- [ ] Add `/api/npu/pool/workers` endpoint
- [ ] Add `/api/npu/pool/reload` endpoint
- [ ] Performance tests (1000+ concurrent tasks)

### Phase 5: Documentation & Deployment
- [ ] Update API documentation
- [ ] Create operator runbook for pool management
- [ ] Update `config/npu_workers.yaml` with production workers
- [ ] Deploy and monitor in production

---

## Success Criteria

From Issue #168:

- ✅ Support 2+ NPU workers simultaneously
- ✅ Automatic failover working correctly
- ✅ <100ms load balancing overhead
- ✅ 99.9% task success rate with retry
- ✅ Health checks don't impact performance
- ✅ Handle 1000+ concurrent tasks
- ✅ <50ms worker selection time
- ✅ <1% task routing errors
- ✅ Graceful degradation with worker failures

---

## File Changes

### New Files
- `tests/test_npu_worker_pool.py` - Unit tests
- `tests/integration/test_npu_pool_integration.py` - Integration tests
- `tests/performance/test_npu_pool_performance.py` - Performance tests

### Modified Files
- `src/npu_integration.py` - Add `NPUWorkerPool`, `WorkerState`, modify `get_npu_client()` and `get_npu_queue()`
- `backend/routes/npu_routes.py` - Add pool management endpoints (if doesn't exist, create)
- `config/npu_workers.yaml` - Update with production worker definitions

### Configuration
- Uses existing `config/npu_workers.yaml` structure
- No changes needed to `src/config/ssot_config.py`

---

## Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|-----------|
| Breaking existing NPU client usage | High | Transparent integration, backward compatibility fallback |
| Pool overhead degrades performance | Medium | Performance tests ensure <100ms overhead target |
| Circuit breaker too aggressive | Medium | Conservative thresholds (5 failures, 60s cooldown) |
| Config reload causes race conditions | Medium | Lock-protected state updates, graceful worker removal |
| All workers fail simultaneously | Low | Fallback to error + CPU processing via existing pattern |

---

## Future Enhancements (Out of Scope)

- Dead letter queue for permanently failed tasks
- Worker capability-based routing (route vision tasks to vision workers)
- Dynamic worker scaling based on queue depth
- Weighted load balancing strategy (use worker `weight` field)
- Metrics export to Prometheus/Grafana
- WebSocket API for real-time pool status updates

---

## References

- **Issue**: [#168 - NPU Multi-Worker Load Balancing](https://github.com/mrveiss/AutoBot-AI/issues/168)
- **Existing Patterns**: `OllamaConnectionPool` ([src/utils/ollama_connection_pool.py](../../src/utils/ollama_connection_pool.py))
- **Service Registry**: [src/utils/service_registry.py](../../src/utils/service_registry.py)
- **Configuration**: [config/npu_workers.yaml](../../config/npu_workers.yaml)
