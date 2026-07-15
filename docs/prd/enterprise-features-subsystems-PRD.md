# Enterprise Features Subsystems PRD

## Product overview

### Document

- Title: Enterprise Features Subsystems — making the stubs real
- Version: 0.1 (draft, pending owner sign-off)
- Status: Planning only — no implementation until this PRD is approved and attached to a GitHub epic
- Owner: mrveiss
- Related code: `autobot-backend/enterprise_feature_manager.py`, `autobot-backend/api/enterprise_features.py`

### Product summary

AutoBot exposes an "enterprise features" subsystem through `EnterpriseFeatureManager` and the `/api/enterprise` router. The API advertises capabilities — cross-VM load balancing, intelligent task routing, comprehensive health monitoring, graceful degradation, failover/recovery, web-research orchestration, and resource optimization — and reports them as "enabled" and "production-ready" with concrete-sounding numbers ("99.9%+ availability", "< 2ms cross-VM latency", "15-25% response-time improvement").

In reality every enablement path terminates in a logger-only stub. `enable_feature()` flips a status enum to `ENABLED` and returns a success payload, but the underlying `_create_*` methods only emit a log line and return. Hardware detection returns a hardcoded fake. Health checks always return `"healthy"`. This is a correctness and trust gap: the platform claims a production posture it does not have.

This project converts each advertised subsystem into a real implementation, wiring to existing infrastructure where it already exists (real hardware detection, the NPU worker manager, the circuit breaker, Prometheus metrics, the task queue) and building the missing pieces where it does not. It begins with an honest-reporting foundation so the API tells the truth before any subsystem is built, then delivers each subsystem behind that truthful surface.

## Goals

### Business goals

- Close the trust/correctness gap: the platform must never report a capability as enabled or a metric as achieved unless it is real and measured.
- Deliver a genuinely enterprise-grade operational posture for the two supported topologies: single-box and multi-node.
- Make the enterprise surface demonstrable — every claim in `/api/enterprise/*` must be backed by evidence (measured metric, live probe, or real component).
- Reduce operational risk by adding real health monitoring, circuit breaking, and failover so degraded conditions are detected and contained rather than silently claimed away.

### User goals

- An operator can trust the enterprise status page: what it says is enabled is enabled, what it reports as a metric is measured.
- An operator can route AI workloads to the correct hardware (NPU/GPU/CPU) and observe where each task ran.
- An operator can see real health across nodes/services and receive real alerts when something degrades.
- A developer relying on enterprise APIs (routing, health, degradation) gets real behavior, not a stub that always succeeds.

### Non-goals

