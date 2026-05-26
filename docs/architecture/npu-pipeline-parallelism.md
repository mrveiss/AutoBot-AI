# NPU Pipeline Parallelism — Architecture Design

**Parent:** MVA-1082 — Cross-host pipeline parallelism for 70B+ models  
**Status:** Draft  
**Date:** 2026-05-25

---

## Overview

Pipeline parallelism splits a large model's layers across multiple NPU workers so
that a single forward pass traverses a chain of workers sequentially, each
processing its assigned layer range before passing the hidden state to the next.
This allows 70B+ models to run on a pool of machines where no single machine
holds enough VRAM for the full model.

```
Token stream
    │
    ▼
[Dispatcher]
    │  shard-plan lookup (Redis npu:pipeline:<plan_id>)
    │
    ├─► Worker A  layers  0–19  ──► hidden state (gRPC/aiohttp) ──►
    ├─► Worker B  layers 20–39  ──► hidden state ──►
    ├─► Worker C  layers 40–59  ──► hidden state ──►
    └─► Worker D  layers 60–79  ──► logits / output token
```

---

## 1. Shard-Plan Format

### Schema

A **shard plan** describes how to partition a model's layers across the available
worker pool for a single inference session.

```python
ShardPlan = list[tuple[str, tuple[int, int]]]
# [(worker_id, (layer_start, layer_end_exclusive)), ...]

# Example — 80-layer model across four workers
plan = [
    ("worker-a1b2", (0,  20)),
    ("worker-c3d4", (20, 40)),
    ("worker-e5f6", (40, 60)),
    ("worker-g7h8", (60, 80)),
]
```

| Field          | Type         | Description                                      |
|----------------|--------------|--------------------------------------------------|
| `worker_id`    | `str`        | ID matching `NPUWorkerConfig.id` in the registry |
| `layer_start`  | `int`        | First layer index owned by this worker (inclusive) |
| `layer_end`    | `int`        | Last layer index (exclusive, Python-slice style) |

Rules:
- Ranges must be contiguous and non-overlapping.
- The union of all ranges must cover `[0, num_layers)`.
- Workers are listed in forward-pass order.

### Redis Storage

Plans are stored as JSON under a TTL key so in-flight sessions survive a
dispatcher restart but stale plans are garbage-collected automatically.

```
Key:   npu:pipeline:<plan_id>
Type:  string (JSON-encoded ShardPlan)
TTL:   session_ttl + 60 s grace (default: 3660 s)
```

**Write** (dispatcher, at session start):

```python
await redis.set(
    f"npu:pipeline:{plan_id}",
    json.dumps(plan),
    ex=SESSION_TTL + 60,
)
```

**Read** (worker, on first hidden-state receive to validate ownership):

```python
raw = await redis.get(f"npu:pipeline:{plan_id}")
plan = json.loads(raw)
```

**Invalidation**: the dispatcher deletes the key on normal session completion or
on a pool-composition change that requires re-planning (see §4).

---

## 2. Dispatcher Protocol

The dispatcher sits between the token generator and the worker chain. It:

1. Resolves or creates the shard plan for the requested model.
2. Forwards the initial embedding (hidden state after the embedding layer) to
   the first worker in the plan.
3. Returns the final logits/output token back to the caller.

### Transport: gRPC vs aiohttp

| Criterion              | gRPC (recommended)           | aiohttp (fallback)              |
|------------------------|------------------------------|---------------------------------|
| Serialisation overhead | Protobuf — minimal           | JSON/msgpack — moderate         |
| Streaming support      | Native bidirectional streams | Chunked HTTP response           |
| Backpressure           | Flow-control built-in        | Manual buffering needed         |
| Deployment complexity  | Requires proto compilation   | Zero extra tooling               |
| Current worker support | Planned (NPUWorkerClient)    | Supported now (aiohttp session) |

**Decision**: use gRPC for hidden-state transfer when both endpoints expose the
`NPUPipelineService` proto. Fall back to `aiohttp` POST with msgpack body when
the remote worker runs an older firmware that lacks the gRPC endpoint.

Capability negotiation happens at plan creation time:

```python
transport = (
    "grpc"
    if worker_details.capabilities.get("grpc_pipeline")
    else "aiohttp"
)
```

### Hidden-State Message

