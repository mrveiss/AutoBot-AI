# Research: layered agent memory + symbolic context offload

**Date:** 2026-08-08
**Source:** an external, cloud-vendor-backed open-source "team memory hub for AI agents"
(TypeScript monorepo, MIT-licensed core, widely starred, a few months old and still on a
pre-1.0 development branch). Repo name, vendor, and locating metadata are withheld per the
no-external-names rule for committed docs; the URL was supplied in-session. Exact star/fork
counts, creation dates and branch names are omitted deliberately — together they identify the
repository as surely as its name does.
**Method:** read the root README, three module READMEs (`MemoryCore`, `MemoryKnowledge`,
`MemoryProxy`), the top-level and `src/` directory trees, the default gateway config, and the
context-offload injector source. Vendor, product and repository names are withheld per the
no-external-names rule. Module and symbol names below are the source's own generic identifiers,
kept only where the mechanism is unintelligible without a label; none of them names the vendor.
**Status:** complete — source analysis and AutoBot comparison.
**Filed as:** umbrella **#13685**, children **#13686-#13692**, plus **#13694** (token estimator)
and **#13695** (idle-flush distillation trigger) from adopt-items 4 and 5.
Wave 1 #13686 (L2 disconnected) · #13687 (L4 disconnected) · #13688 (memory plane untenanted).
Wave 2 #13689 (A/B + flag decision) · #13690 (`compat.py`) · #13691 (budget guard, which depends
on #13640). Wave 3 is #13692 (tool-output offload). Blocker under the tuning items: **#13251**.

---

## Source Analysis

### What It Is

A self-hostable **team-level memory hub** that sits beside an agent runtime rather than inside it.
It turns three raw inputs — conversations, documents, and git repositories — into four governed,
shareable "memory assets": layered **Chat Memory**, versioned **Skills**, an **LLM-Wiki**, and a
**Code-Graph**. The selling proposition is organisational, not just technical: memory is an asset
with an owner, a visibility scope (private / team / restricted), a role model (system admin / team
admin / member), and an explicit **binding** of assets to agents ("loadout"). Maturity is high on
adoption signals but the repo is young and its default branch is a feature branch, not `main` —
an active, fast-moving codebase, not a settled one. Licence is `NOASSERTION` at repo level with
MIT declared inside one module, which is a diligence flag for anything vendored.

### Architecture & Key Patterns

Four deployable services in one monorepo, each independently Dockerised:

| Service | Port | Role |
| --- | --- | --- |
| `MemoryCore` | 8420 | L0–L3 memory store, Skill registry, asset/ACL metadata, HTTP gateway |
| `MemoryKnowledge` | 8421 | Wiki ingestion + Code-Graph indexing engines (a TS web framework + ORM over SQLite FTS5) |
| `MemoryPanel` | 8123 | Control plane: teams, curation, LLM binding, status callbacks |
| `MemoryProxy` | — | Adapter layer onto third-party agent frameworks |

Design patterns that carry the weight:

- **Sidecar, not library.** The memory pipeline runs as its own process; the agent gets a thin
  client adapter. The README is explicit that the plugin "does not run a second memory pipeline
  inside the agent process." One pipeline, many agents.
- **Strict metadata/content split.** `MemoryCore` stores *metadata about* knowledge (id, type,
  status, service location); `MemoryKnowledge` owns parsing, indexing, and content retrieval. The
  registry never grows into a content store.
- **Versioned API planes.** `/capture`+`/recall` (compat) → `/v2/*` (stable) → `/v3/*`
  (recommended). The v3 plane makes `team_id` + `agent_id` + `user_id` **mandatory** on every
  memory call — tenancy is a required argument, not an ambient default.
- **File-and-SQLite substrate.** SQLite (+ optional `sqlite-vec`) plus plain files under a
  dot-directory in `$HOME`. No external service required beyond a chat-completions-compatible
  LLM endpoint.
- **Custom HTTP, not MCP, for the hot path.** MCP exists only as a stdio shim in
  `MemoryKnowledge/src/mcp/` that forwards to the local HTTP API.

### Notable Implementation Details

