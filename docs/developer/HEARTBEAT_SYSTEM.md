# Heartbeat System Reference

> Issue #1407. Backend: `autobot-backend/services/heartbeat_scheduler.py` and
> `autobot-backend/api/heartbeat.py`. Frontend: `autobot-frontend/src/components/agents/HeartbeatPanel.vue`.

> **All background schedulers** (including HeartbeatScheduler) are enumerated in
> `autobot-backend/services/scheduler_registry.py` — the canonical source of truth for
> runtime model, tick interval, and owner file. The full list is also available at runtime via
> `GET /api/admin/schedulers`. See GH#6594.

---

## What HeartbeatPanel Does

HeartbeatPanel is a Vue component that gives operators real-time visibility into
an agent's scheduled execution lifecycle. For a given agent ID it displays:

- Current configuration (enabled state, interval, max duration, last run time)
- Pending wakeup queue with priorities and reasons
- Run history (last 20 runs) with status, trigger, duration, token usage, and cost
- Per-run event timeline, expanded on click
- Controls to update configuration, trigger a manual run, and queue a wakeup

The panel subscribes to the `agent:{agent_id}` live-event channel and
automatically refreshes all three data sections whenever a
`heartbeat_run_started` or `heartbeat_run_completed` event arrives.

---

## Architecture

```
HeartbeatScheduler (asyncio tasks, one per enabled agent)
    │
    ├─ _start_run()
    │       └─ publish_live_event("agent:{id}", "heartbeat_run_started", {...})
    │
    ├─ _invoke_agent()   ← integration point for process adapter (#1406)
    │
    └─ _finalize_run()
            └─ publish_live_event("agent:{id}", "heartbeat_run_completed", {...})

LiveEventManager (in-memory WebSocket channel router, live_event_manager.py)
    └─ broadcasts to all WebSocket clients subscribed to "agent:{id}"

LiveEventService (frontend, src/services/LiveEventService.ts)
    └─ useLiveEvents() composable
            └─ HeartbeatPanel.vue
                    └─ watch(agentId, { immediate: true }) → subscribe/unsubscribe
```

The backend pushes events synchronously after each DB commit.
The frontend receives them over a single WebSocket connection managed by
`LiveEventService` and dispatches them by channel to all registered callbacks.

---

## Backend: HeartbeatScheduler

### Lifecycle Methods

| Method | Purpose |
|--------|---------|
| `start()` | Load all `AgentRuntimeState` rows where `heartbeat_enabled=True` and spawn asyncio tasks |
| `stop()` | Cancel every active task; called on application shutdown |
| `enable_agent(agent_id, interval_seconds)` | Start (or restart) the loop for one agent; enforces `_MIN_INTERVAL_SECONDS = 10` |
| `disable_agent(agent_id)` | Cancel and remove the loop for one agent |
| `wakeup(agent_id, context, priority, reason)` | Insert an `AgentWakeupRequest` row and, if the agent has no active loop, fire an ad-hoc run immediately |

### Run Execution Flow

1. `_heartbeat_loop` sleeps for `interval_seconds`, then calls `_run_once`.
2. `_run_once` calls `_start_run`, `_invoke_agent`, and `_finalize_run` in sequence.
3. `_start_run` creates a `HeartbeatRun` row with `status=RUNNING`, consumes the
   highest-priority pending `AgentWakeupRequest` (if any, its trigger overrides
   INTERVAL), appends a `run_started` event, and publishes
   `heartbeat_run_started` over the live-event channel.
4. `_invoke_agent` wraps `_execute_agent` with `asyncio.wait_for(timeout)`.
   Timeout produces `TIMED_OUT`; exceptions produce `FAILED`.
5. `_finalize_run` updates the run row, updates `AgentRuntimeState.last_heartbeat_at`,
   optionally persists `session_params`, appends `run_finished`, and publishes
   `heartbeat_run_completed`.

### Event Payload Schemas

**`heartbeat_run_started`**

```json
{
  "run_id": "<uuid>",
  "agent_id": "<string>",
  "trigger": "interval | event | manual"
}
```

**`heartbeat_run_completed`**

```json
{
  "run_id": "<uuid>",
  "agent_id": "<string>",
  "status": "completed | failed | timed_out | cancelled",
  "error_message": "<string | null>",
  "tokens_used": "<int | null>",
  "cost_usd": "<float | null>"
}
```

### Run Status Values

| Status | Meaning |
|--------|---------|
| `running` | In progress |
| `completed` | `_execute_agent` returned without error |
| `failed` | `_execute_agent` raised an exception |
| `timed_out` | Exceeded `max_run_duration_seconds` |
| `cancelled` | Task cancelled via `disable_agent` or `stop` |

### Wakeup Trigger Values

| Trigger | Source |
|---------|--------|
| `interval` | Normal scheduled tick |
| `event` | Consumed an `AgentWakeupRequest` row |
| `manual` | `POST /{agent_id}/trigger` API endpoint |

### `_execute_agent` Integration Point

