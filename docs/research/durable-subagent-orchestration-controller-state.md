---
tags:
  - research
  - agents
  - orchestration
  - runtime
aliases:
  - Durable Subagent Orchestration
---

# Durable Subagent Orchestration via Controller-Owned State

**Phase 1 — Source analysis. Phase 2 — AutoBot comparison. Both complete.**

Source: a single-maintainer open-source local orchestration runtime for delegated coding
agents, a few months old, permissively licensed apart from its console. Identified only in the
operator chat reply, per the anonymization rule.

## Source Analysis: a local subagent-orchestration controller

### What It Is

A self-hosted controller that turns ad-hoc agent delegation into durable, transactional runtime
state. The user designs a *responsibility tree* (a reusable, versioned "team" of named members),
publishes a revision, and starts a run against it. A parent agent delegates to its direct
children through controller tools; the controller commits the fan-out, persists the parent's
wait, supervises every return, and resumes the parent once every child has returned a terminal
result. It drives two external agent CLIs as execution backends, exposes a React console and an
HTTP/MCP API, and installs itself as a per-user background service (systemd / LaunchAgent /
Scheduled Task) so runs survive a closed terminal.

Maturity: a few hundred source files of Python against a comparable mass of tests — the test
ratio is genuinely high. Single contributor, a heavy release cadence over a short life, and a
near-empty issue and PR history. Recent Python only, with an embedded relational store by
default and a server-backed option. The project has already been through one disruptive
identity change requiring a migration path for existing installs.

### Architecture & Key Patterns

- **Controller-owned state, provider-agnostic.** Every durable fact — assignments, waves, waits,
  checkpoints, replans, capabilities — lives in relational tables
  (`persistence/models/runtime/{delegation,waiting,dispatch,team,replan}.py`), never in a
  provider transcript. The provider session is disposable execution, not the record.
- **The agent's tool call *is* the transaction.** Children are given an MCP server
  (`interfaces/mcp/node/server.py`) exposing a fixed catalog of "node operations"
  (`runtime/node_operations/catalog.py`): `get_current_context`, `set_work_plan`, `checkpoint`,
  `delegate`, replan operations, `open_human_request`, `start_command_run`. Calling `delegate`
  atomically stages the whole wave and commits it (`runtime/delegation/fan_out.py`
  → `stage_delegation_wave`, with an `IntegrityError` → `CONFLICT` guard so two parents cannot
  hand the same child two open assignments).
- **Delegation ends the parent's process rather than blocking it.** A successful `delegate`
  closes the parent's dispatch; the parent is told to stop immediately and make no further calls.
  The parent is not a polling loop and not a suspended coroutine — it simply exits.
- **Fan-in is a database join, not a wait.** Each child's terminal checkpoint settles exactly one
  pending wave member in the same transaction as the checkpoint itself
  (`runtime/delegation/settlement.py` → `settle_wave_member_for_checkpoint`, a conditional
  `UPDATE ... RETURNING` guarded by an `EXISTS` on the wave still being open). When the last
  member settles, the wave settles and emits a `DelegationWaveSettled` signal; a handler opens
  *at most one* successor dispatch for the parent
  (`runtime/delegation/continuation.py` → `open_delegation_wave_successor`), which relaunches the
  parent agent with a fresh context containing every child result in delegation order.
- **Post-commit signal router.** An in-process typed `asyncio.Queue` dispatcher
  (`runtime/post_commit/router.py`) carries ~15 disposable scheduling hints
  (`post_commit/signals.py`: `WaveMemberSettled`, `DelegationWaveSettled`, `ReplanCommitted`,
  `HumanRequestDue`, `CommandRunDue`, `CommandProcessExited`, `WatchdogDue`, …). Routes are
  immutable after lifespan entry and each signal type has exactly one handler.
- **Signals are hints, never the source of truth.** If the queue is full, `publish` returns
  `False` and marks runtime health — and the caller falls back to performing the continuation
  inline (`settlement.py`, the `if not accepted:` branch). On controller start, a paginated
  startup audit re-reads every recoverable row family from the database and republishes the
  signals (`runtime/startup_audit.py`, `runtime/post_commit/bootstrap.py`). Crash recovery is
  therefore a database scan, not a memory reconstruction.