**1. The L0→L3 semantic pyramid, with a scheduler.** Raw turns (L0) distil into atomic facts (L1),
which group into scenario blocks (L2), which synthesise into a persona (L3). What makes it more
than a diagram is that the cadence is a first-class, tunable pipeline
(gateway config → `memory.pipeline`):

```yaml
pipeline:
  everyNConversations: 5      # L1 extraction cadence
  l1IdleTimeoutSeconds: 600   # flush on idle, not only on count
  l2DelayAfterL1Seconds: 90   # debounce L2 behind L1
  l2MinIntervalSeconds: 900   # floor + ceiling on L2 rebuild
  l2MaxIntervalSeconds: 3600
persona:
  triggerEveryN: 50           # L3 regeneration
  maxScenes: 15
```

Backed by `src/services/`: a `timer-scanner`, a `pipeline-worker`, and a `worker-permit-pool`.
Distillation is a *scheduled background job with concurrency limits*, not something done inline on
the request path — the thing most home-grown memory layers get wrong.

**2. Symbolic short-term memory as an injected Mermaid canvas.** The most original idea, in
`src/offload/`. Instead of carrying verbose tool output in context, the running task's state
machine is maintained as a compact Mermaid diagram ("MMD"). `mmd-injector.ts` keeps **exactly one**
marked message in the message array (marker property `_mmdContextMessage`), locating and replacing
it in place rather than appending. Full tool output is written to `refs/*.md` on disk; context
holds only `node_id` anchors the agent can re-read on demand. Details worth stealing regardless of
the rest:

- The injector is budget-aware — `mmdMaxTokenRatio` bounds the canvas as a fraction of the context
  window, with a dedicated `l3-token-counter`.
- A readiness gate (`waitForL15` / `l15Settled`) **skips injection entirely** rather than injecting
  a half-built canvas, and preserves the previously injected one.
- Compression must skip the marked message — the canvas is explicitly exempt from the compactor,
  so the thing that survives context pressure is the state summary.
- History canvases are injected *only* by aggressive compression, as a replacement for messages
  that were deleted. Compression and memory injection are the same subsystem, coordinated.

**3. Hybrid retrieval that degrades instead of failing.** BM25 (a CJK-aware tokenizer for Chinese, a standard one for English) fused with embeddings via RRF. Crucially `embedding.provider: "none"` is the
**default** — vector search is opt-in, and the system is fully functional on BM25 alone. Recall is
bounded by `maxResults: 5`, `scoreThreshold: 0.3`, `timeoutMs: 5000`.

**4. White-box artifacts.** Every intermediate is a readable file on disk — `persona.md`, scenario
blocks, task canvases, atoms. Debugging recall quality means reading markdown along the chain
persona → scenario → atom → raw conversation, not interrogating an opaque vector index.

**5. Skills as extracted, versioned assets.** A `SKILL.md` + `files/` per skill, with versions,
resources, search, routing, and *conversation-driven extraction* (`/v3/skill/*`) — successful
agent runs get promoted into reusable, discoverable workflows rather than evaporating.

**6. Operational honesty in the docs.** A `v2→v3` data-format migration script with a `--dry-run`
mode and a back-up warning; an explicit rule that binding to a non-loopback address *requires*
the gateway API-key env var to be set; CORS off by default with a "never `*` in production"
note; and a stated
requirement to validate team/user/agent ownership on every request.

### Strengths

- Memory as a **governed, multi-tenant asset** — ownership, visibility, ACLs, and agent bindings —
  rather than a per-user key-value blob. This is the part almost nobody else builds.
- Distillation runs on a **debounced background scheduler with a permit pool**, so memory quality
  work never sits on the user's latency path.
- **Auditable by construction.** Plain-markdown intermediates make "why did it recall that?"
  answerable by reading a file.
- **Graceful degradation is the default**, not a fallback: no embedding provider → BM25; no vector
  DB → SQLite; recall times out → the turn still proceeds.
- **Clean seam** between the memory pipeline and the agent runtime; adapters are thin and the
  adapter contract is stated in three sentences (write L0, recall L1–L3, inject bounded labelled
  context).
