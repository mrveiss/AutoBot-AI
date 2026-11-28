---
tags:
  - research
---

# Research: agent self-model graph and evidence-gated lessons

Status: Phase 1, Phase 2 and the self-knowledge audit (Phase 2b) complete. AutoBot facts verified on `origin/main` at `0e0bd25bf1` (2026-11-26). Issues filed; see Linked issues.

## Summary

The reference work is a self-hosted, LLM-driven multi-agent system written in Go. A planner decomposes a goal into intents, workers claim and run them with real tools, and results are written back into two linked graphs stored in PostgreSQL. Its transferable value is in patterns, not code: a shared entity graph with code-computed identity, a per-task reasoning graph joined to it by anchors, a coverage ledger that records negative results, evidence-gated lessons with a shadow mode, code-owned prompt tails, hierarchical budgets, and a process-wide provider circuit breaker.

Compared against AutoBot, three findings matter most:

1. **Lessons carry no evidence and cannot be retracted.** `analyzer_service.py` admits a lesson on a score delta only. This is the highest-value, most contained adoption.
2. **The memory-graph dedup path exists but nothing enqueues it,** and it dedups on name only.
3. **AutoBot cannot answer questions about itself.** The self-knowledge audit found about 15 disconnected stores with no cross-references and no declared-versus-probed status. Several are unwired or always fail. Questions such as "which node runs this tool" or "which service serves this route" have no answer.

The per-task exploration graph and cold-digest compaction are rejected or deferred: AutoBot's `AgentLoop` has no live constructor, and a graph with no live producer is dead code.

## Techniques in the reference work

### Dual graph

- **Entity graph.** A company-scoped shared graph of typed entities (root domain, IP, subdomain, app, service, endpoint) with containment edges. Identity is a dedup key computed by code. Agents submit raw observations only and never choose identifiers.
- **Exploration graph.** A per-task graph of goal, intent, fact, finding, hint and digest nodes. Typed edges (`spawns`, `derived_from`, `yields`, `proves`, `covers`) have a primary key on (exploration, source, relation, destination) and forbid self-loops. Each node kind has its own state check.
- **Anchors.** A join table `(node_id, asset_id)` links the two graphs. Entity-level coverage ("which entities has this work touched") falls out of the join.

### Cold-digest compaction

A pure function judges planner-round nodes hot or cold (window of 6 rounds, 2 kept). Connected cold nodes are grouped into one `digest` node with `covers` edges. The digest layer is excluded from causal reachability, so compaction never changes what proves what.

### Coverage ledger with negative outcomes

One row per (task, surface, risk area), unique. Outcomes are `reported`, `no_issue_found`, `ruled_out`, `not_applicable` and `needs_follow_up`, with a history table. It records what was checked and found nothing, which prevents re-asking the same question.

### Evidence-gated lessons with shadow mode

- A lesson needs a cue, an action and at least one evidence row.
- Evidence is keyed `(lesson, source_kind, source_id)`, so a re-run cannot inflate support.
- A lesson is withdrawn when the outcome that supported it reverses. A support count is kept.
- Three modes: off, shadow (record and measure, never inject), inject. Injected lessons are rendered as prior outcomes, not instructions.

### Evidence-gated findings

A finding is `verified` only with a bound proof and verbatim evidence quotes (compressed bodies are decoded before the quote check). A separate retester agent re-runs findings and reports still reproducible, fixed or cannot confirm.

### Code-owned prompt tails

Prompt-injection rules are appended in code after the database-editable prompt body, so an operator edit or a stale row cannot drop them. A further rule forbids data from adding goals or scope, or from being relayed to workers as instructions. Tool output is also framed with nonce-tagged boundaries.

### Hierarchical budgets

Budgets nest task, intent, planner round. A child budget is the minimum of its own limit and the parent's remaining amount above a wrap-up reserve. Near the limit a forced wrap-up round runs. Spend is restored from the usage ledger after a restart.

### Process-wide provider circuit breaker

An ordered failover chain of provider profiles shares one breaker registry per process. Deterministic failures (no credit, bad key) trip it at once. Transient 429 and 5xx errors trip it after N occurrences. Backoff steps are 1, 5 and 30 minutes.

### Other patterns

- Event-driven planner loop: a graph change debounces into a planner wake, dispatches intents to a frontier queue, and workers claim from it.
- Tool retrieval that can only remove tools from an already-bound list, never add them, with a fixed core set always kept.
- A guard hook that records who decided each tool call (human, rule, model, system).
- A written contract for any future self-improvement loop: live tasks propose, held-out benchmarks adopt, owner approves each adoption, safety gates are immutable.