- **Layered package boundaries:** `runtime/` (domain + transactions), `persistence/`,
  `interfaces/{cli,http,mcp,web_console}`, `integrations/<provider>/`, `platform/` (OS services,
  workspace files, per-OS process guardians), `operator/` (a conversational front-end that calls
  the *same* controller operations as the GUI, explicitly so chat cannot create a second copy of
  product truth).

### Notable Implementation Details

- **Provider isolation strips the child agent's own orchestration machinery.**
  `integrations/claude/isolation.py` launches each child with subagents, artifacts, slash
  commands, bundled skills, project instruction files, background tasks, auto-memory and
  marketplace auto-install all disabled, via a settings blob plus a dozen `*_DISABLE_*`
  environment variables, and an always-disallowed tool list. The design rule is one orchestration
  authority per run: the controller. Nested provider-native delegation is not merely discouraged,
  it is made unavailable — and startup fails loudly (`ClaudeStartupIsolationError`) if the pinned
  CLI cannot prove the requested boundary.
- **Capabilities deny by default and narrow only downward.** `runtime/capabilities.py` resolves a
  member's *requested* capability set against a controller ceiling; the resolver has no widening
  path, and every effective value keeps its `CapabilitySource` so the console can show *why* a
  member may or may not ask a human, run a command, or reach the network. A denied capability
  carries a `next_legal_action` string that becomes advice inside the agent's prompt rather than
  an opaque refusal.
- **Three terminal outcomes with distinct semantics.** `green` (assignment done),
  `blocked` (a human or teammate must decide — a *terminal* result, not a failure), and `retry`
  (execution failure only: closes the dispatch and attempt, keeps the assignment open, lets the
  controller open a fresh attempt while budget remains). Changed feedback or scope explicitly
  requires a *fresh assignment*, never `retry` — the code enforces the split by preparing a
  separate "semantic retry" dispatch (`runtime/checkpoint/semantic_retry.py`) that re-resolves
  provider route, capabilities and team reads from scratch.
- **Provider success is not task success.** The prompt contract states that provider terminal
  success and another member's green checkpoint are *inputs to judgment*, not proof; only a
  controller-accepted terminal checkpoint from the task lead becomes the result. Prose that says
  "Checkpoint:" without calling the tool records nothing, and the prompt says so explicitly.
