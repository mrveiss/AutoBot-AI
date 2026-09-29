---
tags:
  - research
  - agents
  - plugin-architecture
  - source-analysis
---

# Source Analysis: a self-hosted "AI employee" workforce platform (node-graph agent OS)

*Phase 1 only — AutoBot comparison not started. Source identity withheld per the research
skill's anonymization rule; the reference work is a third-party MIT-licensed vendor project.*

## What It Is

A self-hosted desktop/server platform that packages agent teams as "employees": the operator
describes a job in plain words, the product drafts a small team (one lead plus a few specialist
agents), and the team runs in the background on the operator's own machine — waking on an
inbound message, a webhook or a schedule. The unit of composition is a visual node graph, so a
team is assembled by dragging tool, model, skill, memory and agent nodes onto a canvas and
wiring handles; no code. Four surfaces ship from one repo: a Python backend (FastAPI-style,
WebSocket-first), a React-Flow canvas SPA, an Electron desktop shell that bundles its own
Python/uv runtime, and a CLI/supervisor for headless hosts. Maturity: ~1 year old, ~970 stars
/ 146 forks, latest release v0.2.1, commits landing the same day this analysis was written —
but **4 contributors, of whom one holds 1,361 of ~1,383 commits** (next-highest human: 9).
Bring-your-own-key across 11 cloud providers plus local servers; no subscription tier.

## Architecture & Key Patterns

| Pattern | How it is done |
|---|---|
| **Plugin-per-folder as backend SSOT** | One node = one folder `server/nodes/<group>/<name>/__init__.py` subclassing `ActionNode`/`TriggerNode`/`ToolNode`, declaring Pydantic `Params`/`Output` plus `@Operation` methods. Auto-registers at import; **zero frontend edits** — the UI renders the node from the registered spec. Icon is `icon.svg` in the folder, colour is `meta.json`; neither is a class attribute. 43 node groups, 140+ node types. |
| **Dual execution modes with automatic fallback** | A thin `WorkflowService` facade routes each run through a durable workflow engine when one is reachable, else a plain sequential walk. Each run gets an isolated `ExecutionContext` with no shared globals. Scheduling is continuous `FIRST_COMPLETED` — a node's dependents start the moment it completes, not at a layer boundary. |
| **WebSocket-first API** | Most REST is replaced by one WebSocket endpoint with a core `MESSAGE_HANDLERS` map plus a `ws_handler_registry` that plugins extend. REST is reduced to auth, credentials, webhook, workspace, schemas. |
| **Context ≠ Memory (formal RFC)** | *Context* is a backend-owned, immutable execution journal used to rebuild the next provider request; *Memory* is an explicitly invoked tool over durable facts. Canvas nodes are declarative policy surfaces only and never own the journal, provider binding, tenant scope or compaction algorithm. One context owns multiple isolated threads selected by chat-session → delegated-task → execution id. |
| **Agent teams with an intrinsic task manager** | A team lead gets a non-removable `task_manager` tool (not a palette node). It may assign only to agents wired to its `input-teammates` handle, with a bounded mission, context and acceptance criteria. Durable task lifecycle `blocked → queued → running → submitted → accepted/failed`; completion fires an event that triggers a **separate lead review pass** before anything reaches the human. Delegation depth is capped at two child layers; cycles and ambiguous delegate names are rejected at validation. |
| **Native provider layer, no framework** | A `ChatUnifier` + `run_native_agent_loop` over lossless native messages and provider-neutral `AgentToolSpec`s. Providers self-register via a single `register_provider(ProviderSpec(...))` call at module bottom; OpenAI-compatible providers are a JSON config entry plus one name in a `_COMPAT_PROVIDERS` list. The prior orchestration framework was removed outright, and histories recorded before the cutover are **refused rather than replayed**. |
| **Visibility allowlist decoupled from the registry** | One JSON file gates palette entries, credential categories and skill folders. Deleting a plugin would break saved graphs that reference it, so the allowlist hides the *affordance* while the registry still resolves old references. Two tiers: absolute blocklists (always enforced, beat dev mode) and a positive list that governs only what the plain-language "hire" flow may assemble. |
| **Split persistence plane** | Operational graph state in one SQLite database, credentials in a separate encrypted one, with the boundary drawn in a published diagram. |
| **Skills as plain-text playbooks** | 78 `SKILL.md` files across 18 folders, editable in-UI, materialized into the agent's workspace; a "master skill" node expands to its enabled entries. |

## Notable Implementation Details

1. **A runtime canvas-mutation tool.** One plugin (`server/nodes/tool/agent_builder/`, ~1,290 lines)
   exposes five operations to the model — `inspect_canvas`, `add_tool`, `add_skill`,
   `add_subagent`, `create_workflow` — so an agent extends *its own* team mid-task and the change
   persists. The honest part: tools bind at the start of each turn, so every mutation summary ends
   with *"Available on your next turn"* to stop the model looping on a tool that does not exist
   yet. Mutations broadcast a `workflow_ops_apply` event so the live canvas redraws.