## AutoBot comparison

Verified on `main` at `0e0bd25bf1`.

- **Shared entity graph.** `autobot_memory_graph/core.py` defines `ENTITY_TYPES` and relations including `contains`. `entity_upsert.py` `get_or_create` dedups atomically on sha256 of the casefolded name: name-only and global. Its only caller is `tasks/memory_tasks.py:84` (`memory.update_graph`), and grep finds no enqueue site beyond the route in `celery_app.py:123`. Other writers use the non-deduping `create_entity`.
- **No per-task exploration graph.** No non-test hits for `derived_from`, `spawns`, `yields`, `proves` or `cold_digest`. `agent_loop/belief_state.py` is a flat assertion dict behind a flag that is off, and `AgentLoop` has no live constructor.
- **No anchors** from work to entities. LLC work items use their own Chroma collection.
- **Provenance.** `knowledge/facts.py` `_PROVENANCE_DEFAULTS` is live at document level. `agent_loop` `ToolExecutionRef` is not live.
- **Lessons.** `services/knowledge/analyzer_service.py` gates on a score delta (`_MIN_SCORE_DELTA=0.1`). Lessons cite a `run_id`, have no evidence rows and no retraction.
- **Queue.** `llc/services/work_item_queue.py` `checkout_next` uses a Redis fence plus `SELECT FOR UPDATE`. Wakes in `llc/scheduler/event_wake.py` fire on comment, assign, mention and approval, not on graph change.

### What to adopt

| # | Pattern | AutoBot target | Visible benefit | Hidden cost | Verdict | Effort |
|---|---|---|---|---|---|---|
| 1 | Evidence-gated lessons: cue, action, at least one evidence row; evidence keyed so re-runs cannot inflate support; withdraw on reversed outcome; off/shadow/inject modes; rendered as prior outcomes | `analyzer_service.py` Lesson, `rag_derived_context.py` | Lessons become traceable and self-correcting; shadow mode measures before injecting | One evidence table plus extraction hooks on outcome changes | **Adopt** | Moderate |
| 2 | Code-computed composite dedup key (type, canonical name, parent or scope); agents submit raw observations only | `entity_upsert.py` `name_index_key` | Stops cross-type collisions ("Redis" as DOCUMENT versus CODE) | Key migration of the existing `memory:entity_name:*` index | **Adopt** (after 3) | Moderate |
| 3 | Wire the dedup upsert path that exists but is never enqueued | `tasks/memory_tasks.py` `memory.update_graph` caller | Dedup actually happens | None new: finishing unwired work | **Adopt** (debris, not a new feature) | Trivial to moderate |
| 4 | Anchors: work item or run joined to memory-graph entity | LLC work items plus `autobot_memory_graph` | Entity-level coverage; backlinks from knowledge to work | Cross-store join (Postgres LLC to Redis graph) needs a declared system of record (`store_authority`) | **Adopt with conditions**: only with a declared system of record | Moderate |
| 5 | Coverage ledger with negative outcomes and history | Research orchestrator sub-questions; `finding_proposal_service` | Records what was checked and found nothing; prevents re-asking | Another table; needs a consumer that reads it | **Adopt with conditions**: pick one consumer first | Moderate |
| 6 | Per-task exploration graph (goal, intent, fact, finding, typed edges, provenance) | `agent_loop` `BeliefState`, `ToolExecutionRef` | Auditable reasoning chain | `AgentLoop` is not live; a graph with no live producer is dead code | **Rejected on hidden cost** until a live loop exists | Significant |
| 7 | Cold-digest compaction (pure algorithm; derived layer excluded from reachability) | Would apply to 6 | Bounded planner context | Only meaningful once 6 exists | **Deferred** with 6 | Moderate |
| 8 | Quiet-mode wake suppression: unchanged open-goal fingerprint skips a planner round | `llc/scheduler/event_wake.py` | Fewer redundant LLM wakes | Small; existing dedupe in `event_wake` not audited | **Unaudited**: check before proposing | Trivial |

### What AutoBot already does better

- Semantic KB: ChromaDB retrieval, chunk provenance (`knowledge/chunk_provenance.py`), RAPTOR-style summarizer. The reference work has no vector KB.
- Temporal validity on relations (`autobot_memory_graph/relations.py` `invalidate_relation`, `valid_to`).
- Deterministic code-graph ids with containment (`autobot_shared/code_graph/identity.py` `compute_node_id`).
- Claim queue with fencing (`work_item_queue.checkout_next`) equal to or stronger than the reference claim step.
- Cross-task trajectory retrieval with a reward filter (`memory/trajectory_store.py` `find_similar_trajectories`).

