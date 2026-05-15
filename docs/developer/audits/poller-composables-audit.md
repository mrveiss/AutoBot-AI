# Poller Composables Audit

**Issue:** #5250
**Date:** 2026-04-24
**Author:** mrveiss

---

## 1. Summary Table

| Composable | LoC | Backoff | Race Guard | Cleanup | Error Handling | Max Attempts | Circuit Breaker | Abort-on-Refresh |
|---|---|---|---|---|---|---|---|---|
| `useBackoffPoller` | 170 | ✅ Exponential | ✅ `inFlight` flag | ✅ `onScopeDispose` + visibility | ✅ Logs, continues | ❌ None | ✅ N-failure open | ✅ `visibilitychange` pause |
| `usePollingJob` | 137 | ❌ Fixed interval | ✅ `currentTaskId` swap | ✅ `onScopeDispose` | ✅ Stores in `error` ref | ✅ `maxAttempts` | ❌ None | ❌ None |
| `useBrowserAutomation` (inline) | 335 total | ❌ Delegates to `usePollingJob` | ✅ Via `usePollingJob` | ✅ Via `usePollingJob` | ✅ Catches, sets `error` ref | ❌ None | ❌ None | ❌ None |
| `useKnowledgeVectorization` (shim) | 650 total | ❌ Fixed | ✅ Via `usePollingJob` | ✅ Via `usePollingJob` + `cleanup()` | ✅ Logs errors | ✅ `Number.MAX_SAFE_INTEGER` | ❌ None | ❌ None |
| `vectorizeDocument` (inline while-loop) | ~40 (lines 353–395) | ❌ None (fixed 1 s) | ❌ No guard | ❌ Manual `attempts < maxAttempts` | ✅ Catches, sets status | ✅ `maxAttempts` env var | ❌ None | ❌ None |

---

## 2. Concern Matrix

| Concern | `useBackoffPoller` | `usePollingJob` | Inline `while` loop |
|---|---|---|---|
| Timer primitive (setTimeout/setInterval) | `setTimeout` chain | `setInterval` | `setTimeout` (await new Promise) |
| Deduplication / in-flight guard | ✅ `inFlight` boolean | ✅ `currentTaskId` task-swap | ❌ Missing |
| Auto-cleanup on scope dispose | ✅ | ✅ | ❌ (must be cancelled by caller manually) |
| Fixed-interval polling | ❌ (dynamic backoff) | ✅ | ✅ (hard-coded 1 000 ms) |
| Exponential backoff | ✅ configurable multiplier | ❌ | ❌ |
| Circuit breaker (open/probe/reset) | ✅ threshold + reset delay | ❌ | ❌ |
| Page-visibility pause | ✅ | ❌ | ❌ |
| Max-attempt auto-stop | ❌ | ✅ `maxAttempts = 60` | ✅ env-var driven |
| Terminal-state callback (`onDone`) | ❌ | ✅ `isComplete` + `onDone` | ❌ (uses `completed` flag inline) |
| Reactive `isPolling`, `data`, `error` | ❌ (state for circuit only) | ✅ all three | ❌ (caller-owned refs) |
| Reactive `attempts` counter | ❌ | ✅ | ❌ (local variable) |
| Task-key (taskId) re-entrant cancel | ❌ | ✅ | ❌ |

---

## 3. Consumer Inventory

### `useBackoffPoller` consumers