- Context offload and context compression are **designed together**, which is rare.

### Weaknesses / Limitations

- **Four services, one product.** Core + Knowledge + Panel + Proxy, each with its own port, env
  surface, and Dockerfile. Nothing here is a single-binary drop-in.
- **Young and unsettled.** Four months old, default branch is a feature branch, 464 PRs, and
  already one breaking on-disk format migration (v2→v3). Vendored code would be chasing a moving
  target; a mixed `NOASSERTION`/MIT licence picture compounds it.
- **Docs are partly untranslated.** `MemoryKnowledge/README.md` is Chinese-only, as are the
  gateway-config comments — a real cost for a team that has to operate it.
- **LLM cost and latency are structural.** Extraction, scenario building, and persona regeneration
  are all LLM calls on a timer. Nothing in the config caps spend; `maxTokens: 32000` per call with
  a 300s timeout, defaulting to a vendor-hosted endpoint.
- **No recall observability.** The README concedes it: traceability exists but is manual file
  inspection; there is no dashboard, no recall-quality metric, no eval harness. You cannot tell
  whether memory is helping without running a benchmark yourself.
- **Tuning burden is admitted, not solved.** Extraction cadence, persona triggers, and recall
  timeouts are all knobs with no guidance on how to set them for a given workload.
- **Not MCP-native** on the hot path — integration is a bespoke HTTP contract plus per-framework
  adapters, so every new runtime is new adapter code.
- **Sensitive data flows outward by default.** Conversations, personas, and indexed source code are
  all sent to an external LLM endpoint for distillation. Local-only operation means BM25 retrieval
  and no distillation at all.

### Visible vs Hidden Metrics

**Visible (all self-reported; no independent replication found):**

| Claim | Number |
| --- | --- |
| Long-term persona-recall accuracy (public benchmark) | 48% → 76% (+59% relative) |
| Broad multi-source search success (public benchmark) | +51.52%, tokens −61.38% |
| Software-engineering task success (public benchmark) | +9.93%, tokens −33.09% |
| Long-context reasoning success (public benchmark) | +7.95%, tokens −30.98% |
| Adoption | 17.6k stars, 1.6k forks |

Caveats that matter more than the numbers: measured "over continuous multi-turn sessions, not
isolated turns" — i.e. against a baseline with *no* memory and *no* offload, which is the easiest
possible comparison; the harness, model, and seeds are not published in the README; and the token
savings and the success-rate gains are reported together without separating which mechanism
(offload vs. recall) produced which. The star count reflects a cloud vendor's launch reach as much
as engineering merit.

**Hidden (the costs an adopter inherits):**

- **Operational load:** four services, four ports, three databases' worth of state, plus a
  callback loop between Knowledge and Panel that must be wired correctly (three env vars whose
  `/v3` suffix rules differ per variable — documented, and exactly the kind of thing that breaks
  silently).
- **Ongoing LLM spend, unbounded:** a background timer that calls an LLM every 5 conversations and
  regenerates a persona every 50, per user, forever. Cost scales with conversation volume, not
  with value extracted, and there is no budget knob.
- **Data-egress coupling:** distillation ships conversation content and indexed source to an
  external inference endpoint. For a self-hosted, local-first platform this is the single largest
  hidden cost.
- **Format churn:** one breaking on-disk migration in four months. Every upgrade is a data
  migration until the format settles.
- **Tuning as permanent maintenance:** seven interacting scheduler constants with no defaults
  guidance and no metric to tune against — recall quality is invisible, so tuning is guesswork.
- **Learning curve:** the offload subsystem alone (`mmd-injector`, `state-manager`, `reclaimer`,
  `context-token-tracker`, L3 helpers) is a stateful, hook-ordered machine entangled with the
  agent's compaction logic. Adopting it means owning that entanglement.
- **Lock-in shape:** low at the storage layer (SQLite + markdown, trivially readable), high at the
  integration layer (bespoke HTTP contract, per-framework adapters, not MCP).

**Weighing.** The visible wins split cleanly into two mechanisms with very different cost
profiles, and they should be judged separately rather than as one package:

