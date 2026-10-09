# Research: Coding-agent bot roster — host, delegation, groups and memory

**Source:** the reference work — an open-source (Apache-2.0) personal host that wraps locally
installed coding agents as persistent, named "bots" reachable from phone, desktop and terminal.
**Status:** Phase 1 and Phase 2 complete (2026-10-09). Findings filed as #18134 (delegation cap and engine timeout), #18135 (client correlation id), #18136 (a2a task recovery), #18137 and #18138 (memory batching and profile cap), plus a comment on #16836 for the prompt-cache prefix instance in `chat_workflow/llm_handler.py`.
**Related:** [agent-host-and-agent-client-protocols.md](agent-host-and-agent-client-protocols.md)
(the ACP protocol layer this work builds on).

---

## Source Analysis: a multi-agent "bot roster" host over ACP

### What It Is

A single Rust host binary runs on the user's computer, speaks the Agent Client Protocol (ACP, over
stdio) to any installed coding harness (~40 from the public ACP registry, auto-detected or fetched on
first use), and exposes each configured agent as a persistent *bot*: name, avatar, standing
instructions, agent backend, project folder, permission policy. Clients — native iOS, an Electron
desktop app, and a terminal UI — are thin mirrors of host state. Remote access goes through an
end-to-end encrypted channel relayed by a serverless edge worker; push notifications are sealed to
the phone's key. Maturity: single-author, ~7 months old, ~180 stars, very active (pushed today),
shipping signed releases on four platforms plus an App Store app. Docs are thorough but partly in
Chinese (the relay protocol spec).

### Architecture & Key Patterns

- **Host-authoritative monolith + thin clients.** `hub.rs` coordinates actors and event publication;
  `store/` (SQLite) persists every mutation with a **global monotonic `rev`**. Clients sync with
  `since: rev`, then follow SSE/channel events; duplicate sends are deduped by `clientNonce`.
  No client routes messages, parses mentions or counts replies — all logic is host-side.
- **One actor per bot** (`agent/bot/`): serializes that bot's turns, owns its ACP process; main chat
  and each reply thread are distinct ACP sessions ("lanes" = `(chat, thread)`).
- **Built-in MCP servers injected into every agent** via an authenticated local MCP→HTTP bridge
  (`mcp.rs`): `team` (bot-to-bot), `memory` (history search), `routines` (scheduling/webhooks).
  Product features are delivered *as tools to the agent*, not as host-side orchestration.
- **Transport split:** loopback HTTP+SSE with a bearer token for local/SSH clients; per-(device,host)
  E2E keys for phones, direct-connection race (1.5 s) before falling back to the relay; offline
  encrypted mailbox in a per-computer durable object; host-signed ACL is authoritative.
- **Mutual minimum versions** (`minApp` / `minHost`) for client/host compatibility, separate from the
  wire version.

### Notable Implementation Details

