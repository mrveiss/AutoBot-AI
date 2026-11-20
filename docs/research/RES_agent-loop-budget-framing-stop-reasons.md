# Agent-loop budgets, untrusted-data framing and typed stop reasons

**Date:** 2026-11-19 · **Type:** technical research (anonymized) · **Baseline:** `origin/main` @ f98f24e811

## Source analysis: a self-hosted autonomous agent platform with a planner/worker loop (the reference work)

### What it is

A self-hosted, LLM-driven autonomous agent platform shipped as one compiled binary with an embedded web UI. PostgreSQL is its only external dependency, and it supports Anthropic, OpenAI-compatible and Ollama models. The inner agent loop comes from a separate harness library; the platform is the orchestration, policy and persistence layer around that loop.

Method: read-only inspection of public file contents. Nothing was cloned or run. For the agent, guard, provider-pool, recorder and evidence files only doc comments, signatures and prompt constants were read, not function bodies, so behaviour claims below are "as documented in code comments", not verified logic. Not read: the changelog, the largest tool-definition file, the database, server and web layers, the skill files.

### Architecture and key patterns

- **Three agent roles:**
  - The orchestrator is a thin chat agent that observes and steers through hints and high-priority intents.
  - The planner is the only role that creates intents. It wakes on debounced graph changes, and most wake-ups dispatch nothing.
  - A worker claims one intent, runs real tools, writes facts back and stops.
- **Dual graph:** a shared long-lived graph plus a per-task exploration graph (goal, intent, fact, finding, hint nodes; spawns, derived_from, yields, proves edges). The program computes dedup keys and parent/child links; agents submit raw observations only.
- **Fresh session per planner wake-up.** A persistent per-task todo store carries multi-step chains across rounds.
- **Editable prompt body with code-owned tails.** The operator-editable prompt lives in the database. Safety blocks are appended after rendering, so a stored override cannot drop them.
- **Everything is a decorator on the model-provider interface:** call recorder, failover pool and side-question snapshot capture.

### Notable implementation details

- **Hierarchical budgets:** task, then intent, then planner round.
  - A child's budget is `min(own, parent remaining above the wrap-up reserve)`. The reserve is the larger of 5% and a fixed token/turn floor.
  - A worker is not dispatched if the remaining budget is below its estimated cost (a rolling average of finished workers).
  - Exhaustion triggers exactly one forced wrap-up round; the first caller wins. During wrap-up only write-back tools are allowed.
  - Spend is restored from the usage ledger after a restart. Budgets are off by default.
- **Graph-level cold-node compaction:**
  - A node is hot if it is a live intent, an ancestor of one, or a direct child of one. A node must stay cold for several rounds before it is eligible.
  - Union-find groups connected cold nodes into blocks of at least two; each block is LLM-summarised into a digest node with `covers` edges.
  - A liveness recheck before commit ensures a digest never covers a revived node. Only facts and settled intents fold; findings and goals never do.
- **Projection-only tool retrieval:** BM25 over tool name, description and parameter names, queried with the goal plus the current intent. It can only remove tools, never add them; core tools are always kept. It falls back to the full list on an empty query, a small catalog or a scorer error. Off by default.
- **Untrusted-data defence, three layers:**
  1. The harness frames tool results with nonce tags.
  2. Every agent- or externally-derived field is wrapped in a per-message cryptographically random nonce frame. A neutraliser rewrites the marker stem inside the data, so content cannot open or close a frame. Operator-authored content stays outside.
  3. Code-owned prompt tails tell the agent to quote the payload as evidence, record it as a possible injection, and never act on instructions the data contains. The compactor gets the same rule.

  A code comment admits the framing is advisory: it cannot stop a model from following the text.
- **Failover pool:** an ordered chain with a process-wide circuit breaker.
  - Cooldowns escalate 1 min, 5 min, 30 min and persist across restarts.
  - Deterministic failures (no credit, bad key) trip the breaker immediately; transient ones trip it after 3.
  - A member may only be abandoned before it yields any event. Mid-stream failures go to the harness's resume logic (no mid-stream switch).
  - Members whose context window cannot hold the request are skipped.