1. **Symbolic context offload** (the −30% to −61% token results). The mechanism is
   self-contained, the storage substrate is plain files, and it needs *no* extra service and *no*
   extra LLM calls. Hidden costs are mostly implementation complexity, which is bounded and
   one-off. This is where the value density is.
2. **The layered memory hub** (the persona-recall result). Real capability, but the hidden costs —
   four services, perpetual background LLM spend, outward data egress, unsettled on-disk format,
   unmeasurable recall quality — are recurring and land squarely on the operator. For a
   local-first, self-hosted platform the egress and spend costs in particular can outweigh a
   self-reported accuracy gain on a benchmark nobody else has reproduced.

The genuinely portable assets are **ideas, not code**: the debounced background distillation
scheduler, the budget-aware single-marked-message injector, the "compression must skip the memory
message" invariant, the embedding-optional retrieval default, and — least glamorous, most valuable
— making tenancy a *required argument* on the memory data plane rather than an ambient default.

---

## AutoBot Comparison

**Audit scope (files read, not guessed):** `autobot-backend/chat_history/layers.py`,
`chat_history/context_overflow.py`, `chat_workflow/llm_handler.py` (lines 795–849),
`memory/manager.py`, `memory/verbatim_store.py`, `memory/essential_story.py`,
`memory/working_memory.py`, `memory/compat.py`, `memory/memory_privacy_test.py`,
`memory/security_idor_hotfix_test.py`, `services/memory/compression.py`,
`services/skill_management/` (all modules), `skills/`, `tasks/memory_tasks.py`,
`celery_app.py` beat schedule, `knowledge/search_components/`, `agent_loop/loop.py`,
`autobot_shared/ssot_config.py`.

**Headline:** AutoBot already has *more* memory machinery than the source — five layers to their
four, a symbolic index, a skill-distillation pipeline they don't match, and user-facing memory
transparency they lack entirely. The problem is not absence. It is that **the best of it is
switched off, and one branch of it cannot fire at all**. The one genuine capability gap is
context offload of tool output.

---

### What We Can Adopt

#### 1. Tenancy as a required argument on the memory data plane — **adopt**

- **Already-exists audit:** `memory/manager.py:403` `store_memory(category, content, metadata,
  reference_path, embedding)`, `:443` `retrieve_memories(category, limit, start_date, end_date,
  reference_path)`, `:472` `search_memories(query)`. **None of the three takes a `user_id`,
  `tenant_id`, or `session_id`.** `search_memories` returns whatever the storage layer's
  `search(query)` returns, unfiltered. Tenancy exists *above* this layer
  (`memory/memory_privacy_test.py` proves cross-user list/delete rejection for the transparency
  engine; `memory/security_idor_hotfix_test.py` covers the working-memory key-shape allowlist;
  `memory/working_memory.py:33 is_working_memory_key` is a real allowlist) and *beside* it
  (`llm_handler.py:848` notes the search-before store is "user/tenant-scoped by the store"). The
  general memory manager is the hole.
- **Visible benefit:** cross-tenant memory leakage becomes unrepresentable rather than
  test-enforced; the source's `/v3` plane rejects a call missing `team_id`/`agent_id`/`user_id`.
- **Hidden cost:** low. It is a signature change plus call-site updates; the only production
  callers are `memory/compat.py:72,87,100`. No new dependency, no new service, no LLM spend.
- **Verdict:** **adopt.** The cheapest item on this list and the only one that closes a security
  shape rather than adding a feature. Hidden costs do not approach the benefit.
- **Effort:** moderate (signature + storage-layer filter + regression test).

#### 2. Context offload of tool output to `refs/` with in-context anchors — **adopt-with-conditions**

