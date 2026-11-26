# Local-first agent platform: preemptive model scheduling and curated knowledge

Research note on a reference work: an open-source, self-hostable personal-agent platform that runs agents on the user's own computer against local models.

## Linked issues

- #21913 Research: preemptive model scheduling and curated knowledge — adoption tree
- #21914 bug(llm): chat_completion latency clock starts before the concurrency slot and rate-limit token are acquired
- #21917 feat(llm): priority admission and adaptive concurrency for model calls
- #21915 feat(kb): search accepts an agent-supplied query list fused by rank, and returns curated and verbatim results as two lists
- #21918 feat(memory): graph observations get stable IDs, per-item sources and edit-by-ID
- #21916 feat(slm-agent): persist events before sending, and verify the package checksum on the node after sync
- #21919 feat(agents): wire background sub-agents with a report-only channel
- #21920 security(agent-seam): desktop control tools and the out-of-process delegation engine are outside pre-action verification
- #16768 outbound anti-spam guard (existing; delta for daily cap and defer-until-idle added as a comment)

## Source Analysis: the reference work

### What It Is
A server plus per-computer daemon platform. The server holds rooms, permissions, collaborative documents, memory and a model-maintained wiki; a daemon on each user computer runs coding-agent runtimes against local or subscription models and acts on the desktop and browser. Young (days old) but large and heavily specified.

### Architecture & Key Patterns
- Outbound-only daemon: one WebSocket dialled out, no listening ports on the client; local helpers bind loopback or an owner-only socket.
- Daemon keeps per-context ordered command queues and a SQLite event ledger: every event persisted before send, replayed after reconnect; synced files checked by SHA-256.
- One workspace per agent×context with writable scratch, read-only memory/wiki mounts.
- Agents call the server through a CLI; the server re-checks every call against current permissions.
- Rule-based checks then an LLM review gate desktop/browser/shell actions (not uniform across runtimes).
- OpenAPI as contract source, generated server and client types.

### Notable Implementation Details
1. **Adaptive priority-preemptive model scheduler** — per-endpoint queue; concurrency adapts (additive increase while latency per 1k prompt tokens holds, decrease when slower, halve on rate-limit/overload/timeout with timed back-off); soft limit reserves the last slot for interactive work; seven priority classes from tool approval down to background memory refresh; higher priority preempts — background calls are stopped and re-queued without counting as failures, running runs yield at a resumable session point and resume with the same ID; timeouts count running time only.
2. **Meta / background-copy delegation** — one front agent per room talks to the user; background copies never message the user, put questions in their report; explicit task state machine where "canceled" means paused and resumable.
3. **Model-maintained wiki with app-enforced edit discipline** — typed entity pages; section-level proposals; summaries kept or rewritten with a stated reason; list entries edited one at a time by app-assigned IDs; facts cite their source version and rewrites must preserve or justify dropping sources; the change log is written by the application, never the model; hard size caps.
4. **Keyword-only dual-list retrieval** — full-text search over multiple agent-supplied rewordings, reciprocal rank fusion, time-aware boosting that never filters, separate ranked lists for curated overviews vs originals; mutable facts re-checked against live sources before being stated as current.
5. **Proactive assistant with nightly clue→rule learning** — polls mail/calendar/chat, quiet hours and a daily cap, delivery waits for chat silence; nightly a model turns explicit user feedback on unsolicited messages into clues, and repeated same-kind clues into bounded, human-readable rules; an explicit list of signals never to learn from.
6. **Hardware-fit model selection** that counts a model installed only after it answers a real question.

### Strengths
- Operational semantics specified as tables (priorities, states, caps), not implied.
- Failure-neutral preemption.
- Anti-drift discipline for LLM-maintained knowledge.
- Interpretable, bounded preference learning.

### Weaknesses / Limitations
- Very large multi-stack surface for its age; high churn risk.
- Action review not uniform across agent runtimes.
- No semantic retrieval — recall depends on the agent's rewordings.
- Restrictive licence: ideas portable, code not.
- Performance and quality claims self-reported with lab caveats.

### Visible vs Hidden Metrics
- **Visible:** large MoE models on consumer GPUs, throughput tables, frontier-equivalence claims — self-reported.
- **Hidden:** five stacks to operate; one-GPU throughput forces the preemption machinery; long first-token latency on the flagship config; natural-language rule prompts that must stay in sync with code.
- **Weighing:** as a product, hidden costs and licence dominate; as a pattern source the scheduler, wiki edit discipline and clue→rule learning are stack-independent.