2. **Compaction stated as invariants, not prose.** Only committed prefixes compact; a boundary
   never splits an assistant tool call from its results; the active checkpoint plus the exact
   event tail is the only source (startup Markdown never is); a candidate must serialize for the
   provider, cover the claimed sequence *and* reduce active tokens before activation; activation
   is **compare-and-swap** against checkpoint and source hash; concurrent writes keep an exact
   uncompacted tail; raw journal events are immutable; a failed attempt is recorded and preserves
   the prior checkpoint. Providers with verified native compaction use it, others get portable
   structured checkpoints, and a provider switch opens a new epoch with a portable handoff while
   archiving the opaque provider state.
3. **Memory as one multi-op tool with a store-authority rule.** `remember / recall / list / get /
   update / forget`, optimistic versions, idempotent mutation receipts, expired items omitted.
   **SQL/FTS is authoritative and stays usable when embedding generation fails; the embedding
   projection is a rebuildable accelerator.** The namespace is derived backend-side from
   authenticated owner + workflow + node and is *absent from the tool input schema*, so the model
   cannot address another tenant's memory. Memory explicitly does *not* auto-inject prompts,
   persist transcripts or compact context.
4. **Capability roster lines.** Each teammate is rendered into one system-prompt line —
   `- <node_id>: <label> (<type>) - tools: …; skills: …` — because the long per-delegate tool
   descriptions are deliberately hidden from the lead's model. The doc states the failure it
   prevents: otherwise a teammate labelled "Web Agent" holding a scraping toolkit is
   indistinguishable from one holding nothing. Locked by a topology test.
5. **Auto-skill phantom edges.** Some tools ship a default skill; a canvas-edit hook creates the
   skill connection automatically so the model gets both the invocation schema and the usage
   guidance from one wire instead of two.
6. **Tool errors must propagate.** House rule: never catch inside a tool callback and return
   `{"error": …}` — re-raise, because the surrounding lifecycle owns the `error` broadcast and the
   "model sees the failure and continues" behaviour depends on it. A closed legacy-call-site list
   in a test prevents new raw-dict broadcasts.
7. **Docs prescribe live counts instead of frozen numbers.** Contributor docs give the *command*
   for each figure (`len(NODE_METADATA)` after importing nodes, `find … -name SKILL.md | wc -l`)
   and warn which naive glob over- and under-counts. Diagrams carry the source files they were
   drawn from in their SVG `<desc>`.
8. **Known limitations are published.** The team doc states plainly that off the durable engine,
   `assign_task` persists a `queued` task and returns a delegation request that only the durable
   workflow consumes — so in the in-process path *no teammate ever runs it*, with the two missing
   config keys named.

## Strengths

- **Plugin ergonomics.** Adding a tool, provider, skill or integration is one folder and no
  frontend change. That is the property that produced 140+ nodes with a 4-person contributor list.
- **Contract/invariant testing culture.** 84 top-level test files plus 11 test packages
  (`nodes/`, `credentials/`, `llm/`, `temporal/`, `routers/`, …), a `NodeTestHarness`, and tests
  whose job is to freeze a contract rather than exercise a feature — parity between the two
  execution paths, "frontend holds no copies of node types", hire-payload contract, catalogue sync.
- **CI that includes the thing most repos skip:** build + frontend lint + typecheck + frontend
  tests, backend pytest, CLI pytest, **and a cross-OS install/start/stop smoke job**.
- **Measurement discipline** (item 7 above) and **disclosed gaps** (item 8) — the two habits that
  make an external reader able to trust the rest.
- **Documentation density:** 50+ internal deep-dive docs, 14 source-backed architecture diagrams,
  3 numbered RFCs for the load-bearing contracts (schema translation, context/memory, provider
  contract).
- **Distribution breadth** from one tree: signed-app-less desktop installers for 4 targets, a
  curl/iwr installer, a Docker compose self-host, and a one-command cloud deploy.

## Weaknesses / Limitations