- **Already-exists audit:** searched `agent_loop/`, `services/`, `orchestration/` for
  `offload|spill.*disk|write.*artifact.*ref` — **every hit is *compute* offload**
  (`services/npu_client.py`, `services/execution/modal_backend.py:208`,
  `orchestration/orchestrator_legacy_api.py:83`), not context offload. Searched the same tree for
  `tool_result|tool_output` intersected with `trunc|offload|limit|max_|size` — **zero hits**.
  `agent_loop/loop.py:612` merges `tool_results` and `:1395 _record_observation_fingerprints`
  fingerprints them for *novelty/stagnation detection* (#6627), not for size management. Tool
  output enters context whole and stays there. The closest existing thing is
  `chat_history/context_overflow.py`, which summarises the *conversation* at 90% fill — a
  reactive whole-history compressor, not a per-observation offload. `memory/verbatim_store.py:37`
  is a term→chunk inverted index for *recall*; it is not a task-state canvas and does not reduce
  in-context size.
- **Visible benefit:** the source's largest and most credible claim (−61.38% / −33.09% / −30.98%
  tokens), and the mechanism needs no extra service and no extra LLM call.
- **Hidden cost:** high implementation complexity. The source's `src/offload/` is a stateful,
  hook-ordered machine (`mmd-injector`, `state-manager`, `reclaimer`, `context-token-tracker`, L3
  helpers) entangled with the compactor, and it depends on an invariant we would have to add:
  *the compactor must never touch the marked message.* Adopting the whole subsystem means owning
  that entanglement.
- **Verdict:** **adopt-with-conditions.** Take the *contract*, not the code, and take it in two
  independently valuable pieces: (a) large tool results spill to a file with a stable anchor the
  agent can re-read; (b) a single marked, compaction-exempt context message holding the task state.
  Condition: (a) lands and is measured first. If the token reduction from (a) alone is small, (b)
  is not worth the compactor entanglement — the same discipline #12555 already applied to the
  symbolic index (merge flag-on only if the benchmark shows a win).
- **Effort:** (a) moderate, (b) significant.

#### 3. A trimming budget guard, not a warning — **adopt**

- **Already-exists audit:** `chat_history/layers.py:285` sets `_L0_L1_MAX_TOKENS = 900` and
  `:319-325` compares the estimate against it and calls `logger.warning(...)` — then **renders
  and returns both layers anyway**. The budget is advisory. Contrast the source's
  `mmdMaxTokenRatio`, which bounds the injection as a fraction of the real context window and
  drops content to stay inside it.
- **Visible benefit:** the "acceptance-criterion guard" in the docstring becomes a guard.
- **Hidden cost:** near zero — the trim decision is local to `build()`.
- **Verdict:** **adopt.** A constant that only logs is a constant that does nothing.
- **Effort:** trivial.

#### 4. Event-driven debounce bands on distillation, alongside cron — **adopt-with-conditions**