## AutoBot Comparison: the reference work → AutoBot

Audit method: read-only sweeps of `main` at 18fe780f29, quoted file:line below. Paths relative to repo root, backend under `autobot-backend/`.

### What We Can Adopt

| # | Pattern | AutoBot today (audit) | Delta to adopt | Visible benefit | Hidden cost | Verdict | Effort |
|---|---|---|---|---|---|---|---|
| A | Priority LLM admission + adaptive concurrency | PARTIAL — fixed `asyncio.Semaphore(max_concurrent)` per provider (`llm_shared/base_provider.py:133-136`), covers `chat_completion` only (#16538 comment :131); `LLMRequest` (`llm_shared/models.py:153`) has no priority; 429 handling is retry back-off (`optimization/rate_limiter.py:56-66`), never a concurrency change. Greps `AIMD`, `PriorityQueue`, `LLMPriority`, `interactive.*slot`: empty | Priority field on `LLMRequest`; per-endpoint priority queue replacing the bare semaphore; soft limit reserving last slot for interactive chat; AIMD (halve on 429/503/timeout, +1 while latency per 1k prompt tokens holds); background calls cancellable + re-queued without counting a retry | Chat stays responsive while KB/memory/consolidation jobs run on one local Ollama | Scheduler state per endpoint; cancellation semantics for streams; tuning | **adopt-with-conditions**: priority + reserved slot + AIMD now; preemption only for *background* calls (cancel+requeue), no mid-run yield of agent runs | significant |
| A′ | Timeout/latency measured from slot acquisition | **Defect**: `start = time.monotonic()` taken *before* the semaphore and rate-limiter acquire in `chat_completion._attempt()` (`base_provider.py`) → recorded latency and any latency-driven decision includes queue wait | Move the clock inside the acquired slot; record queue wait separately | Correct latency metrics; prerequisite for AIMD | none | **adopt** (defect fix) | trivial |
| B | Background sub-agents with report-only channel | PARTIAL — delegation off by default (`chat_workflow/delegation.py:73-77`), runs inline blocking the turn (:287), synthetic session id, "No DB/session is created" (:172); `SubagentSpawner`/`SubagentManager` (`services/agents/subagent_spawner.py:39`, `subagent_manager.py:33`) exported but **no non-test callers** (unwired); approval expiry exists (`services/approval_gate_service.py:398`, `approval_expiry_scheduler.py:30`) | Wire the spawner: background execution, own session/workspace, output into a task folder the lead reads; sub-agent cannot message the user (questions go into its report); task state machine where cancel = pause/resumable; `WAITING_FOR_APPROVAL` state | Long work no longer blocks chat | Session/workspace lifecycle, more concurrent LLM load (depends on A) | **adopt-with-conditions** (after A) | significant |
| D | App-enforced edit discipline for model-maintained knowledge | ABSENT — memory graph `add_observations` appends with no IDs (`autobot_memory_graph/entities.py:359,379`); no per-item source; `consolidate_facts` is delete-only (`knowledge/facts.py:1496`); greps `section_id`, `rewrite_reason`, `source_message_id`, `MAX_OBSERVATIONS`: empty. Prior research verdict "copy the invariants" (memory-governance doc; #18821 mutation audit, #18079, #18078) | App-assigned stable observation IDs; updates by ID (unmentioned items untouched); per-item source citation; rewrite must keep or justify dropped sources; change log written by the app; per-entity caps with merge-oldest | Memory stops drifting/losing provenance on LLM rewrites | Migration of existing observations; stricter write API | **adopt** (invariants only, fold into #18821 family) | moderate |
| E | Agent-supplied rewordings fused by RRF; dual result lists | PARTIAL — RRF exists for semantic+BM25 (`knowledge/search_components/hybrid_search.py:47`); multi-query path keeps first hit per id, **no rank fusion** (`knowledge/search.py:731` `_execute_multi_query_search`); expansion is a static synonym table (`search_quality.py:136`); verbatim store separate (`memory/verbatim_store.py`) but never returned as its own ranked list | Search tool schema accepts `queries[]` (≤6, incl. translations — relevant for Latvian); fuse per-query lists with RRF; return curated vs verbatim as two lists; prompt rule "search originals before claiming never recorded"; time named in query boosts, never filters | Better recall for paraphrase/cross-language; fewer false "no record" answers | Extra queries per search (latency) | **adopt** | moderate |
| F | Proactive assistant with nightly clue→rule learning | ABSENT — heartbeat scheduler is cron wake (`llc/scheduler/heartbeat_scheduler.py`); `NotificationService` (`services/notification_service.py:265`) has no quiet hours/cap/deferral; greps `quiet.?hours`, `daily_cap`, `never_learn`, `wait_for_idle`: empty. Outbound guard (quiet hours, rate cap, dedup) already filed as #16768 under #16838 | (1) quiet hours + daily cap + defer-until-chat-idle → into #16768; (2) later: bounded, human-readable clue→rule distiller with explicit never-learn list | Fewer, better-timed unsolicited messages; interpretable personalisation | Needs a proactive pipeline that doesn't exist yet; long prompt spec that must stay in sync with code | (1) **adopt** via #16768; (2) **adopt-with-conditions** — only once a proactive pipeline exists | (1) moderate, (2) significant |
| G | Write-ahead event ledger on edge agent | PARTIAL — SLM agent buffers to SQLite only *after* a failed send (`autobot-slm-backend/slm/agent/agent.py:270`), replays via `sync_buffered_events` (:295); `get_package_checksum` SHA-256 (`code_distributor.py:117`) has no callers | Persist before send, delete on ack; verify package checksum on node after sync | No lost heartbeat/event on crash mid-send | Small disk I/O | **adopt** (write-ahead + wire checksum) | trivial |
| G′ | Single dial-out WebSocket replacing push | HTTP POST heartbeat + Ansible push | — | No inbound ports | Rewrites the builtin-updater path (owner rule: updates go only through it); SLM is an admin panel for AutoBot's own nodes | **rejected-by-hidden-metrics** | — |

### What We Already Do Better
- **Action review (C):** AutoBot's `_seam_guard_message` chain (`chat_workflow/tool_handler.py:3160-3171`) runs rule checks → pre-action verifier with per-class thresholds and a **panel quorum** (`autobot_shared/pre_action_verifier_guard.py:81-103`) → approval → repetition guard on every routed tool. The reference work: rules + single LLM review, and one runtime skips review entirely.
- **Retrieval core (E):** hybrid semantic + BM25 with RRF (`hybrid_search.py:47`) vs the reference work's keyword-only search with no embeddings.
- **Approval expiry** already exists (`approval_expiry_scheduler.py:30`, 60 s sweep).
- **Provider resilience:** circuit breaker (`base_provider.py`, GH#11488) and pre-emptive model fallback on rate-window headroom (`model_fallback_coordinator.py:58,147`).

### Gaps & Opportunities (by impact)
1. **A′ latency clock defect** — trivial, unblocks A.
2. **A priority admission** — biggest user-visible win on single-GPU nodes.
3. **E multi-query RRF + dual lists** — the fused-rank fix in `_execute_multi_query_search` is small.
4. **D memory edit invariants** — extends #18821.
5. **G write-ahead ledger + checksum wiring.**
6. **B background sub-agents** — wire the unwired spawner (after A).
7. **C coverage gaps** — desktop/VNC tools absent from `tool_catalogue.py` (grep `vnc|mouse|keyboard|desktop`: empty) so never verifier-checked; `claude_code` delegation engine runs only under `--disallowedTools` with no LLM review (`delegation.py:15-21`).
8. **F proactive** — quiet-hours part via #16768; learning later.

### Specific Code/Files Affected
- `autobot-backend/llm_shared/base_provider.py` — move latency clock inside slot; replace semaphore with priority admission.
- `autobot-backend/llm_shared/models.py` — `LLMRequest.priority`.
- `autobot-backend/llm_shared/optimization/rate_limiter.py` — feed 429/503 into concurrency halving.
- `autobot-backend/chat_workflow/delegation.py`, `services/agents/subagent_spawner.py`, `subagent_manager.py` — background execution, report-only channel.
- `autobot_shared/status_enums.py` — `WAITING_FOR_APPROVAL`.
- `autobot-backend/autobot_memory_graph/entities.py` — observation IDs, per-item source, app change log.
- `autobot-backend/knowledge/search.py` (`_execute_multi_query_search`), search tool schema — `queries[]` + RRF, dual lists.
- `autobot-backend/services/notification_service.py` — quiet hours/cap/defer (#16768).
- `autobot-slm-backend/slm/agent/agent.py`, `event_buffer.py`, `code_distributor.py` — write-ahead, checksum verify.
- `autobot_shared/tool_catalogue.py`, `api/vnc_mcp.py` — catalogue desktop tools as sensitive.

**Not examined:** frontend, autobot-browser-worker internals, `email-reading-capability-audit.md`, `managed-integration-platform-agent-tools.md`.