- **The manager behavior prompt is a genuine artifact** (`runtime/prompt/assets/behaviors/
  manager.txt`, ~6 KB). It forbids relaying (do not pass your assignment down unchanged, do not
  present a child's checkpoint as your own), requires deciding the *work shape* before
  delegating, names five orchestration patterns (sequence, parallel, iterative
  evaluator-optimizer, bounded batch map, hybrid) and ties each to a dependency/risk condition,
  prescribes a six-step integration routine on wave return, and imposes a participation minimum:
  every current direct child must return green at least once under its current configuration
  before the manager's own green is legal — with "remove an irrelevant child rather than invent
  filler work" as the stated escape.
- **Structural replan is subtree-bounded and revision-preserving.** A manager may add, update or
  remove descendants mid-run; a successful replan closes the current dispatch and the agent
  continues only from the fresh successor context. Earlier revisions, completed work and accepted
  history are not rewritten.
- **Per-OS process ownership is taken seriously.** Separate POSIX and Windows guardians, process
  owners, ownership-recovery and workspace-file/lease implementations
  (`runtime/command_run/`, `platform/workspace_files/`), rather than a shared lowest common
  denominator.
- **Waves are bounded to 1–8 children** per delegate call, checked before staging
  (`require_wave_size`).

### Strengths

- The core insight is sound and cleanly executed: **a parent that exits and is relaunched from
  committed state cannot leak a wait**, whereas a parent that stays resident polling its children
  loses everything when the terminal, the provider session or the host dies.
- Failure paths are designed, not bolted on: queue-full falls back to inline execution, startup
  re-derives work from rows, conditional SQL updates make settlement idempotent and
  double-settle-proof, and the recovery story is verifiable in code rather than asserted in a
  README.
- Test mass is proportionate to the runtime — roughly one test file for every two source files —
  including component, integration and real-backend end-to-end suites.
- The prompt assets encode orchestration *judgment* (when delegation is worth its cost, what a
  manager owes beyond paraphrase) rather than only schema mechanics — this is the part that
  transfers regardless of whether the runtime itself does.
- Honest about its own limits in the contract: "blocked" is a first-class outcome, and the
  documentation states that a one-member team is valid and usually wiser than ceremony.

### Weaknesses / Limitations

- **Bus factor 1.** A single contributor, and an issue and PR history close to empty. No second
  reviewer has exercised any of this.
- **Identity churn already once.** A disruptive rename shipped with a migration command,
  architecture decision records and explicit warnings about initialising before migrating. The
  release cadence is velocity, but also an unstable target for anyone pinning it.
- **The isolation layer depends on private, undocumented provider internals.** The dozen
  `*_DISABLE_*` environment variables and settings keys it sets on the child agent CLI are not a
  supported public interface; a provider release can silently remove or rename them, and the
  guarantee "only the controller orchestrates" quietly weakens without any test failing upstream.
- **"No polling" is narrower than the marketing.** The *parent agent* does not poll — true and
  valuable. The *controller* still runs deadline machinery: watchdog inactivity timeouts, human
  request deadlines, command-run deadlines (`post_commit/deadlines.py`, `WatchdogDue`). Timer
  supervision moved down a layer; it did not disappear.
- **The console is not under the permissive licence the project advertises.** It is
  source-available under a sustainable-use style licence inherited from the UI it was derived
  from: internal business, personal and non-commercial use only, redistribution limited to free
  non-commercial. The open-source headline does not cover the primary interface.
- **Every claim in the visible metrics is self-reported.** No independent benchmark, no
  third-party deployment report, no comparison harness. "Interruption recovery" is verifiable by
  reading the code (and I did), but *rates* — how often recovery succeeds under real provider
  failure — are unmeasured anywhere in the repo.
- **Adoption is an all-or-nothing posture.** The value is the transactional runtime; taking a
  piece of it (say, just the checkpoint semantics) means reimplementation, not integration.

### Visible vs Hidden Metrics

**Visible (all self-reported):** durable fan-out/fan-in across interruption; reusable versioned
teams; recursive delegation with no global polling loop; visual authoring canvas + conversational
operator over one shared operation set; a set of starter workflows; two provider backends; an
embedded default datastore with a server-backed option; cross-platform background service; a
modest star count.

**Hidden (what an adopter inherits):**

| Cost | Detail |
|---|---|
| New stateful service | A controller database (relational, with its own schema contract, forward-upgrade path and backup module) plus a per-user OS background service. Both need operating, backing up and upgrading. |
| Vocabulary tax | Workflow, revision, member, task, assignment, attempt, dispatch, wave, wait, checkpoint, boundary, replan, steering, human request, command run. Roughly fifteen terms before a first run — and they are load-bearing, not cosmetic. |
| Provider-internals coupling | Isolation rests on undocumented CLI env vars and settings keys; a provider upgrade is an unannounced breaking-change risk. |
| Bus factor / support | One maintainer, a codebase only months old, one disruptive identity change already. A blocking bug is yours to fix. |
| Licence split | The primary interface cannot be redistributed commercially; only the runtime carries the permissive licence. |
| Runtime cost of the model itself | Every delegation and every wave return *relaunches an agent with fresh context*. Durability is bought with re-established context on each continuation — the opposite of a cheap resident parent. Nothing in the repo measures this. |
| Recent-Python floor | Uses current-generation type-alias and generic syntax throughout; not backportable without rewriting. |

**Weighing:** the hidden costs do not undercut the central *idea* — they undercut *adopting the
implementation*. The transactional fan-in (checkpoint and wave-settlement in one transaction,
signals as hints with a database-scan fallback) and the delegation-ends-the-parent inversion are
genuinely good and worth stealing conceptually; they cost nothing to reason about and are
provider-neutral. The runtime that delivers them, however, arrives with a new stateful service, a
fifteen-term vocabulary, coupling to undocumented provider internals, a bus factor of one, and a
non-redistributable UI. For anyone who already owns an orchestration layer and a persistence
tier, the rational move is to lift the mechanism and the prompt contract, not the dependency.

The one unmeasured factor that could flip the verdict either way is the context cost of the
relaunch model: if re-establishing parent context on every wave return is expensive at depth,
durability is being paid for per-continuation, and the repo offers no numbers on that.

---


---

## AutoBot Comparison: the reference work → AutoBot

**Headline.** The reference work's entire architecture exists to solve one defect: *the parent's
wait for its children is not durable*. AutoBot has exactly that defect, in four places. It does
not bite today only because agent delegation is **off by default** — and the module that
implements it carries an eight-item enablement checklist with every box unchecked
(`autobot-backend/chat_workflow/delegation.py:33-58`). So the durability work below is not an
independent improvement; it is the **precondition** for ever setting
`AUTOBOT_DELEGATION_ENABLED=true`.

Our capability and approval model is meanwhile *stronger* than the source's, and our event-gap
honesty is stronger still. The gap is durability and reachability, not governance.

### What We Can Adopt

#### 1. Startup re-derivation of in-flight work from the durable row — **adopt**

- **Source pattern:** `runtime/startup_audit.py` + `post_commit/bootstrap.py` paginate every
  recoverable row family on controller start and republish the work signals, with an explicit
  pagination guard so a non-progressing scan raises instead of looping.
- **Already-exists audit:** AutoBot *already owns this pattern* in two places —
  `autobot-backend/initialization/lifespan.py:2043` calls `_recover_agent_sessions`
  → `llc/scheduler/session_checkpointer.py:112 recover_incomplete_runs()`, which selects
  `status='running'` rows, marks them `INTERRUPTED`, drops the Redis checkout lock and re-adds
  the agent to the heartbeat schedule; and `lifespan.py:2058 _recover_index_queue()` reloads
  queued index jobs from Redis. Confirmed absent for two others:
  - `services/process_adapter_service.py:70` constructs a fresh `asyncio.Queue()`, and `start()`
    (`:74-78`) only launches `_dispatch_loop()` against it. Grep for `process_runs` outside
    `migrations/` returns **zero** recovery call sites — a crash mid-subprocess leaves the
    Postgres row at `RUNNING` with nothing that will ever resume it.
  - `utils/long_running_operations/operation_manager.py:100` declares
    `self.operations: Dict[str, LongRunningOperation] = {}`, and `resume_operation` (`:409-418`)
    does `self.operations.get(checkpoint.operation_id)` then raises
    `ValueError(f"Original operation ... not found")`. The checkpoint survives on disk and in
    Redis (`checkpoint_manager.py:72-121`); the registry needed to act on it does not.
- **Delta to build:** two missing recovery call sites, matching a pattern we already ship twice.
- **Visible benefit:** stranded `process_runs` rows and orphaned operation checkpoints become
  recoverable instead of permanently unreachable.
- **Hidden cost:** low but real — recovery must be idempotent and bounded, or a boot after a
  long outage stampedes the dispatcher. The source's `STARTUP_AUDIT_PAGE_GUARD` is the shape to
  copy.
- **Effort:** moderate.

#### 2. A denial that names the next legal action — **adopt**

- **Source pattern:** `runtime/capabilities.py` pairs each denied capability with a
  `next_legal_action` string (e.g. for a denied command run: *"avoid long command; for example,
  run focused tests one by one rather than the whole test suite"*) which reaches the agent's
  prompt as advice rather than an opaque refusal.
- **Already-exists audit:** our denials are plain strings with no alternative —
  `chat_workflow/tool_dispatch_guards.py:63` builds
  `f"Tool '{tool_name}' is forbidden by agent '{agent_id}' capability manifest (matched
  '{matched}')"`; `middleware/builtin/permission_enforcement.py:124,136` raise bare
  `PermissionError`. **The carrier already exists and is unused here:**
  `utils/errors.py:14-77` defines `RepairableException(message, suggestion=...)` explicitly so
  "the LLM can then attempt an alternative approach", but grepping `suggestion` across
  `tool_dispatch_guards.py`, `permission_enforcement.py` and `orchestration/agent_registry.py`
  returns **zero hits** — it is wired only to OS-level tool failures (file-not-found, timeout).
- **Delta to build:** populate the existing `suggestion` field on the capability-denial paths.
- **Visible benefit:** a blocked agent stops burning turns retrying a tool it can never call.
- **Hidden cost:** denial text is model-visible, so guidance must not disclose manifest topology
  (which agent holds which boundary). Keep it generic — "use the read-only variant", not a dump
  of the forbidden set.
- **Effort:** trivial.

#### 3. Provenance on a capability decision — **adopt-with-conditions**

- **Source pattern:** every resolved value keeps a `CapabilitySource`, so the console can show
  *why* a member may or may not act — own request, controller ceiling, or default.
- **Already-exists audit:** `security/authority.py:56-63` `Authority.meet` tracks four surfaces
  separately (`approval_gates`, `forbidden_tools`, `permissions`, `capabilities`) and correctly
  distinguishes `None` (unconstrained) from an empty grant — but it returns merged frozensets
  with no origin. `tool_dispatch_guards.py:53-56` does `forbidden = forbidden | inherited.
  forbidden_tools`, which **erases** whether a block came from the agent's own manifest or from
  an inherited parent boundary; `:63-69` logs `agent_id` and `matched` but not the hop. Searched
  for `provenance`, `granted_by`, `PermissionResolution`, `effective_permission` — nothing
  beyond the unrelated LLC company-role `role_permission.py:178-223`.
- **Condition:** attach provenance to the **denial record**, not to `Authority` itself.
  `Authority` is a frozen dataclass on the hot dispatch path and `meet` is called per hop;
  widening it taxes every call site for a debugging benefit.
- **Visible benefit:** "which hop denied this" becomes answerable; delegation denials become
  debuggable at depth.
- **Hidden cost:** a second representation of the same decision can drift from the lattice.
- **Effort:** moderate.

#### 4. A pinned definition revision per run — **adopt-with-conditions (needs a decision)**

- **Source pattern:** every task pins the exact published workflow revision it started with;
  replans change future responsibility without rewriting earlier revisions or accepted history.
- **Already-exists audit:** no versioning on either definition family — `models/workflow.py:65`
  `class Workflow(Base)` has `status` but no version/revision/published column;
  `llc/models/role_workflow.py:33` likewise. A repo-wide grep for `(version|revision): Mapped`
  filtered to workflow/team/role models returns **zero**. `models/workflow_audit.py:22`
  `WorkflowAuditLog` records `user_id`/`workflow_id`/`action`/`details` — it answers *who
  changed what*, but a running instance still cannot name the definition version it began under.
- **Condition:** only worth the cost if definitions are actually edited while runs are in
  flight. If they are not, the audit log is the cheaper answer and this stays unbuilt.
- **Visible benefit:** a run's behaviour stays explainable after its definition moves.
- **Hidden cost:** a full revision lifecycle (draft → publish), migrations on two model
  families, and a new UI concept. This is the most expensive item here.
- **Effort:** significant.

#### 5. Publish-failure inline fallback — **rejected-by-hidden-metrics**

- **Source pattern:** when the post-commit queue rejects a signal, the caller performs the
  continuation inline (`settlement.py`, the `if not accepted:` branch).
- **Already-exists audit:** no inline fallback anywhere in AutoBot;
  `services/gateway/message_queue.py:63-66` catches `asyncio.QueueFull` and does
  `self.logger.error("Message queue full, dropping message")` — drop plus a log line.
- **Verdict:** **rejected.** Running the work inline on the producer's thread inverts the reason
  the bounded queue exists; under the exact load that fills the queue, the fallback cascades
  latency into the producer. The right fix for our drop path is observability plus bounded
  retry — and the counter for it is *already written and never called*:
  `autobot_shared/monitoring/metrics/websocket.py:101-105` declares an
  `autobot_websocket_messages_dropped_total` Counter with a `record_message_dropped()` method
  (`:235-237`) whose only other repo-wide match is a docstring baseline file. Wire that instead.
- **Effort:** trivial (wiring the counter).

### What We Already Do Better

1. **The capability lattice is mathematically stronger.** `security/authority.py:7-8` states the
   invariant — *"effective permission at any hop is the meet of every hop from the originator
   through it. Relaying can never widen it."* `meet` (`:56-63`) is union-of-restrictions,
   intersection-of-grants, composed across an arbitrary delegation chain. The source narrows a
   member's request against a **single** controller ceiling
   (`runtime/capabilities.py resolve_effective_capabilities_from_member_request`) with no
   composition across hops, and its own prompt contract states capabilities "never inherit from
   a parent" — a simpler model that cannot express our inherited-boundary case.
2. **Deny-by-default is enforced and quoted at every layer, and misidentification narrows.**
   `autobot_shared/auth/permissions.py:546-548` (unmapped role denied, fails closed);
   `mcp_tool_permissions.py:303-304` (an exact entry is the only way a tool resolves);
   `middleware/builtin/permission_enforcement.py:91-92` (`fail_closed = True`, `priority = 0`)
   with an undeclared tool raising outright at `:116-124`; and
   `orchestration/agent_registry.py:578-588`, where an unresolved agent id falls back to the
   broad `SENSITIVE_TOOLS` set, not an empty one — *"A misidentified agent is therefore more
   restricted than any real one, which is the correct direction."* Unbounded executor profiles
   are unreachable by alias (`agent_registry.py:512-517`).
3. **Our human-in-the-loop proves a human.** `api/user_management/human_decider.py:26-37`
   `require_interactive_human` raises 403 unless the approver is a person's interactive login,
   enforced on approve/reject/request-revision (`api/approval_gates.py:200,234,268`). The source
   has a "Human Request" capability but nothing establishing that the answerer is not another
   agent.
4. **Event-gap honesty is genuinely ahead.** `events/channel_stream.py:195-242 replay_since`
   never returns a partial history as if it were whole, with four distinct resync reasons
   (`replay_unavailable`, `durable_write_lost`, `replay_corrupt`, trimmed window), backed by a
   durable `_mark_broken` record of the lowest lost id. The source detects its own drops via a
   health counter but offers consumers **no** equivalent "your history has a hole" contract.
5. **Store authority is a declared artifact, not folklore.** `autobot_shared/store_authority.py`
   names the system of record and its rebuildable projections per concept — `llc_work` →
   Postgres with Redis/Chroma projections (`:106-121`), `agent_work_claims` → Redis as a
   deliberate TTL'd exception (`:244-255`), `chat_sessions` → disk (`:205-216`). The source's
   equivalent is implicit in its table design.
6. **Delegation, when enabled, is better governed.** `forbidden_work` enforced at the
   `_dispatch_tool_call` seam, authority met with the parent's
   (`chat_workflow/delegation.py:225-228` — *"delegating can never widen what the parent may
   do"*), a depth bound (`:71`, default 2) and a per-turn cap (`:73`, default 5). The source
   bounds wave width (1–8 children) but ships no per-member forbidden-tool manifest.

### Gaps & Opportunities

Prioritized by impact:

| # | Gap | Evidence | Impact |
|---|---|---|---|
| 1 | **The fan-in wait is memory-resident in all four fan-out sites.** A crash mid-fan-out strands the batch. | `agents/hierarchical_agent.py:392` (`asyncio.gather`), `orchestration/subagent_dispatcher.py:118` (`bounded_gather`), `execution_strategies/_collaborative.py:57-59` (`await future` loop), `_parallel.py:79-82` (`asyncio.wait`) | **Blocking** for enabling delegation |
| 2 | **Delegation is built, governed, tested and never turned on.** Eight-item checklist, no box ticked. | `chat_workflow/delegation.py:33-58`; `DELEGATION_ENABLED` default `False` at `:69` | High — sunk capability |
| 3 | **Two stranded-work recovery gaps.** Durable row survives; the registry to act on it does not. | `services/process_adapter_service.py:70,74-78`; `utils/long_running_operations/operation_manager.py:100,409-418` | High |
| 4 | **Only the disabled path reaches `SubagentDispatcher`.** | `execution_strategies/_parallel.py:68` gated on `SUBAGENT_REFLECTION_ENABLED`, default `false` at `autobot_shared/ssot_config.py:119-122` | Medium |
| 5 | **A dead delegation pair shadows the live one.** `HierarchicalAgent(` appears only in its own file and its test; `tools/delegate_tool.py` (`name = "delegate"`) is constructed nowhere in production, while `chat_workflow/tool_handler.py:2302 _handle_delegate_tool` is the real path. | grep-verified | Medium — consolidate, per the no-fork rule |
| 6 | **Ten-plus signalling mechanisms against a doctrine that says "one bus."** | `EVENT_STATE_DOCTRINE.md:14-17`; enumerated: `events/bus.py`, `event_manager.py`, `live_event_manager.py`, `events/channel_stream.py`, `events/stream_manager.py`, `autobot_shared/message_bus.py`, LLC publisher/router, ~11 ad-hoc Redis pub/sub sites, `services/gateway/message_queue.py`, Celery | Medium |
| 7 | **The dropped-message counter is dead code.** | `autobot_shared/monitoring/metrics/websocket.py:101-105,235-237`, no callers | Low — trivial fix |
| 8 | **No "next legal action" on a denial; no provenance on a capability decision.** | items 2 and 3 above | Low |
| 9 | **No expiry on DB-persisted approval gates.** The event-bus tool approval has `approval_timeout_seconds` (default 300); the `approval_gates` flow has no timeout found. | `api/approval_gates.py` | Low |

### Specific Code/Files Affected

| File | Change |
|---|---|
| `autobot-backend/initialization/lifespan.py` | Two new recovery calls beside the existing `_recover_agent_sessions` (`:2043`) / `_recover_index_queue` (`:2058`) |
| `autobot-backend/services/process_adapter_service.py` | Boot-time re-query of `process_runs` for `QUEUED`/`RUNNING`, idempotent re-enqueue, bounded page size |
| `autobot-backend/utils/long_running_operations/operation_manager.py` | Rebuild `self.operations` from the checkpoint store at init so `resume_operation` (`:409-418`) stops raising after a restart |
| `autobot-backend/chat_workflow/tool_dispatch_guards.py` | Carry `suggestion` (next legal action) and the deciding hop on the denial at `:63` |
| `autobot-backend/middleware/builtin/permission_enforcement.py` | Same, for `:124,136` |
| `autobot-backend/orchestration/{subagent_dispatcher,execution_strategies/*}.py` | Persist "waiting for N children" before the `gather`/`wait`, settle per child, re-derive on boot |
| `autobot-backend/agents/hierarchical_agent.py`, `autobot-backend/tools/delegate_tool.py` | Consolidate into the live `chat_workflow` delegation path — wire in, do not delete, per the no-deletion rule |
| `autobot_shared/monitoring/metrics/websocket.py` | Call `record_message_dropped()` from the real drop sites (`event_manager.py:134`, `live_event_manager.py:139`, `message_queue.py:66`) |

### Verdict

**Adopt the mechanism, not the dependency.** Three items are cheap and clearly ours to take: the
startup re-derivation pattern (which we already ship twice and are missing twice), the
next-legal-action denial (carrier already written), and the dropped-message counter (already
written, never called). The pinned-revision concept needs a product decision before it earns its
migration cost. The inline publish fallback is rejected outright — our own resync contract is
the better answer.

The real output of this comparison is not a feature list. It is that **AutoBot's delegation
capability is complete, governed and switched off, sitting on a fan-in wait that would not
survive a restart**. The reference work is worth studying precisely because it answers the
question our unchecked checklist is waiting on.

**Confidence:** high on all AutoBot claims — every one is cited to a line read in this session or
verified by grep. Moderate on the source's internals: read from its published sources, not run.

**Not verified:** whether definitions are edited mid-run in practice (decides item 4); the
context cost of the source's relaunch-per-continuation model, which it does not measure either.

---

## Issue coverage for the nine gaps

Searched open **and** closed issues per gap. Note: multi-term `gh issue list --search` queries
AND every term and returned eight false negatives on the first pass — the counts below are from
short-query re-runs, validated against a known-good control search.

| # | Gap | Existing issue | Status |
|---|---|---|---|
| 1 | Fan-in wait memory-resident in all 4 fan-out sites | **none** | Searched `asyncio.gather`, `in-flight resume`, `durable wait`, `parent wait children` — no issue covers orchestration fan-out durability |
| 2 | Delegation built, governed, never enabled | #11266 **CLOSED/COMPLETED** | Closed 2026-07-08 on PR #11276, *"harden governed delegation **for** enablement"*. Flag still `default=False` (`delegation.py:69`); all eight checklist boxes unticked. Parent epic #11260 also closed. **Nothing open tracks the enablement itself.** |
| 3 | Two stranded-work recovery gaps | #14863 **OPEN** (understates class) | Names three in-memory job stores and the four properties each needs; `ProcessAdapterService` and `LongRunningOperationManager` are two more instances — the class is **5, not 3**. #1751 (CLOSED) already proposed consolidating the former with the latter's framework. Adjacent open: #17023, #17017, #17010. #3231 (CLOSED) covered Redis-TTL expiry before resumption. |
| 4 | `SubagentDispatcher` reachable only behind a default-off flag | **none direct** | #10603 (OPEN) is the umbrella for built-but-disconnected machinery — natural host |
| 5 | Dead `HierarchicalAgent` + `tools/delegate_tool.py` pair | #11207 **CLOSED/COMPLETED** | Closed with *"the `delegate` tool is now wired to … `chat_workflow/delegation.py`"*. The replacement landed; the superseded pair was never wired in or consolidated and is still present |
| 6 | 10+ signalling mechanisms vs a "one bus" doctrine | partial | #14822 (OPEN, retire duplicate event socket), #14815 (OPEN umbrella), #17020 (OPEN). No issue states the fleet-wide count |
| 7 | `record_message_dropped()` declared, never called | **none** | Searched `messages_dropped`, `dropped message metric`, `websocket metrics unused` |
| 8 | No next-legal-action, no provenance on a denial | **none** | #13588 (CLOSED) fixed the adjacent fail-open; #655 (CLOSED) created `RepairableException`. Nothing on wiring guidance into denials |
| 9 | No expiry on DB-persisted approval gates | **none direct** | #17043 (OPEN) consolidates the general + LLC approval systems — natural host |

**Summary at audit time:** 4 gaps unfiled (1, 7, 8, and 4 in part), 2 filed but scoped too
narrowly (3, 6), 2 closed as completed with the work outstanding (2, 5), 1 with an open host to
extend (9).

## Filed 2026-09-22 — all findings now tracked

**Umbrella #17275** — delegation's fan-in wait does not survive a restart; durability before
enablement. Six native sub-issues:

| Issue | Gap | Subject |
|---|---|---|
| #17281 | 1 | fan-in wait memory-resident at all four fan-out sites (blocks #17285) |
| #17282 | 4 | `SubagentDispatcher` reachable only behind a default-off flag |
| #17283 | 3a | `ProcessAdapterService` has no startup recovery |
| #17284 | 3b | `LongRunningOperationManager.resume_operation` always fails after a restart |
| #17285 | 2 | governed delegation never enabled — #11266 closed on a hardening PR |
| #17286 | 5 | superseded `HierarchicalAgent`/`DelegateTool` pair still present |

**Standalones:**

| Issue | Gap | Subject |
|---|---|---|
| #17287 | 7 | dropped-message counter declared, never incremented; six log-only drop sites |
| #17288 | 8 | denial names no legal alternative and no deciding hop |
| #17289 | 9 | DB-persisted approval gates have no expiry |
| #17290 | E1 | `worker_node` subscribes to `orchestrator_tasks`; nothing publishes to it |
| #17291 | E2 | gateway `MessageQueue` is a sole carrier, drops on full |
| #17292 | E3 | `code_exec/broker` swallows the durable-write exception |
| #17293 | E5 | workflow execution state carries a 24h TTL; #3231 fixed a different key |
| #17294 | 6 | ten-plus signalling mechanisms against a one-bus doctrine |
| #17295 | E4 | LLC startup recovery writes run status unconditionally (latent) |

Cross-linked as comments on #14863 (class is 5 stores, not 3), #11266, #11207, #3231, #17043
and #10603. `#17285` carries a native `blocked_by` edge on `#17281`.

Nothing from this review is unfiled.