- **Already-exists audit:** AutoBot's scheduling is Celery beat with **fixed wall-clock crontabs**
  — `celery_app.py:245` (04:00 UTC), `:251` (04:20, "after trajectory pass"), `:239` (Monday
  03:00). Event-driven memory writes exist and are off the hot path
  (`tasks/memory_tasks.py`, #5073, `acks_late=True`, idempotent retries).
  `services/skill_management/skill_distillation_scheduler.py` is a *periodic* leader-elected pass
  with a durable cursor (#12809). What is absent is the source's shape: an **idle-flush timeout**
  (`l1IdleTimeoutSeconds: 600`), a **debounce delay** behind the upstream stage
  (`l2DelayAfterL1Seconds: 90`), and a **min/max interval band** (`900`/`3600`) instead of a fixed
  time of day.
- **Visible benefit:** distillation tracks conversation activity instead of the clock — a session
  that ends at 09:00 is consolidated at 09:10, not at 04:00 tomorrow.
- **Hidden cost:** moderate, and it is the source's own admitted weakness — seven interacting
  constants with no guidance and **no metric to tune against**. Adding an interval band without a
  recall-quality metric means adding tuning surface we cannot evaluate. Also: more frequent
  distillation is directly more LLM spend, uncapped in their design.
- **Verdict:** **adopt-with-conditions**, and the condition is a hard blocker: this is gated on
  recall-quality measurement (**#13251 / #13243** — `knowledge/rag_benchmarks.py` guards a fake
  embedding over 20 synthetic docs). Tuning knobs before the metric exists is the mistake, not
  the fix. The idle-flush alone (cheap, obviously correct, no new tuning surface) can land first.
- **Effort:** idle-flush moderate; full band significant and blocked.

#### 5. A real token counter — **adopt-with-conditions**

- **Already-exists audit:** `services/memory/compression.py:26-38` estimates tokens as
  `len(text.split()) * 1.3`, with a docstring claiming "within ~10% of real BPE counts for English
  prose". `chat_history/layers.py` uses per-layer `token_estimate()` on the same footing.
  `context_overflow.py` thresholds (80% warn / 90% compress) sit on top of these estimates.
  The source ships a dedicated `l3-token-counter` and a `fast-token-estimate` as separate paths.
- **Visible benefit:** the 90% auto-summarise trigger stops firing early or late by a
  double-digit margin on code, CJK, or JSON-heavy content — where `words × 1.3` is worst.
- **Hidden cost:** a real tokenizer is a dependency with per-model vocabularies and a cold-start
  cost, and the estimate is on a hot path.
- **Verdict:** **adopt-with-conditions** — keep the heuristic as the fast path (it is fine for
  English prose), and use an exact count only at the compress/overflow decision boundary, where
  being wrong is expensive. A blanket swap is rejected on hidden cost.
- **Effort:** moderate.

#### 6. Rejected by hidden metrics

| Candidate | Why rejected |
| --- | --- |
| The four-service topology (Core/Knowledge/Panel/Proxy, 3 ports + callback loop) | AutoBot's memory is already in-process behind `MemoryManager` with Celery for async work. Splitting it out buys nothing we lack and adds three services, a callback contract, and a second source of truth for tenancy. |
| LLM-driven persona regeneration on a timer, per user, forever | Unbounded recurring spend with no budget knob, and it egresses conversation content to an external endpoint. AutoBot's `memory/essential_story.py` already produces the always-loaded summary from *stored facts* with usage-aware reinforcement (#12553) and a fingerprint-keyed cache — no LLM call per regeneration. Ours is strictly cheaper for the same output. |
| Bespoke HTTP capture/recall contract + per-framework adapters | Integration-layer lock-in; every new runtime is new adapter code. AutoBot's MCP surface already exists and is the better seam. |
| `git clone` + index as the code-graph ingest | AutoBot's code graph is further along and already has its own tracked backlog (#13505, #13467). Nothing here to import. |

---

### What We Already Do Better

- **Skill assets.** The source extracts skills from conversations on a timer. AutoBot has
  `services/skill_management/` with `skill_extractor` (#4338), `skill_proposer`, `skill_ranker`
  (#4337), `skill_feedback`, `skill_metrics`, `skill_health_scheduler`, and a
  `skill_distillation_scheduler` (#12809) that is **leader-elected via a Redis SETNX-with-TTL
  lease and advances a durable cursor only after a conversation is fully processed** — plus
  `skills/governance.py`, `skills/gap_detector.py`, `skills/bundles.py`,
  `skills/dependency_resolver.py`, `skills/external_importer.py`. Their design would propose the
  same skill N times from N workers; ours cannot.
- **User-facing memory transparency.** `memory/transparency.py` with
  `list_user_memories` / `forget_memory` / `forget_everywhere` / `export_user_memory`, tenant
  isolation proven by test (`memory/memory_privacy_test.py`), plus IDOR and CSWSH regression
  coverage (`memory/security_idor_hotfix_test.py`). The source has ACLs for *sharing*; it has no
  subject-access or right-to-be-forgotten path at all.
- **Usage-aware memory ranking.** `memory/essential_story.py:36-63` boosts a fact's static
  `quality_score` by recall frequency and recency with an exponential half-life (#12552/#12553),
  and has a deterministic `fact_id` tiebreaker so equal-quality facts stop flipping on Redis SCAN
  order. Their L3 persona has no usage feedback loop — a fact that is never recalled ranks the
  same as one recalled daily.
- **Retrieval as a real component suite.** `knowledge/search_components/` (`bm25.py`,
  `hybrid_search.py`, `keyword_search.py`) plus `advanced_rag_optimizer.py`, `services/rag_service.py`
  and `knowledge/facts.py`. Hybrid is our normal path; theirs ships with
  `embedding.provider: "none"` as the default, i.e. BM25-only out of the box.
- **Evidence discipline before enabling.** `memory/verbatim_store.py:37-41` — the symbolic drawer
  index is default-off with an explicit rule that it merges flag-on *only if*
  `benchmarks/verbatim_symbolic_benchmark.py` shows a latency win with no recall regression. The
  source ships seven scheduler constants with no metric and concedes it has no recall observability.
- **No egress required to remember.** Distillation in the source is an external LLM call on
  conversation content and indexed source. AutoBot's always-loaded summary path is local fact
  ranking. For a self-hosted, local-first platform this is the single most important difference,
  and it favours us.
- **Five layers, and a goal dimension they lack.** `chat_history/layers.py` adds
  **L4 GoalAncestry** (goal→project→tenant chain, GH#6469) on top of L0–L3. Nothing in the source
  connects memory to an organisational goal hierarchy.

---

### Gaps & Opportunities

Ordered by impact. Items 1–3 are defects found during this audit, not feature requests — they are
existing AutoBot work that does not run.

0. **Two of the five layers are structurally disconnected — the stack cannot work as wired.**
   Found by tracing the call site after the first pass. `chat_workflow/llm_handler.py:814` reads
   the memory graph as `getattr(self, "memory_graph", None)`. `self` is a `ChatWorkflowManager`,
   which inherits `ConversationHandlerMixin, ToolHandlerMixin, LLMHandlerMixin,
   SessionHandlerMixin` (`chat_workflow/manager.py:233-238`) — **none of them defines
   `memory_graph`**. The attribute lives on `ChatHistoryBase` (`chat_history/base.py:91`, assigned
   at `:244`), a different object. The `getattr` default therefore always returns `None`, and
   `Layer2OnDemand.render` returns `""` on its first branch (`layers.py:152-154`). Combined with
   L4 below, **enabling the feature flag today yields L0 identity + L1 essential story + L3 only
   on keyword match** — the legacy path plus a static identity block. That is almost certainly
   why the A/B never produced a reason to flip the flag: the experiment could not have won.
   Canonical accessors exist (`utils/resource_factory.py:94
   ResourceFactory.get_chat_history_manager`, `utils/chat_utils.py:285`), so this is a sourcing
   fix, not new plumbing.
1. **L4 GoalAncestry can never fire in production.** `chat_history/layers.py:361-367` gates L4 on
   `await l4.should_load(goal_ancestry)`, and `build()` defaults `goal_ancestry=None`
   (`:295`). The **only** production call site — `chat_workflow/llm_handler.py:810-816` — passes
   `user_message`, `model_name`, `session_id`, `memory_graph`, `knowledge_service` and
   **never passes `goal_ancestry`**. GH#6469's layer is unreachable even with the feature flag on.
   The producer exists and matches the consumer exactly:
   `llc/services/goal.py:239 GoalService.get_goal_ancestry_for_work_item(session, goal_id)`
   returns a root-first `list[dict]` with `id`/`title`/`level`/`status` and cites GH#6469 in its
   own docstring — precisely the shape `Layer4GoalAncestry.render` reads. Both ends were built;
   only the connection is missing. *Wire it in — per the no-deletion rule this is unfinished
   work, not dead code.*
2. **The whole tiered stack is shipped dark.** `autobot_shared/ssot_config.py:1985` —
   `tiered_context_enabled: bool = Field(default=False, ...)`. #5066's five-layer, budget-aware,
   selectively-loaded pipeline exists, is tested (`chat_history/layers_test.py`,
   `tests/test_goal_ancestry_layer.py`), is wired at one call site, and is **off**. The comment at
   `llm_handler.py:800` describes it as an "A/B against legacy path" — no recorded A/B result was
   found in the audit. Either the comparison ran and the outcome should be recorded and the flag
   flipped, or it never ran and the work is parked. This is the highest-impact item on the list
   because everything else in this section is downstream of it.
3. **`memory/compat.py` has no production callers.** The only importer found repo-wide is
   `tests/memory/test_compat_singletons.py:18`. It is also the *only* caller of the untenanted
   `search_memories` (`:87`, `:100`) and `retrieve_memories` (`:72`). Either it is the migration
   shim something still needs and the caller is missing, or the migration finished and it should
   be recorded as such with a link. Not a deletion candidate.
4. **The memory data plane has no tenancy parameter** (item 1 in *What We Can Adopt*). Worth its
   own issue with a security label — the guards that exist are at the layers above.
5. **No context offload of tool output** (item 2 in *What We Can Adopt*). The largest genuine
   capability gap, and the only one where the source has something we have no analogue for.
6. **The budget guard does not guard** (item 3). Trivial fix, and it undermines an acceptance
   criterion that is presumably recorded as met.
7. **Recall quality is still unmeasurable** — already filed as **#13251 / #13243**. This audit
   independently reconfirms it: five of the items above want a tuning decision, and none of them
   can be evaluated without it. This is the blocker that makes item 4's interval bands premature.

---

### Specific Code/Files Affected

| File | Change |
| --- | --- |
| [chat_workflow/llm_handler.py:814](../../autobot-backend/chat_workflow/llm_handler.py#L814) | Replace `getattr(self, "memory_graph", None)` — which can never resolve — with the canonical `ResourceFactory.get_chat_history_manager()` accessor, so L2 can fire (gap 0). |
| [chat_workflow/llm_handler.py:810](../../autobot-backend/chat_workflow/llm_handler.py#L810) | Pass `goal_ancestry=` from `GoalService.get_goal_ancestry_for_work_item()` so L4 can fire (gap 1). |
| [autobot_shared/ssot_config.py:1985](../../autobot_shared/ssot_config.py#L1985) | Flip `tiered_context_enabled` default once the A/B result is recorded — or record that it is parked (gap 2). |
| [chat_history/layers.py:319-325](../../autobot-backend/chat_history/layers.py#L319-L325) | Trim to `_L0_L1_MAX_TOKENS` instead of only warning; bound as a ratio of the real context window rather than a flat 900 (adopt 3). |
| [memory/manager.py:403,443,472](../../autobot-backend/memory/manager.py#L403) | Add required tenant/user scoping to `store_memory` / `retrieve_memories` / `search_memories`; push the filter into `_general_storage` (adopt 1). |
| [memory/compat.py:72,87,100](../../autobot-backend/memory/compat.py#L72) | Resolve the shim: locate the missing caller or record the completed migration; update for the new tenanted signatures (gap 3). |
| [agent_loop/loop.py:612](../../autobot-backend/agent_loop/loop.py#L612) | Spill oversized `tool_results` to a session-scoped artifact file, substituting a stable anchor in context (adopt 2a). |
| [chat_history/context_overflow.py](../../autobot-backend/chat_history/context_overflow.py) | Add the compaction-exempt marked-message invariant if 2b proceeds; move the 90% trigger onto an exact token count (adopt 2b, 5). |
| [services/memory/compression.py:26-38](../../autobot-backend/services/memory/compression.py#L26-L38) | Keep `words × 1.3` as the fast path; exact count at the compress decision boundary (adopt 5). |
| [services/skill_management/skill_distillation_scheduler.py](../../autobot-backend/services/skill_management/skill_distillation_scheduler.py) | Add an idle-flush timeout; interval bands deferred behind #13251 (adopt 4). |

---

### Bottom Line

Four of the eight prioritised items are **AutoBot code that already exists and does not run** —
two of the five context layers structurally disconnected, the tiered stack flag-off with no
recorded A/B result it could have won, and a compat shim with no caller. One
is a **tenancy hole** on the memory manager. One is a **real capability gap** (tool-output
offload) worth taking as a contract in two measured steps rather than as a subsystem. One is
trivial (a guard that only logs). One is the blocker underneath the rest (#13251).

The source's genuine contribution to us is not code and not architecture. It is the observation
that a memory layer nobody can measure is a memory layer nobody can tune — which is the same
conclusion #13251 already reached from the other direction.