```protobuf
message HiddenState {
  string plan_id      = 1;
  string session_id   = 2;
  int32  layer_in     = 3;   // first layer processed by the sender
  int32  layer_out    = 4;   // first layer expected by the receiver
  bytes  tensor_data  = 5;   // bfloat16 row-major tensor, shape encoded in metadata
  map<string, string> metadata = 6;
}
```

For the `aiohttp` fallback the same fields are encoded as a msgpack dict in the
POST body to `POST /pipeline/hidden-state`.

### Flow

```
Dispatcher                 Worker A                Worker B …
    │                          │                       │
    │──── HiddenState(l=0) ───►│                       │
    │                          │  forward pass l 0–19  │
    │                          │──── HiddenState(l=20)►│
    │                          │                       │  forward pass l 20–39
    │                          │                       │──► … ──► logits
    │◄─────────────────────────────────────── logits ──│
```

---

## 3. Failure Modes

### 3.1 Worker Drop Mid-Pass

**Scenario**: a worker goes offline while it holds an in-flight hidden state.

**Detection**: `NPUWorkerManager` health checks (`_health_check_task`) set
`WorkerStatus = UNAVAILABLE` in Redis within one health-check interval
(default 30 s). The dispatcher detects this when it receives an HTTP/gRPC error
from the next-hop worker or when the hidden state does not arrive within the
`hidden_state_timeout` (default 10 s).

**Recovery**:
1. Abort the current session; surface an error token to the caller.
2. Publish `worker.unavailable` event on the event bus; `NPUWorkerManager`
   increments `_worker_failure_counts[worker_id]` and applies exponential
   backoff (1× → 8× the health-check interval, i.e. 30 s – 240 s).
3. Re-plan: remove the dropped worker from the active pool, build a new shard
   plan over the remaining workers (or fail with `INSUFFICIENT_CAPACITY` if the
   remaining pool cannot cover all layers).
4. The failed session is not retried automatically; the client must re-issue the
   request so the new plan takes effect.

### 3.2 Pool Composition Change

**Scenario**: a new worker joins or an existing worker is removed while active
pipeline sessions are running.

**Trigger events** (emitted by `NPUWorkerManager`):
- `worker.added` — new worker registered and health-checked green.
- `worker.removed` — worker deregistered by operator or eviction policy.

**Dispatcher behaviour**:
- **Worker added**: existing sessions continue on their current plan. New
  sessions use the updated pool. The dispatcher does not migrate in-flight
  sessions.
- **Worker removed**: same as §3.1 — sessions routed through the removed worker
  are aborted; all new sessions re-plan without it.
- The Redis key `npu:pipeline:<plan_id>` is deleted for all sessions affected by
  the removed worker so stale plans cannot be re-used.

### 3.3 Heterogeneous VRAM

**Scenario**: workers have different VRAM capacities; the naive equal-split plan
would OOM a smaller worker.

**Plan allocation algorithm** (weighted proportional split):

```python
def build_shard_plan(workers: list[WorkerDetails], num_layers: int) -> ShardPlan:
    total_vram = sum(w.vram_gb for w in workers)
    plan, cursor = [], 0
    for i, w in enumerate(workers):
        share = w.vram_gb / total_vram
        count = round(num_layers * share) if i < len(workers) - 1 else num_layers - cursor
        plan.append((w.id, (cursor, cursor + count)))
        cursor += count
    return plan
```

VRAM per worker is read from `NPUWorkerDetails.vram_gb` (populated during
registration or health-check response). A worker with 0 VRAM reported is
excluded from pipeline plans and used only for non-pipeline requests.

---

## 4. Latency Budget Guard

### TTFT Inflation Threshold

Pipeline parallelism adds inter-worker network latency to every token's first
pass. The latency budget guard aborts the pipeline path and falls back to
single-worker or CPU inference when the measured Time-To-First-Token (TTFT)
exceeds an acceptable multiple of the baseline.

```python
# Constants (threshold_constants.py / ssot_config)
TTFT_BASELINE_MS: float = 300     # expected single-worker TTFT for the model
TTFT_INFLATION_RATIO: float = 2.5 # allow up to 2.5× baseline before fallback
TTFT_WINDOW_SAMPLES: int = 10     # rolling window for smoothing
```