- **Bot-to-bot delegation as MCP tools** (`chat/team.rs`, `chat/team/requests.rs`):
  `list_bots`, `ask_bot` (synchronous, waits for the recipient's final reply), `message_bot`
  (fire-and-forget). Admission control rejects self-delegation, duplicate outstanding requests to
  the same recipient, and **direct or indirect wait cycles (a wait-for graph, including queued
  requests)**. Host-wide cap 64 outstanding, 16 per sender; **chain hop limit of 8** carried into
  the recipient's turn so A→B→A ping-pong is bounded; resets only on a new user turn. 10-minute
  ask timeout including queue and approval time; failure is a tool error, never a fabricated reply;
  no auto-retry. Only the request text crosses — never the requester's transcript. Delegated
  requests are excluded from the user-fact memory keeper. Pending requests become "interrupted"
  errors after host restart rather than being replayed.
- **Group chats as "room turns"** (`chat/group.rs`): the group has no harness of its own; a user
  message starts up to 3 rounds / 10 replies; responders are the @-mentioned members (or all),
  one at a time with rotating start; a member may reply `(pass)`; a silent round ends the turn; a
  new message or Stop preempts before the next speaker. Each member runs in its *own main
  session*, given a framed delta ("what was said since you last spoke here").
- **Threads fork sessions** (`session/fork` where the harness supports it, else a fresh session
  seeded with the root and preceding lines); nothing in a thread leaks into the main session.
- **Prompt-cache-stable instruction snapshot** (`chat/context.rs`): the system instructions are
  rendered once and stored keyed by *(session, compaction epoch)*, so the prompt stays
  byte-identical and the provider prompt cache stays warm. The host advertises a compaction
  capability; each completed compaction (deduped by id) bumps the epoch and triggers one
  re-render. Mid-session profile edits are sent once as an appended update block and folded into
  the snapshot at the next compaction.
- **Batched, deferred memory keeper** (`chat/memory/`): memorable exchanges (not "thanks/ok") are
  queued persistently; extraction runs after 5 min of quiet or 8 queued exchanges, using a
  one-shot, tool-less, cheapest-model agent. Facts are plain markdown (`profile.md` capped at 100,
  consolidated to 60 with dropped facts moved to a monthly log — nothing lost); newest 30 log lines
  within 4,000 chars go into the prompt. Periodic one-line "episode" journal entries; automatic
  bot naming from the first exchanges. A `search_history` substring tool covers what the keeper
  did not record.
- **Crash-resumable turns:** `turn.inflight.<bot>` records the running turn; after a restart the
  session is resumed with a hidden "you were interrupted, don't repeat finished steps" prompt,
  unless the turn is over an hour old.
- **Message folding:** user messages sent while a bot works are folded into one next turn; bot
  requests occupy separate turns and act as fold boundaries.
- **Test discipline:** an end-to-end test spins up a real host and MCP subprocess with *scripted
  ACP agents* (no paid provider calls) covering discovery → delegation → approval → reply → sync;
  cross-language crypto test vectors for the relay.

### Strengths

- Every limit in the delegation system is explicit, numeric and documented (caps, hop limit, timeout,
  cycle rejection, restart semantics) — the failure modes are designed, not discovered.
- "Features as MCP tools" keeps the host thin and harness-agnostic; any ACP agent gains delegation,
  memory and routines with no per-harness work.
- Prompt-cache awareness (frozen snapshot, epoch-keyed re-render) is a real cost lever few hosts
  bother with.
- Clear ownership table (what lives where, who is the system of record) and an honest note that
  "E2E encrypted" does not hide metadata.
- Deterministic, provider-free integration tests for multi-agent flows.

### Weaknesses / Limitations

- Single-user, single-computer focus by the author's own statement; no RBAC, no multi-tenant model.
- No task scheduler or isolated worktrees for delegated work — bots sharing a folder can clobber each
  other; the docs push that onto the user ("give bots explicit file ownership").
- Non-Claude harnesses get degraded context handling (no system-prompt channel, no compaction
  signal → instructions only refresh on new session).
- Memory is per-bot only; no shared user memory or project memory; history search uses plain
  substring matching, no semantic retrieval; group chats are not searchable from a member's history.
- Delegated work is never replayed after restart — correct, but leaves partial changes for the user
  to inspect.
- Bus factor of one; heavy surface (iOS + Electron + TUI + Rust host + two edge workers) for a solo
  maintainer.

### Visible vs Hidden Metrics

- **Visible (self-reported):** "40+ agents", free / no paid tier, E2E encrypted relay, four
  platforms, ~180 stars. None independently verified here; the agent count is the public ACP
  registry's size, not tested integrations.
- **Hidden:** the relay depends on a hosted edge account the author operates (availability and trust
  assumptions sit with one person); ACP adapter quality varies per harness and is outside the
  host's control; the delegation system's correctness rests on wait-graph and cap logic that must be
  kept in step with queue semantics; per-platform native code (screen helpers, speech) multiplies
  maintenance.
- **Weighing:** for a single developer driving local coding agents from a phone, the visible wins
  hold. As a *pattern source* the value is in the small, well-bounded mechanisms (delegation
  admission control, room-turn protocol, cache-stable instruction snapshots, batched memory
  keeper, rev-based sync) — not the product, whose transport and client surface would be pure
  hidden cost to adopt.

---

## AutoBot Comparison: the reference work → AutoBot

Audit scope: `autobot-backend/` and `autobot-frontend/src` on `main`, 2026-10-09. Paths are relative
to `autobot-backend/` unless prefixed.

### What We Can Adopt

| # | Pattern | Already-exists audit | Visible benefit | Hidden cost | Verdict | Effort |
|---|---|---|---|---|---|---|
| A1 | **Delegation admission control** — wait-for-graph cycle rejection, self-delegation rejection, tree-wide (not per-run) caps, a wait timeout on the `internal` engine | `chat_workflow/delegation.py:68-72` has `DELEGATION_ENABLED` (default off), `MAX_DELEGATION_DEPTH=2`, `MAX_DELEGATIONS_PER_TURN=5`; the per-turn counter lives in each run's own context, so a child resets it (cap is per run, not per tree). Searched `delegation.py`, `tool_handler.py`, `agents/hierarchical_agent.py` for cycle/visited/wait-for and self-target checks — none. `internal` engine has no wait timeout; `claude_code` uses `timeout_seconds or 600` (`services/execution/claude_code_backend.py:481`) | Bounded fan-out and no runaway trees before delegation is switched on | Small: a counter carried through the delegation context plus a timeout. A full wait-graph only matters once delegation targets *named peers*; depth-only recursion cannot cycle by identity | **Adopt-with-conditions** — tree-wide budget + `internal` timeout now (prerequisite to enabling the flag); wait-graph only if named-agent delegation lands | Moderate |
| A2 | **Prompt-cache-stable system prompt** — dynamic memory content placed *after* the static instructions, re-rendered only on a defined epoch | Anthropic `cache_control` on the system block exists (`llm_shared/providers/anthropic.py:253-267`); `prompt_manager.py:1274-1330` already does static-prefix/dynamic-suffix for vLLM. But the main chat path **prepends** dynamic context: `chat_workflow/llm_handler.py:922` (`tiered_ctx + system_prompt`) and `:929` (`story + system_prompt`) — any new fact invalidates the whole cached prefix | Cache hits on every chat turn; lower latency and token cost | Low: reorder at the existing call site; follow the existing `get_optimized_prompt` rule rather than adding a second mechanism | **Adopt** — fix the ordering at the one call site; compaction-epoch re-render is optional follow-up | Trivial–moderate |
| A3 | **Batched, filtered memory extraction** — queue exchanges, extract after N exchanges or a quiet window, skip trivial acknowledgements, cheapest-tier model | `chat_workflow/stop_hook.py:28-75` queues extraction after **every** turn; no trivial-message filter; model from SSOT `knowledge_extraction` agent config. The task itself is broken: `tasks/memory_tasks.py:69` calls `extract_facts_from_messages`, which no class defines — **already filed as #18075** (this audit is a second witness, not a new issue) | Fewer LLM calls; extraction sees several exchanges of context at once | Debounce state must survive restart (Redis); quiet-window timing adds latency to fact availability | **Adopt after #18075** — batching is pointless on a path that does not run | Moderate |
| A4 | **Fact-profile cap with consolidation to a log, never delete** | `knowledge/facts.py:1570-1665` `consolidate_facts` only deletes, off unless `AUTOBOT_FACTS_PRUNE_EPOCH` set, dry-run default; no profile size cap; no dropped-fact log (searched fact_log / dropped_facts) | Bounded prompt size, no information loss | Must respect the no-agent-deletes-data rule (#17038): a move-to-log still rewrites stored data, so it goes through the approval gate | **Adopt-with-conditions** — route through the #17038 review queue | Moderate |
| A5 | **Client nonce dedup on chat send** | `IdempotencyMiddleware` exists and is opt-in by `Idempotency-Key` (`middleware/idempotency_middleware.py:43`, wired `initialization/middleware.py:120-137`); `autobot-frontend/src` never sends the header; `useChatStore.ts:210-221,285-298` matches echoes by (sender, content) and its own comment names a client correlation id as the complete fix | Retries and reconnects cannot double-send; echo matching stops depending on content equality | Very low — the server half exists; this wires the client | **Adopt** (wire-in of an existing feature) | Trivial |
| A6 | **Turn queue per session with folding** of messages sent while busy | `chat_workflow/manager.py:313` global lock, `:318` busy counter only; no per-session queue or fold (searched session_lock, turn_queue, pending_messages) | Ordered turns; messages typed while busy become one next turn | Touches the core streaming path; needs a clear UX for queued input | **Adopt-with-conditions** — needs a design decision on busy-time UX first | Significant |
| A7 | **Crash recovery for in-flight chat turns** (mark interrupted, or resume with a "don't repeat finished steps" hint if young) | LLC runs already do this (`llc/scheduler/session_checkpointer.py:112`, called from `initialization/lifespan.py:1865`). Main chat: LangGraph checkpointer resumes only after an approval pause (`manager.py:3910`); no startup sweep. A2A tasks in WORKING stay until TTL (`a2a/task_manager.py:173-183`) | Users see "interrupted" instead of a spinner that never ends | Low for mark-interrupted; resume-with-hint carries replay risk for side-effecting tools | **Adopt mark-interrupted** for chat and A2A, reusing the LLC pattern; reject auto-resume | Moderate |
| A8 | **Scripted-agent integration test for a delegation chain** | Unit tests with fakes exist (`chat_workflow/delegation_test.py:100,248,267`); `agents/multi_agent_workflow_validation_test.py` needs a live backend; no A→B chain or cycle test with scripted agents | Regression net for A1 before the flag is enabled | Low | **Adopt** together with A1 | Moderate |

### What We Already Do Better

- **Reconnect catch-up:** `events/channel_stream.py:195-239` `replay_since` with an explicit gap/resync signal, and the frontend sends per-channel `last_event_id` (`services/LiveEventService.ts:85,431`; `useSessionSync.ts:163-175`) — per-channel cursors plus a snapshot rebuild on gap, which a single global `rev` does not give.
- **History search:** `memory/verbatim_store.py` has semantic (`:390`) and symbolic-plus-recency (`:310`) search, against the reference work's plain substring. The gap is exposure — it is an MCP/REST tool (`mcp_server/autobot_server.py:274,833`), not in the chat agent's own tool set.
- **Durable agent runs:** the LLC heartbeat scheduler (Redis ZSET claim, 30 s checkpoints, 6 h stall sweep, rate-limit resume from `context_snapshot`) is more robust than restart-marker-only recovery.
- **Governed delegation engines:** the `claude_code`/`internal` split with refusal of unbounded executor types (`delegation.py:251-255`) and the laundering test (`delegation_laundering_test.py`) already address privilege escalation through delegation, which the reference work leaves to each harness.

### Gaps & Opportunities (by impact)

1. **#18075 — fact extraction is broken** (already filed). Blocks A3/A4.
2. **A2 prompt ordering** — cheapest real cost/latency win; one call site.
3. **A5 nonce wire-in** — closes a documented double-send gap with existing server code.
4. **A1 + A8** — required before `AUTOBOT_DELEGATION_ENABLED` can safely default on.
5. **A7** — interrupted-turn marking for chat and A2A.
6. **Not adopted:** group "room turns" (no multi-agent chat product requirement in AutoBot; `api/chat_compare.py` covers parallel model comparison), chat threads/forks via session fork (no requirement found; would need a product decision), and the phone relay/E2E mailbox stack (product-specific; pure hidden cost).

### Specific Code/Files Affected

| File | Change |
|---|---|
| `chat_workflow/llm_handler.py:915-932` | Append tiered context / essential story after the static system prompt instead of prepending |
| `chat_workflow/delegation.py`, `chat_workflow/tool_handler.py:2312-2378` | Tree-wide delegation budget carried into children; wait timeout for the `internal` engine; self-target rejection if named targets are added |
| `chat_workflow/stop_hook.py`, `tasks/memory_tasks.py` | After #18075: debounce/batch extraction, trivial-message filter |
| `knowledge/facts.py:1570-1665` | Cap + move-to-log consolidation through the approval gate |
| `autobot-frontend/src/stores/useChatStore.ts`, chat send API call | Send `Idempotency-Key` per message; match echoes by key |
| `initialization/lifespan.py`, `a2a/task_manager.py` | Startup sweep marking in-flight chat turns and WORKING A2A tasks interrupted |
| `chat_workflow/delegation_test.py` (or a sibling) | Scripted multi-agent chain/cycle test |