| # | Weakness | Evidence |
|---|---|---|
| 1 | **Bus factor 1.** One author holds ~98% of commits; the next human contributor has 9. Every architectural rule above lives in one head. | contributors API: 1361 / 12 (bot) / 9 / 1 |
| 2 | **No file-size discipline.** `server/core/database.py` ≈190 KB, `server/services/ai.py` ≈123 KB, `server/routers/websocket.py` ≈72 KB in single modules; the AI-contributor memory file is ≈323 KB. AutoBot's ceiling is 600 lines. | contents API sizes |
| 3 | **A published functional hole.** Delegation silently no-ops on the non-durable execution path (weakness the project itself documents, see Notable #8) — the fallback mode advertised as automatic is not feature-equivalent. | `docs-internal/agent_teams.md` § Known limitations |
| 4 | **A committed `.env` that is not git-ignored**, carrying `SECRET_KEY`, `JWT_SECRET_KEY` and `API_KEY_ENCRYPTION_KEY`. The values are placeholder-shaped (they contain change/dev-style marker words, not high-entropy material), so this is not a live leak — but a tracked `.env` is the mechanism by which the next real key gets committed, and a shipped default encryption key means every self-host install shares one unless the operator overrides it. | `.env` present in tree at 6,135 B; `grep -nE '^\.?env' .gitignore` → no hits |
| 5 | **No Python lint or type gate in CI.** Frontend gets eslint + typecheck; the backend job runs pytest only. | grepped `predeploy.yml` for `ruff\|mypy` → no hits |
| 6 | **Unsigned desktop builds** — documented as requiring the operator to click past macOS Gatekeeper and Windows SmartScreen. | README quick start |
| 7 | **Two execution paths to keep at parity** is a permanent tax; they already ship an edge-condition parity test, which is the symptom, not the cure. | `server/tests/test_edge_condition_parity.py` |
| 8 | **Breaking-change churn at v0.2.x:** the orchestration framework removed, a wire-format v1/v2 duality purged, pre-cutover durable histories *refused*. Fine for a pre-1.0 product; costly for anyone who forks it. | RFC-0002 §2 |

## Visible vs Hidden Metrics

**Visible (advertised):** 140+ tools · 11 cloud providers + local · 78 ready skills · 12 canvas
themes · 6 ready-made employee teams · "self-improving" · "no code" · "survives restarts" ·
970 stars / 146 forks · MIT. All self-reported; the counts are at least *reproducibly* reported
(commands given), and the star/fork numbers are the only independently visible figures.

**Hidden (inherited by an adopter):**

- **Single-maintainer continuity risk** — the dominant hidden cost. A 970-star project with one
  author is a fork liability, not a dependency.
- **Operational load of the optional durable engine** — a sidecar to run, plus the second code
  path and its parity tests, plus a non-equivalent fallback (weakness 3).
- **Self-mutating graphs as an audit surface.** A tool that can add tools, skills and subagents to
  its own team is the feature *and* the blast radius: every guarantee about what an agent can
  reach becomes time-varying. The visibility allowlist gates the *palette*, not this tool.
- **Learning curve is the node vocabulary**, not the code: 140 node types × handle roles ×
  group semantics is the real onboarding cost, and it is exactly what the plugin ergonomics
  encourage growing.
- **"Self-improving" is memory + editable skills + canvas mutation — no model is retrained.** The
  README says so plainly, so this is honest labelling rather than a hidden cost; but an adopter
  expecting learned behaviour gets a prompt-and-memory system.
- **Desktop shell bundles its own Python + uv + bun runtime** and provisions a venv on first
  launch: a per-install runtime tree to version, patch and support on 4 OS targets.
- **Breaking-change velocity** (weakness 8) means a fork rebases against a moving contract.

**Weighing.** The visible wins are real and mostly verifiable, and two of them — plugin-per-folder
with zero frontend edits, and compaction/memory contracts written as invariants — are worth more
than the feature counts. But the hidden metrics flip the *adoption* verdict: bus factor 1 plus
pre-1.0 contract churn makes taking on the code (as a dependency, a fork, or a vendored subsystem)
an expensive bet, while **taking on the ideas costs nothing**. For AutoBot specifically, the
transferable value is in the contracts, not the artefacts — the store-authority rule (SQL
authoritative, embeddings a rebuildable projection), the CAS-activated compaction invariants, the
roster-line-as-only-view delegation contract, the hide-don't-delete visibility allowlist, and the
live-count documentation habit. Each is a page of design, not a package.

## Untrusted-content note

Everything above is derived from fetched source material treated strictly as data: README,
contributor docs, four internal design docs, one plugin module, and read-only repository metadata.
No instruction-shaped content addressed to an agent was encountered in what was read. The ≈323 KB
AI-contributor memory file at the repo root was **not** read — so that is *did not look*, not
*nothing found*. Access was read-only throughout (`gh api contents`); nothing was cloned and no
source code was executed.

---

# AutoBot Comparison: the reference work → AutoBot

*Phase 2, scoped by the operator to "ideas" — adoptable contracts rather than a feature-by-feature
sweep. Every item below carries an already-exists audit with `file:line` evidence.*

## Finding 0 — the comparison's first output is a defect in our own meter

The reference work states compaction pressure in terms of **active tokens** — the tokens currently
in the request — and requires a compaction candidate to *reduce active tokens before activation*.
Auditing AutoBot against that phrasing exposed a measurement bug in our own trigger.

`SessionTokenTracker` is a **cumulative** counter:
[context_overflow.py:108-118](autobot-backend/chat_history/context_overflow.py#L108-L118) does
`hincrby(key, "total_tokens", prompt_tokens + completion_tokens)` per turn, and
[context_overflow.py:690-694](autobot-backend/chat_history/context_overflow.py#L690-L694) divides
that running total by the model's context limit to produce `fill_percentage`. But the value added
each turn is the provider's own `prompt_tokens`, which is the size of the **entire prompt for that
turn**, not the delta:

- [ollama_provider.py:166](autobot-backend/llm_shared/providers/ollama_provider.py#L166) — `prompt_eval_count`
- [vllm.py:112](autobot-backend/llm_shared/providers/vllm.py#L112) — `len(output.prompt_token_ids)`
- [anthropic.py:357](autobot-backend/llm_shared/providers/anthropic.py#L357) — `response.usage.input_tokens`
- reaching the tracker unmodified via [overflow_integration.py:92-105](autobot-backend/chat_history/overflow_integration.py#L92-L105) → [api/chat.py:836](autobot-backend/api/chat.py#L836)

So the meter sums the whole history once per turn: it grows ~quadratically in turn count while real
fill grows linearly. A 2k-token conversation on an 8k model reads as "over 100% full" after ~5
turns, at ~25% actual fill.

**The proof that this is a bug and not a convention** is inside the same file: after compaction,
[context_overflow.py:820-836](autobot-backend/chat_history/context_overflow.py#L820-L836) resets the
session and re-seeds it with `estimate_fast(...)` **per retained message** — the sum-of-message-sizes
convention, which is the correct one for fill. One counter, two incompatible meanings: conversation
size immediately after a compaction, cumulative spend from the next turn onward.

**Consequences:** compaction fires far earlier and far more often than the 90% threshold implies
(each run is a paid LLM call that collapses history), and the 80% `context_warning.fill_percentage`
shown to the user at [api/chat.py:858-868](autobot-backend/api/chat.py#L858-L868) is wrong.

**Not a duplicate.** `gh issue list --state all` searched for `SessionTokenTracker`,
`fill_percentage`, `context overflow token accounting` and `compaction pressure`: the neighbours are
#13694 (the *estimator* was words×1.3 — closed), #14066 (the *split point* was a raw index — closed)
and #14065 (a failed summary reset the counter anyway — closed). None of them is about the
counter's accounting convention. `fill_percentage` returns zero issues.

## What We Already Do Better

### Store authority — we have the rule the reference work states in prose, in code, with a guard

Their memory RFC says SQL/FTS is authoritative and the embedding projection is a rebuildable
accelerator — for one subsystem, as a paragraph. AutoBot has it as an enforced table:
[store_authority.py:6-34](autobot_shared/store_authority.py#L6-L34) declares three rules, every
concept names its `system_of_record`, `rebuilt_by` names the code that reconstructs each projection
so the claim is checkable, and `repo_tests/store_authority_test.py` makes an undeclared dual write a
finding. It is deliberately in code rather than docs so it is reachable *from the copy site* — 13
non-test modules call it, including [fact_store.py](autobot-backend/knowledge/fact_store.py),
[fact_projection.py:5-20](autobot-backend/knowledge/fact_projection.py#L5-L20) (with
`rebuild_fact_projections` as the promised reconstruction) and
[work_claims.py](autobot_shared/coordination/work_claims.py).

Their "remains usable when embedding generation fails" clause is also already covered: the KB keeps
an independent BM25 index ([bulk.py:1196-1198](autobot-backend/knowledge/bulk.py#L1196-L1198),
[fact_projection.py:260](autobot-backend/knowledge/fact_projection.py#L260)) plus
`hybrid_search` at [relations.py:321-323](autobot-backend/knowledge/relations.py#L321-L323).

### Compaction safety — two of their invariants already landed, with the reasoning recorded

- *"A boundary never splits an assistant tool call from its tool results"* → `_pick_boundary` +
  `_tool_calls_of` + `_sanitize_tool_messages`, [context_overflow.py:269-297](autobot-backend/chat_history/context_overflow.py#L269-L297) and [:434-466](autobot-backend/chat_history/context_overflow.py#L434-L466), landed as #14066.
- *"Failure records the attempt and preserves the prior state"* → `SummarizationFailed` propagates
  deliberately so the tracker reset cannot run on an uncompressed history, and the failure is
  surfaced to the user rather than only logged (#14065): [context_overflow.py:795-806](autobot-backend/chat_history/context_overflow.py#L795-L806), [api/chat.py:864-868](autobot-backend/api/chat.py#L864-L868).
- *"Raw journal events are immutable"* → the transcript is never rewritten; only the summarizer's
  input is clipped, [context_overflow.py:323-333](autobot-backend/chat_history/context_overflow.py#L323-L333).

### Measurement discipline — theirs is a docs habit, ours is a 923-line doctrine with guards

Their contributor docs publish the *command* for each count instead of a frozen number, which is
good practice. [MEASUREMENT_DISCIPLINE.md](docs/developer/MEASUREMENT_DISCIPLINE.md) is 923 lines
covering positive controls before counts, sets-versus-counts, instantaneous counts of transient
state as samples, and the family of errors that are "correct, complete, and about a different
question" — backed by ratchet baselines and repo guards rather than convention.

## What We Can Adopt

### A1 — Pressure as *active tokens*, not cumulative spend `adopt` · trivial

**The idea:** the reference work computes compaction pressure from the active checkpoint plus the
exact event tail — the tokens in the *next request* — and never from a running total.

**Audit:** the counter is cumulative
([context_overflow.py:108-118](autobot-backend/chat_history/context_overflow.py#L108-L118)) and is
divided by the context limit ([:690-694](autobot-backend/chat_history/context_overflow.py#L690-L694)).
See Finding 0 for the full evidence chain and the dedup search.

**Visible benefit:** the trigger and the user-facing "% full" become the number they claim to be;
compaction stops firing early, which removes both a paid LLM call and an unnecessary history
collapse per false trigger.
**Hidden cost:** near zero — the correct convention is already implemented in the reset path, so
this is a change of what `add_message_tokens` is given (the latest turn's prompt size, replacing the
total) plus a positive-control test. Cumulative spend is still worth keeping, under its own key.

### A2 — Compaction activation as compare-and-swap `adopt-with-conditions` · moderate

**The idea:** *"Activation is compare-and-swap against checkpoint and source hash; concurrent writes
remain an exact uncompacted tail."* Two racing compactions cannot both win.

**Audit:** AutoBot has no such guard. `grep -nE 'compare_and_swap|expected_version|source_hash|checkpoint'`
over `autobot-backend/chat_history/*.py` and `chat_workflow/compact_hook.py` returns nothing, and
`grep -nE 'lock|semaphore|serial|mutex'` over [api/chat.py](autobot-backend/api/chat.py) returns
nothing — so two concurrent POSTs for one `session_id` can both cross the threshold, both pay for a
summary, and the later `reset_session` overwrites the earlier's accounting. No existing issue
(searched `concurrent compaction`, `summarization race session`).

**Visible benefit:** removes a duplicate-summary/duplicate-charge race and makes the tracker's
post-compaction value deterministic.
**Hidden cost:** a real one — this adds a lock or a versioned checkpoint to a path that currently has
no state beyond a Redis hash. Condition: fix A1 first. A1 alone reduces trigger frequency by roughly
an order of magnitude, which shrinks the race window this would close; do A2 only if the race is
still observable afterwards, and prefer a Redis `SET NX` compaction lease over a full checkpoint
model.

## Rejected by Hidden Metrics

| Candidate | Why rejected |
|---|---|
| **Dual execution modes with automatic fallback** (durable engine ⇄ sequential walk) | Their own docs are the argument against it: a permanent parity tax (they ship an edge-condition parity test) plus a *published functional hole* where delegation queues and never runs off the durable path. AutoBot already has one execution plane; adding a second mode buys resilience we would then have to prove twice. |
| **Provider-native compaction + epoch-on-provider-switch + portable handoff** | This machinery exists to manage *opaque provider-side* compaction state. AutoBot's summary is plain text ([`_compose_summary`](autobot-backend/chat_history/context_overflow.py#L422-L433)), i.e. portable by construction, so a provider switch mid-session needs no epoch, no archive and no handoff. Adopting it would import the cost of a problem we do not have. |
| **Approval expiry / reconciliation** | Not rejected — **already filed**. Confirmed independently here: `ApprovalStatus.EXPIRED` is declared at [models/approval.py:34](autobot-backend/models/approval.py#L34) and in the LLC migration enum, and no production code assigns it (`grep -rn 'EXPIRED\|"expired"'` over `autobot-backend/**.py` finds writers only in SSO sessions, knowledge freshness and the secrets audit). That is #17289 exactly, so this is a **second witness raising its priority, not a second issue** — and #14068 covers the "nobody is at the screen" half. |

### A3 — "Namespace fields are absent from the tool input" as an asserted invariant `adopt` · moderate

**The idea:** their memory tool derives its namespace from authenticated owner + workflow + node, and
the RFC states that the namespace fields **are absent from `ToolInput`**. The model cannot name a
namespace because there is no field to name one in.

**Audit — we already hold the rule, in one module, as a comment.**
[llc/agent_tools.py:232](autobot-backend/llc/agent_tools.py#L232) says it outright: *"company_id and
user_id come from the authenticated chat context — NEVER from LLM params (audit/tenant integrity,
#11501 review)"*, enforced at [tool_handler.py:2670-2673](autobot-backend/chat_workflow/tool_handler.py#L2670-L2673),
and `CREATE_TASK_SCHEMA` ([:30](autobot-backend/llc/agent_tools.py#L30)) exposes only
title/description/type/priority. The KB MCP schema is likewise clean
([knowledge_mcp.py:112](autobot-backend/api/knowledge_mcp.py#L112)).

It is not applied everywhere. The thinking-MCP tools expose `session_id` as a model-filled schema
field defaulting to `"default"` ([sequential_thinking_mcp.py:116](autobot-backend/api/sequential_thinking_mcp.py#L116),
same shape at [structured_thinking_mcp.py:206](autobot-backend/api/structured_thinking_mcp.py#L206)),
resolved by `get_session_key()` = `self.session_id or "default"`
([schemas_system.py:3034-3036](autobot-backend/api/schemas_system.py#L3034-L3036)) and keyed straight
into a process-global dict ([:54](autobot-backend/api/sequential_thinking_mcp.py#L54),
[:190](autobot-backend/api/sequential_thinking_mcp.py#L190)) with **no caller-derived component**.
*Scoped honestly:* that router carries `dependencies=[Depends(check_admin_permission)]`
([:48-51](autobot-backend/api/sequential_thinking_mcp.py#L48-L51)) and the dict access takes a lock,
so this is reasoning-session bleed between admin-initiated callers, **not** a cross-tenant hole.
Separately, the agent KB/RAG tool carries no caller identity at all
([agentic_search.py:438](autobot-backend/knowledge/search_components/agentic_search.py#L438)) while
the memory storage layer makes `user_id` keyword-only-required
([memory/manager.py:405](autobot-backend/memory/manager.py#L405)).

**Not a new issue — an instance of a filed class.** #16968 ("the sentiment agent reads and writes any
session's working memory named in the request context") is the same defect class, with #13228 (MCP
calls bypass canonical RBAC) adjacent. Per one-defect-one-fix these are **witnesses that raise
#16968's priority**, listed there.

**What is genuinely new and worth adopting is the enforcement shape:** promote the
`agent_tools.py:232` comment to a repo guard that walks every agent-facing tool schema and fails on a
`user_id` / `session_id` / `company_id` / `namespace` / `collection` property. Visible benefit: the
rule stops depending on whoever reads that one docstring. Hidden cost: one guard plus an explicit
allow-list for the legitimate cases, which is the cheap half of the work — the expensive half is
already tracked in #16968.

### A4 — A rendered per-teammate capability line `adopt` · moderate

**The idea:** each teammate is compiled into one system-prompt line — `- <id>: <label> (<type>) -
tools: …; skills: …` — assembled from the teammate's own tool and skill edges. Their docs give the
reason: the long per-delegate descriptions are hidden from the lead, so without the line a teammate
labelled "Web Agent" holding a scraping toolkit is indistinguishable from one holding nothing.

**Audit — PARTIAL.** AutoBot injects *"Available agents and their capabilities: {capabilities_json}"*
([orchestrator_prompts.py:23](autobot-backend/orchestration/orchestrator_prompts.py#L23)), but that
JSON is `{agent: [cap.value]}` over the 14-member `AgentCapability` enum
([orchestrator.py:742](autobot-backend/orchestrator.py#L742),
[orchestration/types.py:61](autobot-backend/orchestration/types.py#L61)) — abstract capability
labels, no tools, no skills, no model. The `delegate` tool advertises only `task`/`reason`/
`wait_for_result` ([tools/delegate_tool.py:52](autobot-backend/tools/delegate_tool.py#L52)) and
`get_direct_reports` returns agent_id/name/org_role/title
([agent_org_service.py:194](autobot-backend/services/agent_org_service.py#L194)). So the lead plans
against role names, not against what each report can actually execute. No existing issue (searched
`teammate capability roster`).

**Visible benefit:** better delegation targeting and fewer bounced tasks — the lead stops assigning
browser work to a report with no browser tool. **Hidden cost:** prompt length grows with team size,
and the line must be *derived* from the live tool/skill wiring or it becomes a third definition of an
agent's capabilities — which is exactly the drift #13594 already tracks ("capability profiles are
Python literals while model config is runtime data — one agent, two definitions"). Condition: build
it as a renderer over the existing registry + org graph, never as a new stored field.

### A5 — Hide a capability from the UI without making it unresolvable `adopt-with-conditions` · moderate

**The idea:** one config with five lists (nodes, groups, credential categories, skill folders, plus a
positive list for the plain-language build flow) that removes a capability's *UI affordance* while the
backend registry still resolves it — because deleting the plugin breaks every saved graph that
references it. Two tiers: absolute blocklists that always win, and a positive list that governs only
what the guided flow may assemble.

**Audit — PARTIAL, and the gap is the interesting half.** AutoBot's only hide mechanism is the
build-time `featureFlag` on the hardcoded nav array
([navItems.ts:40](autobot-frontend/src/config/navItems.ts#L40), filtered at
[:62](autobot-frontend/src/config/navItems.ts#L62), applied in
[App.vue:1021](autobot-frontend/src/App.vue#L1021)) — and its own comment scopes it correctly as *"a
UX visibility toggle only — never a security boundary"*. It gates **nav routes, not a capability
catalogue**. The subsystem flags ([feature_flags.py:55](autobot_shared/feature_flags.py#L55)) gate
backend *execution*, and the DB/Redis flag API ([api/feature_flags.py:87](autobot-backend/api/feature_flags.py#L87))
switches endpoint enforcement mode. Crucially, our nearest analogue does the opposite of theirs: a
disabled skill is **refused at execute time** ([skills/manager.py:98-105](autobot-backend/skills/manager.py#L98-L105)
returns `"Skill 'X' is disabled"`), i.e. disabling removes resolvability — the exact failure their
design exists to avoid. `LLCCompanyTool` has no hidden/archived column
([llc/models/company_tool.py:53](autobot-backend/llc/models/company_tool.py#L53)). No existing issue
(searched `hide capability without disabling`).

**Why this one matters beyond the UI:** it is the missing mechanism behind two standing house rules —
*never delete code, wire it in* and *"cleanup" means finishing the work*. Retiring a capability today
has only two settings, shipped or deleted, so the safe option is to leave it visible forever.
**Visible benefit:** a capability can be withdrawn from the catalogue while existing references keep
loading. **Hidden cost:** a third visibility plane next to nav flags and subsystem flags — and a
fourth would be a canonicality violation. Condition: it must **replace** the nav-flag array's role
for capability catalogues rather than sit beside it, and the config must be one file with the
`store_authority`-style "declared in code, reachable from the call site" property.

## What We Already Do Better (continued)

### Runtime self-extension is refused by design, and the refusal is enforced at the right layer

Their headline demo — an agent adding its own tools mid-task — has no AutoBot equivalent, and that is
the correct outcome under the house rule that no agent mutates durable state on its own. It is
*enforced*, not merely absent: the agent-facing LLC tool set is exactly
`{create_task, update_goal, request_approval, record_decision}`
([llc/agent_tools.py:91](autobot-backend/llc/agent_tools.py#L91)); attaching a tool to a role requires
`require_company_admin` ([llc/services/role_tool.py:96](autobot-backend/llc/services/role_tool.py#L96))
with the actor taken from `Depends(get_current_user)` and never a payload
([llc/api/roles.py:497](autobot-backend/llc/api/roles.py#L497)); agent enable/disable and model changes
sit behind `require_settings_admin` ([api/agent_config.py:1153](autobot-backend/api/agent_config.py#L1153));
and hiring is an authenticated org action ([llc/api/agent_hires.py:431](autobot-backend/llc/api/agent_hires.py#L431))
that an agent can only *request* via `request_approval(gate_type="hire")`, which a human must approve
([llc/services/approval.py:229](autobot-backend/llc/services/approval.py#L229)).

The one pattern worth lifting from their implementation is **not** the capability but its honesty
note: tools bind at the start of a turn, so every mutation result ends with *"Available on your next
turn"* to stop the model looping on a tool that does not exist yet. That is a cheap rule for any
AutoBot tool whose effect is deferred.

### Delegation bounds are already there

Their validation rejects cycles and depth beyond two child layers; so does ours —
`depth >= MAX_DELEGATION_DEPTH` raises before any engine runs
([chat_workflow/delegation.py:245](autobot-backend/chat_workflow/delegation.py#L245)), unbounded agent
ids are refused ([:252](autobot-backend/chat_workflow/delegation.py#L252)), and org-graph cycles are
rejected at write time ([agent_org_service.py:274](autobot-backend/services/agent_org_service.py#L274),
[llc/services/reporting_line.py:389](autobot-backend/llc/services/reporting_line.py#L389)).

## Gaps & Opportunities, prioritised

| Priority | Item | Why now |
|---|---|---|
| 1 | **A1 — active-token pressure metric** | A live user-visible wrong number plus repeated paid compaction; the correct convention already exists in the same file. Trivial fix. |
| 2 | **A3 — guard that no agent-facing tool schema carries a namespace field** | The rule is already written in one docstring; the guard is what makes it hold. The expensive half is tracked in #16968. |
| 3 | **A5 — hide-without-disable capability config** | The missing mechanism behind two standing house rules; today "retire" means "delete", so nothing is ever retired. |
| 4 | **A4 — rendered per-teammate capability line** | Directly improves delegation quality; must be derived, not stored, or it feeds #13594's drift. |
| 5 | **A2 — compaction activation CAS** | Real race, but A1 shrinks its window by ~an order of magnitude. Re-measure after A1. |
| — | **Frontend type duplication** (out of scope here, worth noting) | A headless backend tool needs no frontend edit (registry-served catalogue: [tool_registry_ref.py:103](autobot-backend/llc/services/tool_registry_ref.py#L103) → [llc/api/tools.py:77](autobot-backend/llc/api/tools.py#L77) → [RolesView.vue:549](autobot-frontend/src/views/llc/RolesView.vue#L549)), but a plugin with UI, a workflow node/step type, or a credential category each require editing a hardcoded frontend array ([plugins/registry.ts:45](autobot-frontend/src/plugins/registry.ts#L45), [useWorkflowBuilder.ts:259](autobot-frontend/src/composables/useWorkflowBuilder.ts#L259) duplicating [vision_step_handler.py:38](autobot-backend/services/workflow_automation/vision_step_handler.py#L38), [SecretsManager.vue:894](autobot-frontend/src/components/security/SecretsManager.vue#L894)), and no guard asserts the frontend holds no copies of backend type lists. |

## Specific Code/Files Affected

| File | Change |
|---|---|
| [context_overflow.py](autobot-backend/chat_history/context_overflow.py) | `SessionTokenTracker`: keep the cumulative `prompt_tokens`/`completion_tokens`/`message_count` fields as *spend*, add an `active_tokens` field written with `HSET` from the latest turn, and compute `fill_percentage` from it. One hash, four fields today — the shape is already there. |
| [overflow_integration.py](autobot-backend/chat_history/overflow_integration.py) | Pass the latest turn's usage as the active value rather than an increment. |
| new repo guard under `repo_tests/` | Walk every agent-facing tool schema (LLC tools, MCP bridges, `tools/tool_registry.py`) and fail on a namespace-shaped property, with an explicit allow-list. |
| [sequential_thinking_mcp.py](autobot-backend/api/sequential_thinking_mcp.py) · [structured_thinking_mcp.py](autobot-backend/api/structured_thinking_mcp.py) | Derive the session key from the authenticated caller and drop `session_id` from the input schema — as an instance under #16968, not a separate fix. |
| [orchestrator.py](autobot-backend/orchestrator.py) · [orchestrator_prompts.py](autobot-backend/orchestration/orchestrator_prompts.py) | Render the capability block from live tool/skill wiring per report instead of `{agent: [cap.value]}`. |
| new capability-visibility config + [navItems.ts](autobot-frontend/src/config/navItems.ts) · [skills/manager.py](autobot-backend/skills/manager.py) | One hide-without-disable config; `skills/manager.py` gains a *hidden* state distinct from *disabled*. |

## Cross-reference against the open backlog

Searched `--state open` on: context window compaction · token budget estimate · chat history trim ·
context overflow · tool schema tenant scoping · agent tool authorization · working memory session
ownership · MCP bridge RBAC · feature flag visibility · retire a capability · disabled skill ·
unwired feature palette · capability catalogue · `context_overflow`.

| Finding | Already filed? | Existing issues it belongs to / sits beside |
|---|---|---|
| **A1** active-token pressure | **No** — new | **Home: #16108** (umbrella: *self-correction, compaction-fidelity and **measurement** gaps from a comparative audit* — identical provenance, and its charter is already "every adoptable item is a design decision restated in AutoBot's own stack"). **Sibling operand: #14029** — context windows come from a static catalog with a 4096 fallback. #14029 is the *denominator* of `fill_percentage`, A1 is the *numerator*: one formula, both operands wrong, and neither is visible while the other is broken. **Probable downstream symptom: #14393** — "a user instruction erodes across repeated compactions" is exactly what an over-firing trigger produces, so A1 may be a root-cause amplifier rather than a neighbour. Adjacent plane: #13685, #16617. |
| **A2** compaction activation CAS | **No** — new | Same file as A1; no existing issue (searched `concurrent compaction`, `summarization race session`). |
| **A3** namespace-absent-from-schema | **Instance already filed; the guard is new** | Instance → **#16968** (same class: a model/request-named session namespace). Mechanism that would fix it → **#16473** (thread company/holder/session identity through the MCP tool-dispatch gate). Authorization context: #13228 (three parallel authz models), #13227 (MCP governance umbrella), #15781 (Principal has no agent identity), #17662. The new part — a guard asserting no agent-facing schema carries a namespace property — belongs under **#13587** (*agent-seam governance is name-scoped, and the best guards are not on the production path*) and **must ship a positive control**, because #15826 found 79 of 133 tree-scanning guards can report clean having examined nothing. |
| **A4** per-teammate capability line | **No** — new | Direct sibling: **#15271** (*capability descriptors state what a tool is, never how far it may go — no bounds and no risk grade reach the model*). Same surface, adjacent content: #15271 is what reaches the model about a *tool*, A4 is what reaches the *lead* about a *teammate*. Constraint: **#13594** (capability profiles are Python literals while model config is runtime data) is the drift this must not feed — render from live wiring, never store a third definition. Context: #16946, #16841. |
| **A5** hide-without-disable | **No** — new, and no existing home | Nearest relative is the inverse defect: **#14406** (11 declared skill triggers have no dispatcher — the manifest advertises a capability that cannot fire). Taxonomy overlap with **#17693** (a check that measures nothing vs a declaration nobody calls). This one needs an owner ruling before implementation, because it adds a third visibility plane beside nav flags and subsystem flags. |
| `ApprovalStatus.EXPIRED` never assigned | **Yes — #17289** | Exact match. Umbrella fit: **#17217** (*declared controls that do not execute — the regulated-readiness gap*), which is this finding's shape verbatim. Other half: #14068 (an approval can only be answered at the screen). **Witness comment, not a new issue.** |
| Frontend holds copies of backend type lists | **Partly — #17571** | #17571 (critical: the canonical harness holds one warn-level smoke rule) is where a "frontend holds no copies of backend type lists" rule would live. Out of this study's scope; noted only. |

### Delivery consequence — one PR, one agent

**A1, A2, #16624 and #14393 all land in `autobot-backend/chat_history/context_overflow.py`:**

- A1 → `SessionTokenTracker.add_message_tokens` / `check_and_protect` ([:108](autobot-backend/chat_history/context_overflow.py#L108), [:690](autobot-backend/chat_history/context_overflow.py#L690))
- A2 → the activation path in `_create_summary` ([:806](autobot-backend/chat_history/context_overflow.py#L806))
- #16624 → `_TOOL_RESULT_CLIP_CHARS = env_int(..., 400)` at [:51](autobot-backend/chat_history/context_overflow.py#L51), applied at [:323-333](autobot-backend/chat_history/context_overflow.py#L323-L333)
- #14393 → `_PRESERVED_USER_MESSAGE_CAP` at [:46](autobot-backend/chat_history/context_overflow.py#L46), used by `_compose_summary` at [:428](autobot-backend/chat_history/context_overflow.py#L428)

Under the same-file rule that is **one PR owned by one agent**, not four. The path is currently clear:
`gh pr list --state open --json files` shows **no open PR touching `chat_history/`**.

## Filed

| Finding | Issue | Parent umbrella | Milestone | Edges |
|---|---|---|---|---|
| A1 active-token pressure | **#17802** `bug` `priority: high` | #16108 | v0.10.0 | blocks #17805 |
| A2 compaction activation CAS | **#17805** `bug` `priority: low` | #16108 | v0.10.0 | `blocked_by` #17802 |
| A3 namespace-absent guard | **#17806** `testing` `security` | #13587 | v0.10.0 | witness on #16968; needs a positive control per #15826 |
| A4 per-teammate capability line | **#17807** `enhancement` | #13587 | v0.10.0 | sibling of #15271; constrained by #13594 |
| A5 hide-without-disable | **#17808** `needs-decision` `architecture` | — (owner ruling first) | v0.9-decisions | relates #14406, #17693 |

Witness comments, no new issues: **#17289** (`ApprovalStatus.EXPIRED` declared and never assigned —
plus a note that it fits #17217's umbrella and carries no milestone) and **#16968** (the thinking-MCP
namespace instance, scoped as admin-gated rather than cross-tenant).

Cross-link comments posted on **#14029** (the other operand of the same fraction), **#14393** and
**#16624** (same-file batching with #17802/#17805), and **#15271** (sibling surface of #17807).

**Two backlog observations that fell out of the cross-reference, not from the source:**

1. #16968 (`priority: high`, security) and #17289 both carry **no milestone**, so neither is visible to
   release triage. Flagged in their comments; assigning a milestone is a scope call.
2. The four same-file issues sit in **three different milestones** (v0.10.0, v0.11.0, v0.14.0). The
   same-file rule and the milestone split pull against each other: batching them means landing all four
   at the earliest milestone, and not batching them means opening `context_overflow.py` three times.
   Recorded rather than resolved — it is a scope decision.