| Consumer | Location | Purpose |
|---|---|---|
| `ChatInterface.vue` | `src/components/chat/ChatInterface.vue:918` | Polls for new chat messages; uses backoff + circuit breaker to prevent 499 cascades (issue #1100) |

### `usePollingJob` direct consumers

| Consumer | Location | Purpose |
|---|---|---|
| `useBrowserAutomation` | `src/composables/useBrowserAutomation.ts:287` | Polls worker status + active sessions every `pollInterval` ms |
| `useKnowledgeVectorization` (shim) | `src/composables/useKnowledgeVectorization.ts:564` | Polls vectorization progress; job created dynamically in `startPolling()` |
| `usePrometheusMetrics` | `src/composables/usePrometheusMetrics.ts:443,550,609,688` | Four independent pollers for metrics dashboard, node metrics, cluster health, alert rules |
| `useServiceMessages` | `src/composables/useServiceMessages.ts:153` | Polls for service message feed; created dynamically in `startPolling()` |
| `useAutoResearch` | `src/composables/useAutoResearch.ts:247` | Polls experiment status; created dynamically in `startPolling()` |
| `useAuditApi` | `src/composables/useAuditApi.ts:476` | Polls audit log refresh; created dynamically in `startPolling()` |
| `useOperationsApi` | `src/composables/useOperationsApi.ts:302` | Polls operations status; created dynamically in `startPolling()` |
| `usePatternAnalysis` | `src/composables/usePatternAnalysis.ts:374` | Polls background pattern analysis task |
| `useIndexingJob` | `src/composables/analytics/useIndexingJob.ts:147` | Polls indexing job completion |
| `useBackgroundTask` | `src/composables/useBackgroundTask.ts:204` | Generic background-task wrapper; creates `usePollingJob` per-invocation |
| `ScreenCaptureViewer.vue` | `src/components/vision/ScreenCaptureViewer.vue:343` | Polls screen capture refresh |
| `KnowledgeResearchPanel.vue` | `src/components/knowledge/KnowledgeResearchPanel.vue:119` | Polls screenshot capture during research |

### `useKnowledgeVectorization` (shim over `usePollingJob`) consumers

| Consumer | Location | Purpose |
|---|---|---|
| `KnowledgeBrowser.vue` | `src/components/knowledge/KnowledgeBrowser.vue:204` | Knowledge document tree with vectorization status |
| `TreeNodeComponent.vue` | `src/components/knowledge/TreeNodeComponent.vue:104` | Per-node vectorization status display |

### Views that call `startPolling`/`stopPolling` on composables

| View | Composable | Interval | Notes |
|---|---|---|---|
| `ExperimentDashboard.vue` | `useAutoResearch.startPolling` | 15 000 ms | Starts on `onMounted`, stops on `onUnmounted` |
| `AuditLogsView.vue` | `useAuditApi.startPolling` | 30 000 ms | Toggle-based; `isPolling` reactive button state |

### Inline while-loop polling (anti-pattern)

| Consumer | Location | Purpose | Gap |
|---|---|---|---|
| `useKnowledgeVectorization.vectorizeDocument` | `src/composables/useKnowledgeVectorization.ts:353–395` | Per-document vectorization job status | No race guard, no backoff, no scope cleanup, `await new Promise(setTimeout)` blocks async caller |

---

## 4. Proposed Layered Structure

The three polling composables cover overlapping but distinct concern levels. The goal is a **3-layer primitive/policy/orchestration** structure where each layer composes the one below.

```
┌─────────────────────────────────────────────────────┐
│  Layer 3 — Orchestration                             │
│  usePollingJob<T>                                    │
│  Job lifecycle: isPolling, data, error, attempts     │
│  isComplete callback, onDone callback                │
│  Task-key race guard (currentTaskId)                 │
│  Delegates timer + dedup to Layer 2                  │
└───────────────┬─────────────────────────────────────┘
                │ composes
┌───────────────▼─────────────────────────────────────┐
│  Layer 2 — Policy                                    │
│  useBackoffPoller (refactored as policy layer)       │
│  Backoff (exponential, configurable)                 │
│  Circuit breaker (N failures → open → probe reset)   │
│  Page-visibility pause/resume                        │
│  maxAttempts (currently only in Layer 3)             │
│  Delegates timer to Layer 1                          │
└───────────────┬─────────────────────────────────────┘
                │ composes
┌───────────────▼─────────────────────────────────────┐
│  Layer 1 — Primitive                                 │
│  useTimerPoller (new name for clarity)               │
│  setTimeout/setInterval wrapper                      │
│  in-flight deduplication flag                        │
│  onScopeDispose cleanup                              │
│  start / stop / isRunning                            │
│  No knowledge of errors, backoff, or jobs            │
└─────────────────────────────────────────────────────┘
```

### Layer descriptions

**Layer 1 — `useTimerPoller` (primitive)**
Single responsibility: fire a callback on a timer, deduplicate overlapping calls, clean up on scope dispose.
No error handling, no backoff, no state. ~30 LoC. This is the only place `setTimeout`/`setInterval` appears in the poller stack.

**Layer 2 — `useBackoffPoller` (policy, refactored)**
Wraps Layer 1. Adds: exponential backoff, circuit breaker, page-visibility integration, configurable `maxAttempts`. Exposes reactive circuit state (`isCircuitOpen`, `consecutiveFailures`, `currentInterval`). Currently `useBackoffPoller` directly calls `setTimeout` — after the refactor it delegates to Layer 1.

**Layer 3 — `usePollingJob` (orchestration)**
Wraps either Layer 1 (for fixed-interval polling) or Layer 2 (for resilient polling). Adds: generic return type `T`, `isPolling` / `data` / `error` / `attempts` reactive refs, `isComplete` predicate, `onDone` callback, task-key cancellation via `currentTaskId`. All current consumers of `usePollingJob` stay at this layer.

### Key change from current state

Currently `useBackoffPoller` and `usePollingJob` are **siblings** with no shared foundation. The refactor makes them a **stack**: Layer 3 (`usePollingJob`) gains an optional `policy` option that accepts a Layer 2 instance, enabling consumers to get backoff + circuit-breaker + job-lifecycle in a single composable call. Consumers that only need fixed-interval + lifecycle keep using `usePollingJob` as-is.

---

## 5. Migration Plan

### Phase 1 — Extract Layer 1 primitive (low-risk)

Create `src/composables/useTimerPoller.ts` with the raw `setTimeout`-chain logic currently duplicated in `useBackoffPoller` and `usePollingJob`. Both existing composables refactor internally to call it — zero public API changes.

**Files to change:** `useBackoffPoller.ts`, `usePollingJob.ts` (internals only)

### Phase 2 — Add `policy` option to `usePollingJob` (additive)

Add an optional `policy?: 'fixed' | 'backoff'` option to `UsePollingJobOptions`. When `'backoff'`, `usePollingJob` wraps a `useBackoffPoller` instance internally instead of a raw `setInterval`. Existing call sites with no `policy` option remain on `'fixed'` unchanged.

**Files to change:** `usePollingJob.ts` (new option path), no consumer changes

### Phase 3 — Migrate `ChatInterface.vue` to Layer 3 (optional, UI-risk)

`ChatInterface.vue` currently calls `useBackoffPoller` directly. After Phase 2, it can switch to `usePollingJob` with `policy: 'backoff'` and gain reactive `data`/`error`/`isPolling` state. Low priority since the current implementation works correctly.

**Files to change:** `src/components/chat/ChatInterface.vue`

### Phase 4 — Eliminate inline while-loop in `vectorizeDocument`

Replace the `while (!completed && attempts < maxAttempts)` loop with `usePollingJob` (isComplete callback). This adds: scope cleanup, race guard, reactive error ref.

**Files to change:** `src/composables/useKnowledgeVectorization.ts` (`vectorizeDocument` method)

### Phase 5 — Dynamic-poller pattern cleanup

Multiple composables (`useServiceMessages`, `useAutoResearch`, `useAuditApi`, `useOperationsApi`) call `usePollingJob(...)` inside `startPolling()` functions. This violates Vue's rule that composables must be called at the top level of a `setup` context. Each should be refactored to call `usePollingJob` once at setup time and configure it via a reactive `intervalMs: Ref<number>`.

`usePollingJob` already accepts `intervalMs: Ref<number>` — the fix is a one-line change per consumer.

**Files to change:** `useServiceMessages.ts`, `useAutoResearch.ts`, `useAuditApi.ts`, `useOperationsApi.ts`, `usePatternAnalysis.ts`, `useBackgroundTask.ts`, `useKnowledgeVectorization.ts` (`startPolling` method)

---

## 6. Discovery Issues to File

The following GitHub issues should be created to track the migration work. The issues are **not created in this PR** — they are enumerated here for batch filing.

| Priority | Title | Scope | Labels |
|---|---|---|---|
| P1 | `refactor(composables): extract useTimerPoller Layer 1 primitive` | Create `useTimerPoller.ts`; refactor `useBackoffPoller` + `usePollingJob` internals | `tech-debt`, `refactor` |
| P1 | `fix(composables): replace inline while-loop polling in vectorizeDocument with usePollingJob` | `useKnowledgeVectorization.ts:353–395` — no race guard, no cleanup, blocking while loop | `bug`, `tech-debt` |
| P2 | `refactor(composables): add policy option to usePollingJob for backoff/circuit-breaker` | Add `policy: 'fixed' | 'backoff'` option to Layer 3 | `enhancement`, `refactor` |
| P2 | `fix(composables): dynamic usePollingJob creation inside startPolling() violates Vue composable rules` | `useServiceMessages`, `useAutoResearch`, `useAuditApi`, `useOperationsApi`, `usePatternAnalysis`, `useBackgroundTask`, `useKnowledgeVectorization` — composable called inside a non-setup function | `bug`, `tech-debt` |
| P3 | `refactor(composables): migrate ChatInterface to usePollingJob(policy: backoff)` | `ChatInterface.vue` — consolidate from `useBackoffPoller` to unified Layer 3 API | `tech-debt`, `refactor` |
| P3 | `feat(composables): add page-visibility pause to usePollingJob` | Port `visibilitychange` listener from `useBackoffPoller` to Layer 2 / expose as option in Layer 3 | `enhancement` |
| P3 | `test(composables): add useBackoffPoller unit tests` | `useBackoffPoller` has no test file; `usePollingJob` has `__tests__/usePollingJob.test.ts` | `test` |

---

## Appendix: Key Implementation Differences

### Timer mechanism

- `useBackoffPoller`: `setTimeout` chain — each tick schedules the next one. Interval varies per tick (backoff math applied after each failure).
- `usePollingJob`: `setInterval` with fixed cadence. Interval is set once at `start()` and read from `options.intervalMs` (plain or `Ref<number>`).
- Inline while-loop: `await new Promise(resolve => setTimeout(resolve, 1000))` — synchronous appearance in async context, no cancellation path.

### Race-condition handling

- `useBackoffPoller`: `inFlight` boolean. If a tick fires while the previous one is still awaiting, the new tick is skipped entirely and rescheduled.
- `usePollingJob`: `currentTaskId` string comparison. `start(taskId)` stores the task key; every `poll()` tick checks it before acting. Calling `start()` again discards any in-flight fetch from the previous task.
- Inline while-loop: no guard — a second parallel call to `vectorizeDocument(sameId)` will corrupt `documentStates`.

### Circuit breaker

Only `useBackoffPoller` has a circuit breaker. After `circuitBreakerThreshold` (default 3) consecutive failures, `isCircuitOpen` is set to `true`. Subsequent ticks skip the actual fetch and schedule a slow probe at `circuitBreakerResetMs` (default 60 s). The circuit auto-resets when the tab regains visibility.

### Scope cleanup

Both `useBackoffPoller` and `usePollingJob` call `onScopeDispose(stop)` when called inside a Vue scope, ensuring the timer is cleared when the owning component or `effectScope` is destroyed. The inline while-loop in `vectorizeDocument` has no such guarantee — if the component unmounts during vectorization, the loop continues running.

### Reactive state exposed

- `useBackoffPoller` exposes: `isCircuitOpen`, `consecutiveFailures`, `currentInterval` — circuit/backoff diagnostics.
- `usePollingJob` exposes: `isPolling`, `data`, `error`, `attempts` — job lifecycle state suitable for template binding.
- Inline while-loop: all state is local variables; nothing is reactive.