`_execute_agent` is the stub that a process adapter (issue #1406) must bind.
It receives `agent_id`, `state_id`, and `run_id`, and must return a dict with
any subset of: `tokens_used`, `cost_usd`, `model`, `provider`, `session_params`.
Returning an empty dict is valid; the scheduler will still record the run.

---

## REST API

All endpoints are mounted under `/api/heartbeat` and require a valid JWT
(`Authorization: Bearer <token>`).

| Method | Path | Purpose |
|--------|------|---------|
| `GET` | `/{agent_id}/config` | Read config and runtime state |
| `PUT` | `/{agent_id}/config` | Update config; syncs scheduler immediately |
| `PATCH` | `/{agent_id}/session` | Persist session_params / current_task_id / extra |
| `GET` | `/{agent_id}/runs` | List runs, newest first (limit/offset) |
| `GET` | `/{agent_id}/runs/{run_id}` | Single run with full event timeline |
| `POST` | `/{agent_id}/wakeup` | Queue a wakeup request (202 Accepted) |
| `GET` | `/{agent_id}/wakeup` | List pending wakeup requests |
| `POST` | `/{agent_id}/trigger` | Trigger an immediate manual run (202 Accepted) |

The scheduler instance is injected via `configure_scheduler()` at application
startup. Endpoints that require the scheduler return `503` if it has not been
configured.

---

## Frontend: HeartbeatPanel

### Component Location

`autobot-frontend/src/components/agents/HeartbeatPanel.vue`

### State

| Ref | Type | Purpose |
|-----|------|---------|
| `agentId` | `string` | Bound to the agent-ID text input |
| `config` | `HeartbeatConfig \| null` | Current runtime state from API |
| `runs` | `HeartbeatRun[]` | Last 20 runs |
| `pendingWakeups` | `WakeupRequest[]` | Unconsumed wakeup queue |
| `editEnabled / editInterval / editMaxDuration` | primitives | Editable config form values |
| `expandedRunId` | `string \| null` | Which run row is expanded to show events |

### Subscribe / Unsubscribe Lifecycle

```ts
watch(agentId, (newId, oldId) => {
  if (oldId) {
    _liveUnsub?.()
    unsubscribe(`agent:${oldId}`, _onLiveEvent)
  }
  if (newId) {
    _liveUnsub = subscribe(`agent:${newId}`, _onLiveEvent)
  }
}, { immediate: true })

onUnmounted(() => {
  _liveUnsub?.()
})
```

The `{ immediate: true }` option means the watcher fires during component
setup, so the subscription is established as soon as `agentId` is non-empty
on mount. `onUnmounted` is the safety net that always cleans up even if
`agentId` is still set when the component is torn down.

### Live Event Handler

`_onLiveEvent` calls `loadData()` on both `heartbeat_run_started` and
`heartbeat_run_completed`. A full three-way parallel fetch
(`/config`, `/runs?limit=20`, `/wakeup`) is issued each time to keep all
three panels in sync without partial state.

### Authentication

The component reads `access_token` from `localStorage` and sets
`Authorization: Bearer <token>` on every `apiFetch` call.

---

## Live Event Channel

**Channel format:** `agent:{agent_id}`

Valid channel prefixes (enforced by `LiveEventManager`): `agent`, `task`,
`workflow`, `global`. A subscription to an unrecognised prefix is silently
rejected and logs a warning.

Clients subscribe by sending a subscription message over the WebSocket
connection to `/api/live-events`. The `useLiveEvents` composable handles
connection management and channel multiplexing transparently.

---

## Configuration

### AgentRuntimeState Fields (DB)

| Field | Default | Constraint | Notes |
|-------|---------|-----------|-------|
| `heartbeat_enabled` | `False` | — | Must be `True` for scheduler to spawn a loop |
| `heartbeat_interval_seconds` | `300` | >= 10 (enforced by scheduler and API) | Seconds between ticks |
| `max_run_duration_seconds` | `600` | >= 10 | Hard timeout per run; passed to `asyncio.wait_for` |

The hard floor for `heartbeat_interval_seconds` is `_MIN_INTERVAL_SECONDS = 10`
(defined in `heartbeat_scheduler.py`). The API schema validates `ge=10` as well,
so both layers enforce it.

The default timeout `_DEFAULT_MAX_DURATION_SECONDS = 600` is used when
`AgentRuntimeState.max_run_duration_seconds` is `None`.

---

## Troubleshooting

### Panel not updating after a run completes

1. Confirm the agent ID entered in the panel matches the agent ID that the
   scheduler is using (case-sensitive UUID string).
2. Open the browser DevTools Network tab and verify the WebSocket connection
   to `/api/live-events` is established (`101 Switching Protocols`).
3. Check the browser console for a log line from `HeartbeatPanel`:
   `Subscribed to live events for agent {agentId}`. If absent, the watcher
   did not fire — ensure `agentId` was set before the component mounted and
   that `useLiveEvents` is imported correctly.
4. On the backend, check that `configure_scheduler(scheduler)` was called at
   startup; if not, all scheduler-dependent endpoints return `503`.

### Panel shows stale data after clicking "Load"

`loadData()` issues three parallel `apiFetch` calls. If any of them fails, the
`error` banner will show the HTTP status and response body. Common causes:

- `401` — `access_token` in `localStorage` is expired; re-authenticate.
- `404` — No `AgentRuntimeState` row exists yet; the API will auto-create one
  on first `GET /config`, so a second load will succeed.
- `503` — Scheduler not initialised; check backend startup logs.

### Missed events / run does not appear in history

Events are in-memory and not persisted in the `LiveEventManager`. If the
frontend WebSocket was disconnected when an event fired, the component will not
receive it. Clicking "Load" at any time performs a full data refresh from the
database, which will show all persisted runs regardless of whether the live
event was received.

### agent_id not set / "Load" button disabled

The "Load" button is disabled while `agentId` is an empty string or while a
load is in progress (`loading = true`). Type or paste a valid UUID into the
Agent ID input and press Enter or click "Load".