- **Typed stop reasons:** the harness reports a provider refusal as an ordinary completion. A stop sink in the call recorder distinguishes `refusal` and `content_filter` from a real end of turn, and the cancellation cause is preserved.
- **Evidence content-addressing:** bodies are content-addressed and hash-verified, kept apart from disposable traffic. A write is durable before it becomes visible; unreferenced blobs are garbage-collected after 24 h. A finding counts as verified only with a bound response and a verbatim-quote check.
- **Coverage gaps:** during wrap-up, unexamined classes surface as explicit gaps so they do not read as clean.
- **Side questions:** an immutable snapshot of the agent's context answers a side question with one provider call, no tools and no effect on the main transcript. Limits: one per parent session, four per process, 120 s timeout.

### Strengths

- Pure algorithm files (cold-node selection, tool retrieval, budget) have no database or LLM dependencies; the repo has a large test suite.
- Comments are candid about limits.
- Safety prompt text cannot be removed by prompt edits, and tool retrieval cannot widen permissions.
- State survives restarts: budgets, breaker cooldowns and side-question snapshots.

### Weaknesses / limitations

- The core loop lives in a separate single-author harness, so it cannot be audited from the platform repo.
- The prompt-injection defence is advisory to the model; externally-derived content is not hard-isolated.
- Budgets and tool retrieval default to off.
- Some files are very large (one over 100 KB, two over 40 KB).
- Its licence restricts code reuse, so only ideas are reusable.

### Visible vs hidden metrics

- **Visible (self-reported, unverified):** verified-finding semantics and encrypted-at-rest storage. No benchmark results were seen.
- **Hidden:** CI health, task success rate, false-positive rate and token cost per task are not published; the core loop depends on an external harness.
- **Weighing:** the engineering signals (tests, candid comments, restart handling) are better evidence than popularity. Treat the design ideas as worth studying.

### Suspected injected text

None was found in the files read. The only injection-style phrases are the project's own defensive prompt and test fixtures. Files listed as not read were not checked.

## AutoBot comparison

**Scope (owner, 2026-11-19):** only the general agent-loop ideas, built in AutoBot's own way. No code is reused. Domain-specific features of the reference work are out of scope.

**Audit result:** 0 of 7 patterns exist in full, 5 exist in part, 2 are absent. Paths are relative to the AutoBot repo root, read from `origin/main`.

### What we can adopt