```
Acceptable TTFT = TTFT_BASELINE_MS × TTFT_INFLATION_RATIO
Default: 300 ms × 2.5 = 750 ms
```

### Fallback Criteria

A fallback is triggered when **any** of the following is true:

| Condition                                           | Action                             |
|-----------------------------------------------------|------------------------------------|
| Rolling-average TTFT > acceptable threshold         | Route new sessions to single worker |
| Remaining workers < `min_pipeline_workers` (2)      | Disable pipeline mode entirely      |
| Hidden-state transfer time > `hidden_state_timeout` | Abort session; re-plan or fallback  |
| `npu:pipeline:<plan_id>` key missing on worker read | Abort session; force re-plan        |

**Fallback path**: the dispatcher sets `pipeline_enabled = False` in the session
context and routes through `ProviderRegistry.get_provider_for_request()` with
`pipeline=False`, which selects a single available worker with sufficient VRAM,
or the GPU-backed WSL2 provider if no NPU worker can serve the model alone.

**Recovery from fallback**: the latency guard re-evaluates every
`TTFT_RECOVERY_WINDOW` (default 60 s) of clean pipeline sessions. If the rolling
average returns below threshold, pipeline mode is re-enabled automatically.

---

## 5. Integration Points

### 5.1 `provider_registry.py` Hook

`ProviderRegistry.register()` accepts a provider whose name matches the
convention `npu_pipeline:<model_id>`. On registration, the registry:

1. Calls `provider.health_check()` to verify at least `min_pipeline_workers`
   workers are available and their combined VRAM covers the model.
2. Stores the provider in `_providers` and adds it to the front of
   `_fallback_chain` (ahead of single-worker NPU and GPU fallbacks).

```python
# In lifespan.py initialisation
from llm_shared import get_provider_registry
from services.npu_pipeline_provider import NPUPipelineProvider

registry = get_provider_registry()
pipeline_provider = NPUPipelineProvider(
    model_id="llama3:70b",
    worker_manager=npu_worker_manager,
    redis=redis_client,
)
registry.register(pipeline_provider)
registry.set_fallback_chain([
    f"npu_pipeline:llama3:70b",
    "npu:llama3:70b",          # single-worker NPU if available
    "ollama",                  # GPU fallback
])
```

The `get_provider_for_request()` method picks the first healthy provider in the
chain, so pipeline is used when healthy and single-worker/GPU is used otherwise
without caller changes.

### 5.2 `npu_worker_manager.py` Event Hooks

`NPUWorkerManager` publishes the following events that the pipeline dispatcher
subscribes to:

| Event              | Payload fields                          | Dispatcher action                         |
|--------------------|-----------------------------------------|-------------------------------------------|
| `worker.added`     | `worker_id`, `vram_gb`, `capabilities`  | Add to active pool; re-plan new sessions  |
| `worker.removed`   | `worker_id`, `reason`                   | Remove from pool; abort affected sessions |
| `worker.updated`   | `worker_id`, `status`, `metrics`        | Update health cache                       |
| `worker.unavailable` | `worker_id`, `next_check_at`          | Same as `worker.removed` for in-flight    |

Subscription is set up in the dispatcher's `startup` hook:

```python
from events.bus import subscribe

subscribe("worker.added",       pipeline_dispatcher.on_worker_added)
subscribe("worker.removed",     pipeline_dispatcher.on_worker_removed)
subscribe("worker.unavailable", pipeline_dispatcher.on_worker_unavailable)
```

The `on_worker_*` handlers invalidate affected shard-plan keys in Redis and
update the dispatcher's in-memory worker pool atomically under an `asyncio.Lock`.

---

## 6. Open Questions / Future Work

- **Proto definition**: the `NPUPipelineService` protobuf is not yet committed;
  tracked in MVA-1082 implementation subtasks.
- **Tensor compression**: bfloat16 transfer is uncompressed; LZ4 compression
  may reduce bandwidth at the cost of CPU on the worker side.
- **Multi-pass (draft tokens)**: speculative decoding across a pipeline requires
  coordinating draft and verify passes across the chain — out of scope for this
  revision.
- **Metrics**: TTFT and hidden-state transfer time should be emitted as
  Prometheus histograms (see `TIMEOUT_CONFIGURATION_PROMETHEUS_METRICS_DESIGN.md`).