- Not building a new multi-VM orchestration platform, container scheduler, or replacing the existing node/worker registry.
- Not implementing true blue-green / zero-downtime deployment in this epic — the `zero_downtime_deployment` and `enterprise_configuration_management` features stay explicitly out of scope and must be reported as `not_implemented` (see foundation task), not "completed".
- Not building auto-scaling of physical/virtual hardware (no cloud provisioning). "Auto-scaling" in configs is reinterpreted as workload placement, not machine provisioning.
- Not adding a new metrics backend — reuse the existing Prometheus infrastructure (`autobot_shared/monitoring/prometheus_metrics.py`, prometheus endpoint from #10720).
- Not rebuilding hardware detection — reuse `HardwareAccelerationManager` (#10717).
- Not rebuilding circuit-breaker primitives — reuse `autobot-backend/circuit_breaker.py`.
- Not changing authentication/authorization model — the router already gates on `check_admin_permission`; reuse it.

### What "enterprise-grade" means here

- Single-box topology: subsystems operate correctly when only the main node exists (no fake peer VMs). Load balancing and health monitoring degrade to "single-target" mode and report honestly.
- Multi-node topology: subsystems distribute and monitor work across the real nodes present in the node/worker registry, not the hardcoded 6-VM table.
- Truthful reporting: every capability flag reflects a real, initialized component; every numeric metric is measured or explicitly labeled as unavailable.

## User personas

### Key user types

- Platform operator / administrator — enables features, watches health, responds to alerts.
- Backend developer — consumes routing/health/degradation APIs and internal services.
- Site reliability / on-call — relies on health monitoring, circuit breakers, and failover during incidents.

### Basic persona details

- Operator: admin-authenticated, uses the enterprise status/infrastructure endpoints and the GUI surfaces that read them. Cares about truthfulness and actionable state.
- Developer: integrates task routing and health signals into agent/workflow code paths. Cares about stable contracts and real behavior.
- On-call: reacts to degradation. Cares that circuit breakers actually open, fallbacks actually engage, and recovery is real.

### Role-based access

- All `/api/enterprise/*` mutating and status endpoints require admin permission (already enforced via `router = APIRouter(dependencies=[Depends(check_admin_permission)])` in `autobot-backend/api/enterprise_features.py:40`).
- Internal subsystem services (router, health monitor, degradation manager) are process-internal singletons and are not directly reachable without going through the admin-gated API or authenticated internal callers.
- Prometheus scrape endpoint access follows the existing metrics endpoint policy (#10720) — no change.

## Functional requirements

Requirements are grouped per subsystem. Priority: P0 (must ship for the epic to close), P1 (should ship), P2 (nice to have / follow-up).

### FR-0 Honest reporting and real hardware detection (P0, foundation)

Prerequisite for everything else. Today the API reports fabricated state and metrics.

- Must-do:
  - Replace `_detect_hardware_capabilities` (`enterprise_feature_manager.py:831-837`, hardcoded RTX_4070/Intel_NPU/22-core fake) with a call into the real `HardwareAccelerationManager` (`autobot-backend/hardware_acceleration.py`).
  - Replace the hardcoded VM topology resource blocks (`enterprise_feature_manager.py:118` cpu_cores/RTX_4070, `:145` Intel_NPU, etc.) with real values sourced from hardware detection for the local node and from the node/worker registry for peers. In single-box mode, only real nodes appear.
  - Make `_check_feature_health` (`:855`) return a real probe result instead of a constant `"healthy"`.
  - Make capability flags reflect real component initialization, not just a status enum flip. A feature is `ENABLED` only if its real component constructed and passed a startup self-check.
  - Replace fabricated metrics with measured or honestly-unavailable values:
    - `_build_production_readiness` (`api/enterprise_features.py:94`) hardcoded "99.9%+", "Enterprise-grade security".
    - `_build_deployment_phases` (`:123`) all-"completed" fake phases.
    - `_build_optimization_results` (`:215`) fake "15-25%"/"20-30%" improvements.
    - `/infrastructure` performance block (`:551`) "< 2ms", "99.9%+", "Optimized".
  - Out-of-scope features (`zero_downtime_deployment`, `enterprise_configuration_management`, `automated_backup_recovery`, `advanced_knowledge_search`, `dynamic_resource_allocation`) must report a distinct `not_implemented` (or `planned`) status rather than being enable-able to a fake `ENABLED`.
- Reuses: `HardwareAccelerationManager` (#10717); node/worker registry (`services/npu_worker_manager.py`, `api/npu_workers.py`); config SSOT (`autobot_shared.ssot_config`).
- New components: an honest status/metrics assembler; a per-feature "real component present?" gate.
- Data/state: none persistent beyond what components already hold; hardware detection cached in-process.
- Failure modes: hardware detection unavailable (OpenVINO/nvidia-smi missing) → report device as `available: false`, never fabricate. Registry empty → single-box mode.
- Success metrics: zero fabricated fields remain in any `/api/enterprise/*` response (audited); every `ENABLED` feature maps to a live component; hardware report matches `nvidia-smi`/`lspci`/OpenVINO on the host.

### FR-1 Cross-VM / cross-node load balancing (P0)

- Must-do:
  - Replace `_create_load_balancer_service` (`:827`, logger-only) with a real load balancer that selects a target node for a unit of work from the live registry.
  - Support the algorithms already declared in config (`weighted_round_robin`, capability-based, health-based failover; `enterprise_feature_manager.py:286-294`).
  - Weight selection by real signals: current load, health status, and declared capabilities from the registry — not the hardcoded resource table.
  - Single-box mode: deterministically select the local node and report `mode: single_target` honestly.
  - Exclude nodes that are unhealthy (per FR-3) or whose circuit breaker is open (per FR-4).
- Reuses: node/worker registry and health signals from `services/npu_worker_manager.py` (registration, heartbeat, backoff, failover monitor); `TaskQueue` (`utils/task_queue.py`) as the dispatch substrate; Redis for shared load/state; Prometheus for per-target counters.
- New components: `LoadBalancer` service (target selection + algorithm strategies); load/weight snapshot reader.
- Data/state: current per-node load counters in Redis; last-selected pointer for round-robin (Redis, per-worker-safe).
- Failure modes: all targets unhealthy → raise a typed "no healthy target" error, do not silently pick a dead node; registry unreachable → fall back to local node and report degraded.
- Success metrics: selection excludes unhealthy/open-circuit nodes 100% of the time in tests; distribution across N healthy nodes within expected weighting tolerance; per-target dispatch counters visible in Prometheus.

### FR-2 Intelligent task routing engine (P0)

- Must-do:
  - Replace `_create_task_routing_engine` (`:839`, logger-only) with a real engine that maps a task's declared requirement class (`ai_tasks`, `gpu_tasks`, `cpu_tasks`, `memory_tasks`; `enterprise_feature_manager.py:311-316`) to a hardware-appropriate target.
  - Consume real hardware capabilities from FR-0 (per-node NPU/GPU/CPU availability).
  - Honor the resource-pool routing logic already defined (`_initialize_resource_pools`, `:205-242`): `npu_preferred` → NPU worker nodes, `gpu_required` → GPU nodes, else CPU.
  - Delegate final target choice to the FR-1 load balancer within the eligible pool.
  - Record where each task actually ran (for observability and future performance-history routing).
- Reuses: FR-0 hardware capabilities; FR-1 load balancer; NPU worker manager for NPU targets; `TaskQueue` registry (`utils/task_queue.py`) for dispatch; Prometheus task metrics.
- New components: `TaskRoutingEngine` (requirement-class → eligible-pool resolver); routing-decision recorder.
- Data/state: routing decisions logged to Redis/Prometheus; optional short-horizon performance history (P1) — the 7-day performance history in config (`:317`) is P1, not P0.
- Failure modes: no node satisfies a hard requirement (e.g. `gpu_required` but no GPU) → typed error + honest report, never silent CPU substitution unless policy allows a labeled fallback.
- Success metrics: `gpu_required` tasks never land on a GPU-less node; NPU-preferred tasks land on NPU nodes when present; routing decision observable per task.

### FR-3 Comprehensive health monitoring (P0)

- Must-do:
  - Replace `_create_health_monitoring_system` (`:843`) and `_start_health_monitoring` (`:851`) with a real background monitor.
  - Probe real service endpoints (`_get_all_service_endpoints`, `:859`) and node health on the configured interval (`health_check_interval`, default 30s).
  - Compute real status per target (healthy / degraded / critical) against real thresholds (`response_time_ms`, `error_rate_percent`, `resource_usage_percent`; `enterprise_feature_manager.py:644-648`).
  - Feed health state to FR-1 (target exclusion) and FR-4 (degradation triggers).
  - Emit health as Prometheus metrics and through the existing event buses for live UI.
- Reuses: NPU worker manager's existing health-check loop, heartbeat staleness detection, and exponential backoff (`services/npu_worker_manager.py:192-411`) as the pattern/engine to generalize; `ServiceHealthMetricsRecorder` in `autobot_shared/monitoring/prometheus_metrics.py`; both event buses (RedisEventStreamManager + LiveEventManager).
- New components: `HealthMonitor` that generalizes the NPU worker health loop to arbitrary service/node endpoints; health-state store.
- Data/state: current health snapshot in Redis; rolling history for trend (P1); the 30-day predictive-health config (`:369-370`) is P2.
- Failure modes: probe timeout → mark degraded/critical with reason, never mark healthy on timeout; monitor task crash → supervised restart, surfaced as an alert.
- Success metrics: `_check_feature_health` reflects the last real probe; a killed dependency transitions to critical within one check interval; health metrics scrapeable.

### FR-4 Graceful degradation — circuit breaker + fallback (P0)

- Must-do:
  - Replace `_create_degradation_system` (`:847`, logger-only for both circuit + fallback config) with a real wiring of the existing circuit-breaker primitive plus a fallback manager.
  - Instantiate circuit breakers per protected dependency using the config already passed (`failure_threshold: 5`, `recovery_timeout: 60`, `half_open_max_calls: 3`; `enterprise_feature_manager.py:672-676`).
  - Implement the declared degradation levels (`full`, `limited`, `basic`, `emergency`; `:382`) as real operating modes with defined behavior at each level.
  - Wire real fallback endpoints (`_get_fallback_endpoints`, `:867`) so that when a primary is open, calls route to the fallback.
  - Recovery strategies (`restart`, `failover`, `scale_out`; `:383`): implement `failover` (P0, via FR-1) and `restart` where applicable (P1); `scale_out` is out of scope (see non-goals).
- Reuses: `autobot-backend/circuit_breaker.py` (`CircuitBreaker`, `CircuitState`, `call_async`, half-open logic) — do not rebuild; FR-1 load balancer for failover; FR-3 health state as a degradation trigger.
- New components: `DegradationManager` (owns per-dependency breakers, current degradation level, fallback routing); level-transition policy.
- Data/state: breaker state is in-process per worker (note: 4 uvicorn workers → breakers are per-worker; shared state via Redis is P1 and must be called out); current degradation level in Redis for cross-worker consistency.
- Failure modes: fallback also down → escalate to next degradation level, report `emergency`; breaker stuck open beyond `max_degradation_time_minutes` (`:384`) → alert.
- Success metrics: N consecutive failures opens the breaker; open breaker routes to fallback; recovery closes the breaker after `recovery_timeout`; degradation level observable.

### FR-5 Failover / recovery (P0)

- Must-do:
  - Turn the advertised `health_based_failover` / `automatic_failover` capabilities into real behavior: when FR-3 marks a target critical or FR-4 opens its breaker, in-flight and new work is redirected to a healthy target by FR-1.
  - Implement recovery: when a failed target returns to healthy, it is re-admitted to the eligible pool.
  - Reuse and generalize the NPU worker manager's failover monitor (`services/npu_worker_manager.py`, failover monitor task started at `:199-202`) rather than inventing a parallel mechanism.
- Reuses: NPU worker manager failover monitor; FR-1 load balancer; FR-3 health; FR-4 breakers.
- New components: a thin failover coordinator that connects health/breaker transitions to registry admission/eviction (may live inside `HealthMonitor` + `LoadBalancer`).
- Data/state: node admission state in the registry/Redis.
- Failure modes: flapping node (rapid healthy/unhealthy) → apply hysteresis/backoff (reuse existing backoff logic, `:257-292`); all nodes failed → emergency degradation (FR-4).
- Success metrics: failover redirect happens within one detection interval; recovered node re-admitted; no work dispatched to an evicted node.

### FR-6 Web-research orchestration (P1)

- Must-do:
  - Replace `_update_chat_workflow_config` (`:819`) and `_initialize_research_endpoints` (`:823`) — both logger-only — with real wiring into the existing research/chat-workflow stack.
  - Determine whether "enable" should mutate real chat-workflow configuration or simply verify that the already-present research capability (librarian agents, MCP integration, `workflow_templates/research.py`, `api/knowledge_research_ws.py`) is reachable and report honestly. (Open question O-3.)
  - The `/api/research/health` endpoint declared as the feature's health check (`enterprise_feature_manager.py:259`) must return a real probe of the research subsystem.
- Reuses: existing research/librarian stack (`async_chat_workflow.py`, `workflow_templates/research.py`, `api/knowledge_research_ws.py`, `mcp/autobot_server.py`); FR-3 health monitor.
- New components: minimal — a config-applier and a real research health probe; avoid duplicating existing research orchestration.
- Data/state: chat-workflow config (existing store); no new persistence expected.
- Failure modes: research backend unavailable → feature reports degraded, does not claim enabled.
- Success metrics: enabling the feature produces an observable, reversible change (or a truthful "already available" report); `/api/research/health` reflects real state.

### FR-7 Resource optimization (P1)

- Must-do:
  - Replace the fabricated `_build_optimization_results` (`api/enterprise_features.py:215`, fake "15-25%" numbers) with real optimization actions and measured before/after metrics, or clearly report "optimization not yet measurable" until baseline data exists.
  - Base "optimization" on the real routing (FR-2) and load-balancing (FR-1) signals rather than static claims.
  - The `/performance/optimize` endpoint (`:487`) must gate on real resource capability (it already calls `_check_resource_capabilities`, `:506`) and only report improvements it can measure.
- Reuses: FR-1, FR-2, Prometheus performance metrics (`PerformanceMetricsRecorder`).
- New components: an optimizer that adjusts routing weights/pool assignments and measures effect.
- Data/state: baseline and post-change metric snapshots (Prometheus/Redis).
- Failure modes: insufficient data for a baseline → report honestly, do not fabricate percentages.
- Success metrics: any reported improvement is derived from a real measured delta; no hardcoded percentages remain.

## User experience

### Entry points

- Admin API under `/api/enterprise/*` (`autobot-backend/api/enterprise_features.py`): `/status`, `/features`, `/features/enable`, `/features/enable-all`, `/features/bulk-enable`, `/infrastructure`, `/performance/optimize`, `/phase4/validation`, `/deployment/zero-downtime`.
- Any GUI surface that reads these endpoints (enterprise/infrastructure status views).
- Prometheus scrape endpoint for the new metrics.

### Core experience

- Operator opens the enterprise status view → sees only real features, with honest statuses (`enabled`, `disabled`, `degraded`, `error`, `not_implemented`).
- Operator enables a subsystem → the real component initializes and self-checks; success means the component is live, failure returns a real error.
- Operator views infrastructure → sees real nodes from the registry with real hardware, real health, and measured metrics (or explicit "unavailable").
- On degradation → operator sees the circuit breaker open, fallback engaged, degradation level, and (later) recovery — all reflecting real state.

### Advanced features

- Performance-history-based routing (FR-2 P1), predictive health (FR-3 P2), cross-worker shared breaker state (FR-4 P1), measured optimization deltas (FR-7 P1).

### UI/UX highlights

- Truthfulness first: no fabricated numbers anywhere; unavailable metrics are labeled unavailable.
- Clear separation of `enabled` vs `not_implemented` so operators never mistake a planned feature for a live one.
- Health and degradation states surface through the existing event buses for live updates.

## Narrative

As an operator I open AutoBot's enterprise status page expecting it to tell me the truth. Today it tells me every feature is enabled and the platform runs at "99.9%+ availability with < 2ms cross-VM latency" — numbers that were never measured, on VMs that may not exist. After this project, the page shows exactly the nodes I actually run, the real NPU/GPU/CPU on each, and the live health of every service. When I enable intelligent task routing, my GPU jobs actually land on the GPU node and my NPU jobs on the NPU worker. When a node degrades, I watch its circuit breaker open, traffic shift to a healthy target, and the node rejoin the pool once it recovers. Every claim on the page is now something I can verify — and when something is not yet built, the page says so plainly instead of pretending.

## Success metrics

### User-centric

- Zero fabricated fields across `/api/enterprise/*` (audited against a fixture list of the current fake values).
- Operators can correctly identify, from the status page alone, which subsystems are real vs planned (validated in review).
- A deliberately failed dependency is reflected as degraded/critical within one health-check interval.

### Business

- Enterprise claims are defensible: every advertised capability maps to a live, testable component.
- Reduced incident blast radius: circuit breakers + failover contain a dependency failure instead of it propagating.

### Technical

- Hardware report matches host tools (`nvidia-smi`, `lspci`, OpenVINO) on both single-box and multi-node.
- Load balancer never selects an unhealthy or open-circuit target (100% in tests).
- `gpu_required` never routes to a GPU-less node; NPU-preferred routes to NPU nodes when present.
- Circuit breaker opens after `failure_threshold` failures and recovers after `recovery_timeout` (unit + e2e verified).
- New subsystems expose Prometheus metrics scrapeable via the existing endpoint (#10720).

## Technical considerations

### Integration points

- `HardwareAccelerationManager` (`autobot-backend/hardware_acceleration.py`, #10717) — real NPU/GPU/CPU detection; replaces the fake in FR-0/FR-2.
- Node / NPU worker registry (`services/npu_worker_manager.py`, `api/npu_workers.py`) — live topology, health loop, heartbeat, backoff, failover monitor; substrate for FR-1/FR-3/FR-5.
- `CircuitBreaker` (`autobot-backend/circuit_breaker.py`) — reused verbatim for FR-4.
- `TaskQueue` (`utils/task_queue.py`) — dispatch substrate for FR-1/FR-2.
- Prometheus (`autobot_shared/monitoring/prometheus_metrics.py`, `api/prometheus_endpoint.py`, #10720) — metrics for all subsystems.
- Redis (`autobot_shared.redis_client`) — shared load counters, health snapshots, degradation level.
- Event buses — RedisEventStreamManager (agent loop) and LiveEventManager (WS); publish health/degradation to both.
- Config SSOT (`autobot_shared.ssot_config`) — hosts/ports/topology; never hardcode.

### Data storage and privacy

- No new user data. Operational state (load counters, health snapshots, breaker/degradation state) lives in Redis with bounded TTLs (TTL from env-backed module constants, never hardcoded — per project rule).
- Metrics contain no PII. Admin-gated endpoints unchanged.

### Scalability and performance

- Backend runs 4 uvicorn workers → in-process singletons (breakers, in-memory selection pointers) are per-worker. Cross-worker consistency (degradation level, round-robin pointer, shared breaker state) must use Redis. This is called out per subsystem; shared breaker state is P1.
- Health probing must be async and bounded (reuse the NPU manager's backoff to avoid probe storms).
- Load-balancer selection must be O(nodes) and cache the registry snapshot.

### Potential challenges

- Single-box vs multi-node divergence: subsystems must behave and report correctly with exactly one real node. Avoid the current fake 6-VM assumption.
- Per-worker vs shared state: naive in-process breakers give inconsistent cross-worker behavior.
- Avoiding duplication: research orchestration and health monitoring have existing engines — generalize/reuse, do not fork (per feedback: "distinguish unwired from orphan", "grep existing solutions before building").
- Honest metrics require baselines: FR-7 cannot report deltas until baseline data exists.

## Milestones and sequencing

### Project estimate

- Medium-to-large. Roughly 9–12 PRs across 4 phases. Foundation is a hard prerequisite for all subsystem work.

### Team size

- 1–2 backend engineers; reviews via code-reviewer per project workflow.

### Suggested phases (dependency-ordered task breakdown)

Each task is intended to become a GitHub sub-issue under the epic, one PR each. Effort: S (< ~0.5 day), M (~1–2 days), L (~3+ days).

Phase 0 — Foundation (honest reporting + real hardware). Prerequisite for all later phases.

- T1 (M, P0, prereq for all): Real hardware detection + honest status/metrics. Wire `_detect_hardware_capabilities` to `HardwareAccelerationManager`; source topology resources from hardware + registry; make `_check_feature_health` real; strip fabricated fields from `_build_production_readiness`, `_build_deployment_phases`, `_build_optimization_results`, and the `/infrastructure` performance block; add `not_implemented`/`planned` status for out-of-scope features and prevent them from reporting fake `ENABLED`. Depends on: none. Blocks: T2–T9.

Phase 1 — Health + topology substrate (unblocks routing, LB, degradation).

- T2 (L, P0): Health monitoring subsystem. Generalize the NPU worker health loop into a `HealthMonitor` probing services/nodes; real thresholds; Prometheus + event-bus emission; back `_create_health_monitoring_system`/`_start_health_monitoring`. Depends on: T1. Blocks: T3, T5, T6.
- T3 (M, P0): Registry-backed topology reader. Replace hardcoded VM topology consumption with a live node reader (single-box + multi-node modes) used by LB and health. Depends on: T1. Blocks: T4, T5.

Phase 2 — Load balancing, routing, degradation, failover.

- T4 (L, P0): Cross-node load balancer. `LoadBalancer` with weighted-round-robin/capability/health-based strategies; excludes unhealthy/open-circuit targets; single-target mode. Backs `_create_load_balancer_service`. Depends on: T2, T3. Blocks: T6, T7.
- T5 (L, P0): Task routing engine. `TaskRoutingEngine` mapping requirement classes to eligible hardware pools using T1 capabilities; delegates target choice to T4; records routing decisions. Backs `_create_task_routing_engine`. Depends on: T1, T3, T4. Blocks: T9 (optimization).
- T6 (L, P0): Graceful degradation. `DegradationManager` wiring existing `CircuitBreaker` per dependency + fallback routing + degradation levels; Redis-backed degradation level. Backs `_create_degradation_system`. Depends on: T2, T4. Blocks: T7.
- T7 (M, P0): Failover + recovery coordinator. Connect health/breaker transitions to registry admission/eviction and LB redirect; hysteresis for flapping. Depends on: T4, T6. Blocks: none.

Phase 3 — Research + optimization + hardening (P1).

- T8 (M, P1): Web-research orchestration wiring. Replace `_update_chat_workflow_config` / `_initialize_research_endpoints` with real wiring or truthful "already available" reporting; real `/api/research/health`. Depends on: T1. (Resolve O-3 first.)
- T9 (M, P1): Measured resource optimization. Replace fake optimization percentages with measured before/after deltas from T5/T4 signals; honest "no baseline yet". Depends on: T4, T5.
- T10 (M, P1): Cross-worker shared state. Move breaker/degradation/round-robin state to Redis for consistency across the 4 uvicorn workers. Depends on: T4, T6.
- T11 (S, P2): Predictive health + performance-history routing scaffolding (only if owner wants it now; otherwise defer). Depends on: T2, T5.

## User stories

### US-001 — Admin authentication for enterprise endpoints

- Description: As an operator, I must be authenticated as an admin to access any enterprise feature endpoint so that operational controls are protected.
- Acceptance criteria:
  - All `/api/enterprise/*` endpoints reject unauthenticated requests.
  - All `/api/enterprise/*` endpoints reject authenticated non-admin users with a 403.
  - An authenticated admin can reach every enterprise endpoint.
  - The existing `check_admin_permission` dependency remains the single enforcement point (no per-endpoint bypass).

### US-002 — Real hardware reported in status

- Description: As an operator, I want the enterprise status to report the actual hardware present so I can trust capacity claims.
- Acceptance criteria:
  - Hardware capabilities come from `HardwareAccelerationManager`, not a hardcoded dict.
  - On a host with no NVIDIA GPU, the report shows GPU `available: false` (no fabricated RTX_4070).
  - On a host with no NPU, the report shows NPU `available: false`.
  - CPU core count matches the host's real count.
  - The report matches `nvidia-smi` / `lspci` / OpenVINO on the host.

### US-003 — No fabricated metrics in any enterprise response

- Description: As an operator, I want every metric shown to be measured or explicitly unavailable so I am never misled.
- Acceptance criteria:
  - `_build_production_readiness` no longer returns hardcoded "99.9%+"/"Enterprise-grade security" strings.
  - `_build_optimization_results` no longer returns hardcoded percentage ranges.
  - `/infrastructure` no longer returns "< 2ms" / "99.9%+" / "Optimized" placeholders.
  - Any metric without a real source is labeled `unavailable` (or omitted), never invented.
  - An audit test asserts none of the known fake strings appear in any enterprise response.

### US-004 — Planned features reported honestly

- Description: As an operator, I want features that are not implemented to be labeled as such so I do not mistake them for live capabilities.
- Acceptance criteria:
  - `zero_downtime_deployment`, `enterprise_configuration_management`, `automated_backup_recovery`, `advanced_knowledge_search`, and `dynamic_resource_allocation` report a `not_implemented`/`planned` status.
  - Attempting to enable an out-of-scope feature returns a clear "not implemented" response, not a fake success.
  - `/deployment/zero-downtime` does not return a fabricated all-"completed" phase list.

### US-005 — Feature enablement reflects a real component

- Description: As an operator, when I enable a subsystem I want it to actually initialize so "enabled" is truthful.
- Acceptance criteria:
  - `enable_feature` sets status to `ENABLED` only after the real component constructs and passes a startup self-check.
  - If component initialization fails, status becomes `ERROR` with a real error message.
  - Re-reading `/status` shows the component as live (not just a flipped enum).

### US-006 — Real per-feature health checks

- Description: As an operator, I want health checks to reflect real probes so degraded features are visible.
- Acceptance criteria:
  - `_check_feature_health` returns the result of a real probe, not a constant `"healthy"`.
  - Killing a monitored dependency causes its feature health to become critical/degraded within one check interval.
  - Health results are timestamped with the actual last-probe time.

### US-007 — Health monitoring across services and nodes

- Description: As an on-call engineer, I want continuous health monitoring so I detect problems proactively.
- Acceptance criteria:
  - A background monitor probes all configured service endpoints on the configured interval.
  - Status is computed against real thresholds (response time, error rate, resource usage).
  - Health transitions are emitted to Prometheus and both event buses.
  - Probe timeouts mark the target degraded/critical, never healthy.
  - The monitor task is supervised and restarts if it crashes, surfacing an alert.

### US-008 — Load balancing selects a healthy target

- Description: As a developer, I want work dispatched to a healthy node so failures do not get routed to dead targets.
- Acceptance criteria:
  - The load balancer selects targets only from live registry nodes.
  - Unhealthy nodes (per health monitor) are excluded from selection.
  - Nodes with an open circuit breaker are excluded.
  - With multiple healthy nodes, distribution follows the configured weighting within tolerance.
  - When no healthy target exists, a typed "no healthy target" error is raised (no silent dead-node pick).

### US-009 — Single-box load balancing degrades honestly

- Description: As an operator running a single box, I want load balancing to work and report its real mode.
- Acceptance criteria:
  - With one node in the registry, the balancer deterministically selects the local node.
  - Status reports `mode: single_target` (or equivalent), not a fake multi-VM distribution.
  - No fabricated peer VMs appear in `/infrastructure`.

### US-010 — Hardware-aware task routing

- Description: As a developer, I want tasks routed to the right hardware class so GPU/NPU work runs where it can.
- Acceptance criteria:
  - `gpu_required` tasks are never dispatched to a node without a GPU.
  - `ai_tasks` (NPU-preferred) are dispatched to NPU nodes when present.
  - `cpu_tasks` are dispatched to CPU-optimized targets.
  - Final target within the eligible pool is chosen by the load balancer.
  - Each routing decision (task → chosen node + reason) is recorded and observable.

### US-011 — Routing failure is explicit

- Description: As a developer, I want an explicit error when no node can satisfy a hard requirement so I am not silently mis-routed.
- Acceptance criteria:
  - When a hard requirement (e.g. GPU) cannot be met, a typed error is returned.
  - No silent substitution to an ineligible node occurs unless a labeled fallback policy is explicitly enabled.
  - The failure is logged and surfaced in metrics.

### US-012 — Circuit breaker opens on repeated failures

- Description: As an on-call engineer, I want a failing dependency's breaker to open so cascading failures are contained.
- Acceptance criteria:
  - After `failure_threshold` consecutive failures, the dependency's breaker transitions to open.
  - While open, calls to the dependency are short-circuited (not attempted against the dead target).
  - The breaker uses the existing `CircuitBreaker` primitive (no reimplementation).
  - Breaker state is observable via status/metrics.

### US-013 — Fallback engages during degradation

- Description: As an on-call engineer, I want fallback routing when a primary is open so service continues in a reduced mode.
- Acceptance criteria:
  - When a primary dependency's breaker is open, calls route to the configured fallback endpoint.
  - The current degradation level (`full`/`limited`/`basic`/`emergency`) is computed and reported.
  - If the fallback is also down, the system escalates to the next degradation level and reports `emergency`.
  - Degradation level is consistent across uvicorn workers (Redis-backed).

### US-014 — Automatic recovery closes the breaker

- Description: As an on-call engineer, I want automatic recovery so the system returns to full service without manual intervention.
- Acceptance criteria:
  - After `recovery_timeout`, the breaker transitions to half-open and probes the dependency.
  - On successful probes, the breaker closes and normal routing resumes.
  - A breaker open beyond `max_degradation_time_minutes` raises an alert.

### US-015 — Failover redirects work to a healthy node

- Description: As an on-call engineer, I want work redirected when a node fails so tasks still complete.
- Acceptance criteria:
  - When a node becomes critical or its breaker opens, new work is directed to a healthy node by the balancer.
  - No new work is dispatched to an evicted node.
  - Failover redirect occurs within one detection interval.

### US-016 — Recovered node is re-admitted

- Description: As an on-call engineer, I want a recovered node to rejoin so capacity is restored.
- Acceptance criteria:
  - When a previously failed node returns to healthy, it is re-admitted to the eligible pool.
  - Hysteresis/backoff prevents a flapping node from being repeatedly admitted/evicted.
  - Re-admission is observable in status/metrics.

### US-017 — Web-research feature reports real state

- Description: As an operator, I want the research feature to reflect the real research subsystem so its status is trustworthy.
- Acceptance criteria:
  - Enabling web-research orchestration performs a real, reversible config change or returns a truthful "already available" report (per resolved O-3).
  - `/api/research/health` returns a real probe of the research subsystem.
  - If the research backend is unavailable, the feature reports degraded, not enabled.

### US-018 — Resource optimization reports measured results

- Description: As an operator, I want optimization results based on real measurements so improvement claims are credible.
- Acceptance criteria:
  - `/performance/optimize` gates on real resource capability being enabled.
  - Reported improvements are computed from real before/after metric deltas.
  - When no baseline exists, the response says so instead of returning fabricated percentages.

### US-019 — Enterprise subsystems expose Prometheus metrics

- Description: As an operator, I want new subsystem metrics scrapeable so I can dashboard and alert on them.
- Acceptance criteria:
  - Load-balancer per-target dispatch counts, health states, breaker states, and degradation level are exposed via the existing Prometheus endpoint.
  - Metrics use the existing `PrometheusMetricsManager` recorders (no new backend).
  - Metrics contain no PII.

### US-020 — Operational state survives worker boundaries

- Description: As an operator, I want consistent behavior across the 4 uvicorn workers so shared decisions are coherent.
- Acceptance criteria:
  - Round-robin selection, degradation level, and (P1) breaker state are backed by Redis where cross-worker consistency is required.
  - Redis keys use TTLs sourced from env-backed constants (no hardcoded TTLs).
  - Behavior is verified with more than one worker in an integration test.

## Risks and open questions

### Risks

- R-1: Per-worker in-process state (breakers, round-robin) causing inconsistent behavior across the 4 uvicorn workers if T10 is deferred — mitigate by making cross-worker-critical state Redis-backed from the start where feasible.
- R-2: Duplicating existing research or health engines instead of generalizing them — mitigate via pre-flight grep and reuse of NPU worker manager + research stack.
- R-3: Single-box assumptions leaking (fake peers) — mitigate with explicit single-target mode tests.
- R-4: `git push != deploy` lag — merged fixes are inert until the next Ansible sync; verification must run against the codebase, and any live-box validation must account for sync timing.
- R-5: Scope creep into true zero-downtime deployment / auto-scaling — explicitly out of scope; enforce via the `not_implemented` reporting in T1.

### Open questions (for owner sign-off)

- O-1: For single-box deployments, is any real "cross-VM" load balancing meaningful, or should FR-1 be explicitly single-target-only until a second node exists? (Affects T4 scope.)
- O-2: Should circuit-breaker/degradation state be shared across uvicorn workers in the initial P0 (raising T6 effort) or accepted as per-worker until T10?
- O-3: Web-research "enable" semantics — mutate chat-workflow config, or verify-and-report-available only? (Affects T8 scope and reversibility.)
- O-4: Do we keep the `/deployment/zero-downtime`, `enterprise_configuration_management`, and `automated_backup_recovery` endpoints/features as `not_implemented` placeholders, or remove them from the surface entirely?
- O-5: What is the authoritative source for the node list in multi-node mode — the NPU worker registry only, or a broader node registry that also includes non-NPU service nodes?
- O-6: Are `scale_out` recovery and `dynamic_resource_allocation` permanently out of scope (no machine provisioning), or planned for a later epic?
- O-7: What baseline window and metric set define a "real" optimization delta for FR-7?