| # | Pattern | AutoBot today | Missing piece | Visible win / hidden cost | Verdict | Effort |
|---|---|---|---|---|---|---|
| 1 | Nested budgets with a wrap-up round | Flat budget checks only: `autobot-backend/llm_shared/token_budget.py:149` `TokenBudgetGate` (off by default), `autobot-backend/services/chat_budget_gate.py:171`, `autobot-backend/services/budget_policy.py:228`, `autobot-backend/llc/scheduler/dispatch_gate.py`; caps at `autobot-backend/agent_loop/loop.py:998` and `autobot-backend/chat_workflow/delegation.py:72`. #18134 (open): the per-turn cap resets in every child. | Child budget = min(own, parent remaining minus a reserve); one forced round where only persist tools run | Work is no longer lost at the cap, and #18134 gets fixed / a 4th budget mechanism, unless we extend `TokenBudgetGate` | Adopt with conditions: extend the existing gate; skip the rolling-average dispatch check until delegation is enabled | moderate |
| 3 | Provider failover deltas | Mostly there: `autobot-backend/llm_shared/fallback_chain.py`, `autobot-backend/llm_shared/failover_policy.py:46-116`, `autobot-backend/llm_shared/provider_degradation.py`, `autobot-backend/chat_workflow/llm_failover.py` (no failover once text has been emitted). The hop filter `_next_usable_hop` (`autobot-backend/llm_shared/model_fallback_coordinator.py:365`) has no size check. The window table is `autobot-backend/context_window_lookup.py:20` `known_context_window_tokens` (`autobot-backend/context_window_lookup.py`). | (a) skip providers whose context window can't fit the request; (b) escalating cooldowns; (c) breaker state that survives restarts | Avoids hops that are certain to fail / small | Adopt: (a) as its own change (#21864); (b) and (c) inside #20380. Do not build mid-stream resume | trivial–moderate |
| 4 | Random-nonce untrusted-data frames | `autobot_shared/prompt_rules.py:85` `frame_untrusted_block` uses a static marker; `:71` neutraliser; about a dozen non-test call sites. #16364 (open): lookalike-bracket bypass | Per-message `secrets` nonce in the frame marker; audit that the safety tail is code-owned on every path | A forged marker becomes impossible, closing the bypass class instead of chasing spellings / about a dozen call sites and golden-string tests change; a nonce in a cached prefix breaks prompt caching, so frames must stay in the uncached tail | Adopt | moderate |
| 5 | Typed stop reasons | `autobot-backend/llm_shared/models.py:131` `finish_reason` is set by providers (`autobot-backend/llm_shared/providers/anthropic.py:431`) but only the compat APIs read it; agent loops ignore it. `autobot-backend/modern_ai_integration.py:44,112,1122` also reads it with its own `_ERROR_FINISH_REASONS` (out of scope for #21865). | Shared enum (end_turn / refusal / content_filter / length / tool_use / cancelled); each loop branches on refusal and length | A refused or empty turn stops looking like success / mapping strings across about 6 provider adapters | Adopt | trivial–moderate |
| 7 | Retrieval-based tool narrowing | Already filed as #20849 (open, under #20842); BM25 exists at `autobot-backend/knowledge/search_components/bm25.py` | Add a "core tools always kept" criterion to #20849 | Smaller prompts / a retrieval miss hides a needed tool; a per-turn tool list invalidates the prompt cache | Already decided: amend #20849 only | — |

### Rejected or deferred (hidden metrics win)

- **2 · Graph-level context compaction: rejected for now.** AutoBot's context is a transcript, not a plan graph. The pattern needs a durable plan graph as the system of record, plus union-find, digest edges and a concurrency-sensitive liveness recheck. Transcript compaction still has open correctness bugs (#17805, #16624, #17802). Revisit after #19755.
- **6 · Side questions from a frozen context snapshot: deferred.** It needs a snapshot API, a new endpoint, UI and budget attribution. No issue asks for it, and the steering path (#17060) should be sound first.

### What we already do better

- **Failover:** cross-worker degradation marks shared through Redis (`provider_degradation.py`), with a non-expiring `NEEDS_REAUTH` state. The reference work's breaker registry is per process.
- **Neutraliser and prompt rules:** already centralised in one shared helper (`autobot_shared/prompt_rules.py`) used by about a dozen call sites. The reference work keeps them in its agent package.

### Specific code/files affected

- `autobot-backend/llm_shared/token_budget.py`, `autobot-backend/chat_workflow/delegation.py` (#1)
- `autobot-backend/llm_shared/failover_policy.py`, `autobot-backend/llm_shared/fallback_chain.py`, `autobot-backend/llm_shared/model_fallback_coordinator.py`, `autobot-backend/context_window_lookup.py` (#3)
- `autobot_shared/prompt_rules.py` and its callers (#4)
- `autobot-backend/llm_shared/models.py`, the provider adapters, `autobot-backend/agent_loop/loop.py`, `autobot-backend/chat_workflow/llm_handler.py` (#5)

### Not checked

The frontend beyond one grep for #6, the SLM backend, the full LLM registry and router for #3(a), and whether every tool-derived field reaching a prompt is framed for #4.

## Linked issues

- #21863 feat(budget): nested agent budgets — a child's allowance is capped by its parent's remainder, with one wrap-up round on exhaustion
- #21864 feat(llm): failover hops to models whose context window cannot hold the request — skip them before dispatch
- #21865 feat(llm): typed stop reasons — agent loops treat refusal, content filter and length cut-off as a normal end
- #16364 (comment: per-message nonce frames), #20380 (comment: breaker ladder + persistence), #20849 (comment: core tools always kept)