### Gaps by impact

1. Lessons lack evidence and retraction (row 1).
2. Memory-graph dedup is unwired and name-only (rows 3, 2).
3. No link between work and knowledge entities (row 4).
4. No record of negative results (row 5).

### Files affected

- `autobot-backend/services/knowledge/analyzer_service.py`, `rag_derived_context.py` (row 1)
- `autobot-backend/autobot_memory_graph/entity_upsert.py`, `entities.py`; `tasks/memory_tasks.py` (rows 2, 3)
- `autobot-backend/llc/services/work_item_queue.py` plus a new anchor projection (row 4)
- `autobot-backend/services/research/orchestrator.py` (row 5)

### Patterns noted for later

Code-owned prompt tails, hierarchical budgets and a process-wide provider circuit breaker were identified as transferable. They were not audited against AutoBot in this pass and are not part of the filed issues.

## AutoBot self-knowledge audit

Scope: the owner's focus that AutoBot should know everything about its environment and capabilities. Verified on `main` at `0e0bd25bf1`. There are about 15 disconnected stores, no cross-references between them, and no declared-versus-probed status anywhere.

| Verdict | Items |
|---|---|
| Does | `SystemKnowledgeManager` change detection; `system_knowledge_import` (lease, fire-and-forget); runtime copies keep operator edits; `system_knowledge_paths`; `self_capabilities` live OpenAPI crawl; SLM `node_capability_profiles` (heartbeat, NULL means not reported); `AgentCapabilityIndexer` (LLC only); `device_capabilities` (an auth concept) |
| Partial | `system_context`: `machine_id` comes from a hardcoded hostname map (`:72-79`). `LLMSelfAwareness`: endpoints are collected (`:147`) but never rendered (`:475-505`). `ServiceRegistry`: static URLs, health probed only from the CLI, starts UNKNOWN |
| Does not | `ToolRegistry` system tools: `worker_node` is never set (`lazy_singleton(ToolRegistry)` `:811`), so calls return "Worker node not available" (`:108`) |
| Unwired | `MachineAwareSystemKnowledgeManager` (`enable_machine_aware=False`, `system_knowledge_import.py:123`); `ManPageKnowledgeIntegrator`; `CapabilityRegistry` (no consumer); `capability_audit` (tests only); `system_context.generate_unique_key` |
| Defined twice or more | Services (2, plus the hostname map); routes (3); agents (4 plus the LLC index); tools (5); man-page writers (4); "capability" names 5 unrelated concepts |
| Unanswerable | Tool to node; route to service; model to node fit; commands per host; fleet inventory from chat |

Pattern applied: one self-model graph (node, service, route, tool, model, command) with code-computed identity keys. Existing probes submit observations. Each entity carries `declared`, `probed-ok` or `probed-failed` plus `last_seen`. One chat query tool reads it. One declared system of record, via `store_authority`. It replaces the duplicates; it is not an additional store.

Related existing issues: #19347, #13511, #12542, #17807, #17808, #20970.

## Owner decisions

Recorded 2026-11-26.

- **System of record.** The self-model's system of record is SLM Postgres. Any other copy is a rebuildable projection.
- **Access model.** Self-awareness is an on-demand tool the chat agent calls, not a block injected into every turn.

## Linked issues

- #22280 umbrella(self-model): AutoBot knows what it runs, where, and what is verified working
- #22267 bug(tools): query_system_information and list_system_services always fail — the ToolRegistry singleton never gets a worker node
- #22268 bug(self-awareness): the route list is collected but never rendered into the self-awareness block
- #22269 bug(system-context): machine_id comes from a hardcoded hostname map, and generate_unique_key has no caller
- #22270 wire(integrations): CapabilityRegistry populates providers but nothing consumes it
- #22271 wire(orchestration): capability_audit is reachable only from tests
- #22272 canonical(knowledge): one man-page ingestion path with per-host facts — machine-aware path unwired, four writers
- #22273 canonical(services): services are defined twice (backend and SLM), and health is probed only from the CLI
- #22274 canonical(api): three route registries, and none records which service serves a route
- #22275 canonical(agents): agent identity, health and presence live in five registries
- #22276 canonical(tools): tool names come from five sources, and no tool records where it runs
- #22277 feat(self-model): one connected self-model — node, service, route, tool, model, command — with declared or probed status
- #22278 feat(chat): a read-only chat tool that queries the self-model
- #22279 feat(knowledge): evidence-gated lessons — admission, support, withdrawal and a shadow mode
