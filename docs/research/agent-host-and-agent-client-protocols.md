# Research: Agent Host Protocol (AHP) & Agent Client Protocol (ACP)

**Sources**
- <https://microsoft.github.io/agent-host-protocol/> · repo `microsoft/agent-host-protocol` (MIT)
- <https://agentclientprotocol.com/get-started/introduction> · repo `zed-industries/agent-client-protocol` (Apache-2.0)
- AHP's own comparison page: `docs/guide/ahp-and-acp.md`

**Status:** Phase 1 (source analysis) complete. Phase 2 (AutoBot comparison) not started — awaiting go-ahead.

---

## Source Analysis: AHP + ACP

### What They Are

These are **two layers of the same stack, not competitors** — and AHP's own docs say so explicitly.

**ACP (Agent Client Protocol)** — created by Zed Industries (June 2025), now co-developed with
JetBrains. Apache-2.0, `v1.7.0`, ~4.0k stars / 349 forks, actively pushed. It standardizes the
**1:1 conversation between one client (editor/IDE/CLI) and one coding agent**: initialize, auth,
create session, prompt, stream updates, call tools, request permission. Its explicit model is
LSP-for-agents — "any editor to any agent, no custom glue". Adoption is the real story: JetBrains
IDEs (built in since Dec 2025), Zed 1.0's headline feature (Apr 2026), Neovim, Emacs, and a
co-launched public **ACP Registry** (Jan 2026) listing dozens of agents — Claude Code, Gemini CLI,
Codex, Copilot, Goose.

**AHP (Agent Host Protocol)** — Microsoft, created 2026-03-12, MIT, ~253 stars / 66 forks, 786
commits, protocol version `0.3.0`, reference implementation is VS Code's built-in client. It solves
a **different** problem: *N clients sharing one agent session*. A session stops being trapped in the
app that started it; IDE, web, CLI and mobile can all attach to the same live session and see the
same state.

AHP's one-line self-description: *"a portable, standalone server protocol that gives multiple
clients a synchronized view of AI agent sessions through immutable state, pure reducers, and
write-ahead reconciliation."*

Maturity: ACP is production infrastructure with an ecosystem. AHP is early (5 months old, 0.3.0,
`StabilityIndex` markers on individual channel pages ranging 1.2–2), but unusually well-specified
for its age — RFC 2119 language, generated JSON Schema, five language SDKs.

### Architecture & Key Patterns

**ACP — point-to-point, JSON-RPC 2.0.**
- Local agents: sub-process over **stdio**. Remote: HTTP/WebSocket (still WIP).
- Client→Agent methods: `initialize`, `authenticate`, `session/new` (`cwd` + `mcpServers`),
  `session/prompt`; optional `session/load` (replays whole history as `session/update`s),
  `session/resume` (reconnect *without* replay), `session/set_mode`, `logout`,
  `session/cancel` (notification).
- Agent→Client methods: `session/request_permission` (baseline); optional `fs/read_text_file`,
  `fs/write_text_file`, `terminal/create|output|release|wait_for_exit|kill`, `elicitation/create`.
- One notification does the heavy lifting: **`session/update`** — message chunks, agent thought
  chunks, tool calls, **plans**, available-command changes, mode changes.
- Capability negotiation at `initialize` (`agentCapabilities.loadSession`,
  `sessionCapabilities.resume/close/additionalDirectories`, `mcpCapabilities.http/sse`).
- Conventions: absolute paths only, 1-based line numbers, camelCase keys (snake_case
  discriminators), Markdown as the default text format, `_meta` + `_`-prefixed methods for
  extensions. **Reuses MCP's JSON representations** where they exist, adds coding-UX types (diffs).

**AHP — hub-and-spoke, state-first, JSON-RPC 2.0, transport-agnostic** (WebSocket in practice;
requirement is only "reliable, ordered, bidirectional, complete-message"). Four ideas carry the
whole design:

1. **Channels are the universal routing key.** Every message — command *and* notification —
   carries a top-level `channel: URI` on its params. Any peer or proxy dispatches on
   `(method, params.channel)` with zero per-method deserialization. The invariant is enforced at
   **compile time** (`types/version/message-checks.ts` fails the build if a new method omits it).
   URI schemes: `ahp-root://`, `ahp-session:/<uuid>`, `ahp-chat:/<cid>`, `ahp-terminal:/<id>`,
   `ahp-changeset:/<id>`, `ahp-automations://`, `ahp-automation-run:/<id>`,
   `ahp-resource-watch:/<id>`, `ahp-otlp:`, `mcp://`.
2. **State + ordered actions, not events.** State-bearing channels deliver mutations as `action`
   envelopes `{ channel, action, serverSeq, origin: { clientId, clientSeq } }`. Clients apply pure
   reducers. Action names are display-oriented and agent-agnostic: `chat/turnStarted`,
   `chat/delta`, `chat/toolCallStart`, `chat/toolCallReady`, `chat/toolCallConfirmed`,
   `chat/turnCancelled`, `chat/draftChanged`, `chat/turnsLoaded`, `root/sessionAdded`,
   `session/chatAdded`, `resourceWatch/changed`.
3. **Write-ahead reconciliation.** Each client keeps `confirmedState`, `pendingActions[]`, and a
   computed `optimisticState` (what the UI renders). On an inbound envelope: own echo → pop
   pending, fold into confirmed; foreign action → fold in and rebase pending; echo carrying
   `rejectionReason` → drop the pending action, revert the optimistic effect. Conflicts are
   server-wins. This works because chat actions are overwhelmingly **append-only**, so rebasing is
   near-trivial.
4. **Reconnect with replay.** `reconnect { clientId, lastSeenServerSeq, subscriptions[] }` returns
   either `{type: "replay", actions[], missing[]}` or, if the gap exceeds the buffer,
   `{type: "snapshot", snapshots[]}`. `missing[]` names subscriptions the server cannot resume.
   Protocol *notifications* are deliberately not replayed — durable truth must live in state.

Other AHP surface worth noting: `subscribe` takes `delivery.maxLatencyMs` (server-side coalescing
budget, `0` = no buffering) and `view.turns` (advisory snapshot tail + `turnsNextCursor` for paging
history via `fetchTurns`). The `resource*` command family (`resourceRead/Write/List/Copy/Delete/
Move/Resolve/Mkdir/Request` + `createResourceWatch`) is **bidirectional** — the server can call it
on the client, which is how host-driven per-session filesystem providers and client-published
`virtual://` URIs work. Auth follows RFC 9728 (Protected Resource Metadata) + RFC 6750 (Bearer)
semantics over JSON-RPC: agents declare `AgentInfo.protectedResources[]` (with a `required` flag),
clients push tokens via `authenticate { resource, token }`, and `-32007 AuthRequired` is the
challenge. The `mcp://` channel relays a **capability-gated subset** of verbatim MCP traffic
(`serverTools`, `serverResources`, `logging`, `sampling`) against a server the host already runs —
anything outside the advertised union MUST be rejected `-32601`.

### Notable Implementation Details

- **The layering is stated, not inferred.** AHP's `guide/ahp-and-acp.md` says: *"AHP is a
  coordination layer. ACP is a communication layer. They compose naturally."* The reference
  architecture is a host speaking **AHP upstream to clients and ACP downstream to agents**, with an
  "agent event mapper" translating ACP `session/update` into AHP `chat/*` actions.
- **"AHP is a mutex over ACP."** Their own analogy. One turn per chat; the first
  `chat/toolCallConfirmed` wins and later ones are rejected; any client can cancel and the host
  forwards it as ACP `session/cancel`. ACP needs none of this because it assumes one client.
- **Doctrine as a spec artifact.** `guide/doctrine.md` is a written constitution with **design
  tests** ("Can a minimal client ignore this and still render a coherent session?", "Is the
  durable, user-visible result in state rather than only an ephemeral notification?") and explicit
  **anti-goals** (no agent loop, no model router, no universal tool registry, no required local
  filesystem or Git, no agent-to-agent semantics, *not a replacement for ACP*). This is the most
  transferable artifact in either project.
- **Per-chat working directories.** `ChatState.workingDirectories` is an optional **subset** of the
  session's set — the documented use case is allocating a **separate git worktree per chat** so
  parallel chats edit independently and an orchestrating chat merges back. (Directly mirrors
  AutoBot's own worktree discipline.)
- **Forks and side-chats as first-class.** `createChat` takes `source: {kind: "fork"|"sideChat",
  chat, turnId}`, gated on `AgentInfo.capabilities.multipleChats.{fork,sideChat}`. Side chats
  snapshot `selection.text` immutably at accept time — later streaming deltas don't retroactively
  mutate it.
- **Drafts are protocol state.** `chat/draftChanged` syncs in-progress, unsent user input across
  clients (debounced, e.g. on blur) — so you can start typing on desktop and finish on mobile.
- **Telemetry is a channel.** `ahp-otlp:` carries OTLP logs/traces/metrics as
  `otlp/exportLogs|Traces|Metrics` notifications, opaque URIs advertised at initialize.
- **`x-` prefix reserved** for implementation-defined extensions across channel schemes, methods,
  and action types; AHP guarantees it will never assign into that namespace.

### Strengths

**ACP:** proven adoption and network effects (registry + JetBrains + Zed + Neovim + Emacs); tiny,
learnable surface; stdio means zero infrastructure; deliberate MCP reuse instead of a parallel type
system; capability negotiation lets small agents ship early.

**AHP:** the multi-client problem is real and nobody else specifies it; the reconciliation model is
the correct one (optimistic + server-sequenced + rebase) and honestly scoped ("append-only makes
this easy"); the uniform `channel` invariant is genuinely elegant and *compiler-enforced*;
reconnect/replay is designed in rather than bolted on; agent-agnostic display state means clients
never learn a provider's tool vocabulary; five SDKs plus generated JSON Schema at 5 months old.

### Weaknesses / Limitations

**ACP:** remote transport (HTTP/WebSocket) still WIP — stdio-first is an editor-shaped assumption;
no multi-client story at all; no reconnection/replay semantics at the protocol level; assumes a
human in an editor invoking an agent for a task, which fits autonomous/long-running/headless
operation poorly; `session/load` replaying the *entire* history as notifications scales badly.

**AHP:** young and pre-1.0 — 0.3.0, mixed stability indices, breaking changes explicitly allowed;
253 stars vs ACP's 4k means one real implementation (VS Code) and effectively a single-vendor
ecosystem so far; a host is a **stateful server you now have to run, persist, sequence, and
replay-buffer** — a materially heavier operational commitment than "spawn a subprocess on stdio";
the channel/URI/action/reducer surface is large (10+ channel types, 30+ commands) and demands a
Redux-shaped client; the transport is unspecified, so cross-vendor interop is not yet guaranteed;
`ahp-and-acp.md` describes composition, but there is no normative ACP-adapter spec.

### Visible vs Hidden Metrics

**Visible**
- ACP: 4,044 stars, 349 forks, Apache-2.0, v1.7.0, JetBrains + Zed + Google + GitHub + 25 agents,
  a public registry. Adoption claims are third-party-verifiable, not self-reported.
- AHP: 253 stars, 66 forks, MIT, 786 commits, 5 language SDKs (Rust/TS/Kotlin/Go/Swift), generated
  JSON Schema, VS Code reference client, `MultiHostClient` in three SDKs. "Multi-client sync" is a
  design claim with exactly one shipping implementation — self-reported.

**Hidden**
- **ACP's real cost is shape, not code.** The protocol is small, but it encodes *one client, one
  human, one editor, one task*. Anything long-running, autonomous, or multi-observer has to be
  fought into that shape. Also: adopting ACP means tracking a fast-moving spec (v1.0→v1.7 inside a
  year) driven by Zed and JetBrains, whose priorities are editor UX.
- **AHP's real cost is a new stateful tier.** Authoritative state, monotonic sequencing, a replay
  buffer, subscription fan-out, snapshot/replay branching, and per-client reconciliation are all
  things you must now operate, persist, back up, and debug. Client-side, every consumer needs
  confirmed/pending/optimistic state and rebasing — that is a real rewrite of any straightforward
  "subscribe to WebSocket, append to array" UI. Add pre-1.0 churn on top.
- **Both:** taking a protocol as your *internal* model couples your domain vocabulary to someone
  else's release cadence. AHP mitigates this with `x-` extensions and an anti-goals list; ACP with
  `_meta`. Neither eliminates it.

**Weighing.** For anyone whose agent already runs in one place for one user, AHP's hidden
operational cost decisively outweighs its visible win — ACP (or a plain WebSocket) is correct, and
AHP is over-engineering. AHP's economics flip only when *multiple simultaneous clients over one
live session* is a real requirement — handoff between desktop and mobile, a shared/observed
session, or reconnect-without-loss over flaky links. Then the reconciliation machinery is not
optional complexity, it is the actual problem, and hand-rolling it is worse.

Crucially, the two are **not an either/or**. The cheapest correct read is: ACP is the *southbound*
interface (how you speak to agents, and how external editors could drive yours); AHP is a
*northbound design vocabulary* (how N clients share one session). The patterns — channels as
routing keys, state-first over event-first, write-ahead reconciliation, replay-on-reconnect,
capability-gated surfaces, doctrine with anti-goals — are adoptable **independently of adopting
either protocol on the wire**, and that is very likely where the value is.

---

---

## AutoBot Comparison: AHP + ACP → AutoBot

**Focus (owner-set):** AutoBot is one host, many clients — so AHP's core problem *is* AutoBot's
problem. This section is scoped to the multi-client session/state-sync path.

**Headline:** AutoBot already has almost every *ingredient* AHP needs — channel-scoped fan-out,
monotonic per-channel event ids, a Redis Streams replay buffer, per-session multi-connection
presence — but they are **wired to three different buses, and the main chat WebSocket uses the one
that is structurally single-client**. The gap is assembly, not invention.

### Audit: what was read

`autobot-backend/api/websockets.py`, `events/bus.py`, `event_manager.py`, `live_event_manager.py`,
`events/stream_manager.py`, `api/live_events.py`, `api/presence_ws.py`, `websocket/presence.py`,
`mcp/autobot_server.py`, `a2a/agent_card.py`; frontend
`src/services/GlobalWebSocketService.ts`, `src/services/LiveEventService.ts`,
`src/stores/useChatStore.ts`; plus repo-wide greps for `@router.websocket`, `register_ws_broadcast`,
`PersistStrategy`, `subscribe_ws`, `event_id`, and `acp|agent client protocol`.

---

### Finding 0 (blocking, pre-existing bug) — `/api/ws` is structurally single-client

Not an adoption item — a defect the audit surfaced, and the reason multi-client does not work today.

`api/websockets.py:681` registers each connection's handler via
`get_event_bus().register_ws_broadcast(broadcast_event)`, which lands on
`EventManager.register_websocket_broadcast` (`event_manager.py:53`). That setter assigns a **single
scalar**, not a list:

```python
self._websocket_broadcast_callback: Callable[...] | None = None   # event_manager.py:31
```

Consequences, in order of severity:

1. **Last-writer-wins.** Client B connecting silently stops Client A receiving anything on this
   path. No error, no log.
2. **First disconnect kills delivery for everyone.** `api/websockets.py:694` clears the callback to
   `None` on *any* client's teardown — including in the `finally` of a client that was already
   superseded. Remaining connected clients go permanently silent.
3. **Chat history stops being written.** `_add_to_chat_history` is invoked from *inside*
   `broadcast_event` (`api/websockets.py:510`). No callback → no broadcast → **no persistence**.
   This is a data-loss path, not just a UI path.

Blast radius is wide: `PersistStrategy.NONE` (which routes to this single-callback path) is the
strategy used by `api/workflow.py` (7 sites), `chat_workflow/cot_events.py:201`, `api/agent.py:194`,
`orchestrator.py:968`, `orchestration/workflow_runner.py:695`,
`services/approval_gate_service.py:362`, `services/npu_worker_manager.py:902`, `worker_node.py`,
`diagnostics.py`. Chain-of-thought, workflow progress, and approval-gate events all ride it.

The frontend's primary socket, `GlobalWebSocketService` (`src/services/GlobalWebSocketService.ts:146`),
connects to exactly this endpoint (`${getApiBase()}/ws`).

**This should be filed and fixed on its own merits regardless of any protocol adoption.** The fix
is small — make the callback a set keyed by connection — and does not require AHP.

---

### What We Can Adopt

#### 1. Host-authoritative session state (AHP's central premise) — **adopt-with-conditions**

*Already-exists audit.* `src/stores/useChatStore.ts` is the source of truth for sessions today:
`createNewSession` mints the id client-side (`:136-138`), messages are appended locally
(`:199`, `:279`), and the store persists to `localStorage` under `autobot-chat-store` (`:856`).
There is no server-authoritative session document and no reconciliation anywhere in the store —
grep for `optimistic|rollback|revert` returns only `hasPendingApproval` (`:462`), which is
unrelated. Two browsers on one account produce two divergent truths that never converge.

*Visible benefit.* Open the same session on desktop and phone and see the same thing; a refresh
stops losing state; server-side features (search, audit, quotas) get one thing to read.

*Hidden cost.* This is the single largest item here. It relocates ownership of chat state from the
store to the backend, touches every writer in `useChatStore.ts`, and demands a
confirmed/pending/optimistic split in the store to avoid regressing input latency. Pre-1.0 protocol
churn if AHP's shapes are copied literally.

*Verdict.* **Adopt the doctrine, not the wire format.** Make the backend authoritative for session
and turn state and give clients a snapshot+delta subscription. Do *not* import AHP's
`ahp-session:/` / `ahp-chat:/` URI scheme or its full 10-channel/30-command surface — AutoBot has
one host and one product, so the interop pressure that justifies AHP's size does not apply.
Effort: **significant**.

#### 2. Reconnect-with-replay via `lastSeenServerSeq` — **adopt** (highest value/effort ratio)

*Already-exists audit.* Three of the four pieces are built:
- `LiveEventManager.publish` already stamps a **monotonic per-channel `event_id`**
  (`live_event_manager.py:_next_event_id`, `:88`).
- `LiveEventService.ts:33,409` already **receives** `event_id` — and does nothing with it but log.
- `RedisEventStreamManager` (`events/stream_manager.py:125`) is a **real replay buffer**: Redis
  Streams via `xadd(..., maxlen=config.max_stream_length)` (`:167`), with `xrange` (`:322`),
  `get_latest` (`:262`), and `get_event` (`:337`).

The missing piece is the wiring, and it is worse than missing — it is *explicitly dropped*:

```python
if persist is PersistStrategy.REDIS:
    logger.critical("PersistStrategy.REDIS is not implemented in EventBus — event dropped ...")
    return                                              # events/bus.py:76-84
```

Meanwhile `LiveEventManager._event_counters` is a plain in-process dict — it resets on restart and
is not shared across workers, so today's `event_id` is not even durable.

Reconnect handling exists on both services (`GlobalWebSocketService.ts:447`,
`LiveEventService.ts:218`) with exponential backoff, and `LiveEventService` correctly re-subscribes
its channels on reopen (`:148`). But no client sends a last-seen id, so **every event during the
disconnect window is silently lost** — the failure mode is invisible, which is the worst kind.

*Visible benefit.* No lost workflow/CoT/approval events across a laptop sleep, a WiFi handover, or
a backend restart.

*Hidden cost.* Sequence allocation must move to Redis to be durable and multi-worker-safe; you
inherit a retention policy (`maxlen`) and the snapshot-vs-replay branch when the gap exceeds the
buffer. Modest and well-bounded.

*Verdict.* **Adopt.** Wire `PersistStrategy.REDIS` into `EventBus.publish`, source `event_id` from
the Redis stream id, accept `last_event_id` on the `/ws/live` subscribe action, and replay via
`xrange` — falling back to a snapshot when the id is older than `maxlen`. Effort: **moderate**.

#### 3. Uniform `channel` routing key on *every* message — **adopt, narrowly**

*Already-exists audit.* AutoBot has **25 WebSocket routes** (`grep -c '@router.websocket'`,
excluding tests): `api/websockets.py` ×3, `api/live_events.py`, `api/terminal.py` ×2,
`api/analytics.py` ×2, `api/advanced_control.py` ×2, `api/presence_ws.py`, `api/monitoring.py`,
`api/voice_stream.py`, `api/logs.py`, `api/vnc_proxy.py`, `api/overseer_handlers.py`,
`services/workflow_automation/routes.py`, and others — each with its own hand-rolled envelope,
auth, keepalive, and teardown.

`LiveEventManager` already validates a channel grammar —
`{agent,task,workflow,heartbeat,company,board}:{id}` plus `global` (`live_event_manager.py:23,25-32`)
— so the concept is established and enforced; it is just confined to one endpoint.

*Visible benefit.* One socket, one envelope, one auth path; new event types need no new route.
Proxies and the frontend dispatch on `(type, channel)` without per-message knowledge.

*Hidden cost.* Consolidating 25 endpoints is a large migration touching binary-ish streams (VNC,
voice, terminal PTY) that genuinely should *not* be multiplexed onto a JSON event socket.

*Verdict.* **Adopt for the event-shaped subset only** — chat, workflow, agent, approvals, NPU,
analytics, monitoring. Leave VNC/voice/terminal/logs on dedicated sockets. Extend the existing
`_VALID_PREFIXES` grammar with `session:{id}` and `chat:{id}` rather than inventing a URI scheme.
Effort: **significant** (but incremental — one route at a time).

#### 4. Write-ahead reconciliation in the Pinia store — **adopt-with-conditions**

*Already-exists audit.* Nothing resembling this exists. `useChatStore.ts` pushes straight into
`currentSession.value.messages` with no pending set; the only echo-handling is id-matching dedup at
`:252` and `:274` (#11843), which is a symptom of exactly the problem AHP's `origin`/`clientSeq`
solves properly.

*Visible benefit.* Instant local echo *and* convergence between clients; deletes the dedup hacks.

*Hidden cost.* Real complexity in the store — `confirmedState` + `pendingActions[]` + computed
`optimisticState`, plus rebase. Only pays off **after** item 1 lands; on its own it has nothing to
reconcile against.

*Verdict.* **Adopt-with-conditions — strictly sequenced after item 1.** AHP's own honesty applies
here: chat actions are append-only, so rebasing is near-trivial and server-wins settles the rest.
Effort: **moderate**, conditional.

#### 5. A written doctrine with anti-goals and design tests — **adopt** (cheapest, highest leverage)

*Already-exists audit.* `docs/developer/` covers *process* (`CLAUDE_RULES.md`, `CLAUDE_GIT.md`,
`CLAUDE_REVIEW.md`, `ARCHITECTURE_EXCEPTIONS.md`) but there is no equivalent of AHP's
`guide/doctrine.md` — a normative statement of *what the event/state layer is for and what it
refuses to do*. The three-parallel-bus history recorded in `events/bus.py:7-12` (and its still-open
"Phase 2/Phase 3" migration plan) is precisely what an anti-goals list prevents.

*Visible benefit.* Kills the "which bus do I publish to?" question permanently; gives reviewers an
objective test.

*Hidden cost.* Essentially none — one document. Risk is it going stale, mitigated by keeping it a
checklist per `CLAUDE.md`'s lean-instructions rule.

*Verdict.* **Adopt.** Steal AHP's design tests verbatim — *"Can a minimal client ignore this and
still render a coherent session?"*, *"Is the durable, user-visible result in state rather than only
an ephemeral notification?"* — and its anti-goals format. Effort: **trivial**.

#### 6. ACP server surface (let external editors drive AutoBot agents) — **adopt-with-conditions**

*Already-exists audit.* **No ACP anywhere.** A repo-wide grep for
`agent client protocol|agent-client-protocol` returns only
`docs/archives/plans/2026-03-04-service-message-bus-design.md:17`, which refers to an unrelated
"Agent Communication Protocol" from a LangGraph article. AutoBot does expose two adjacent surfaces:
an MCP **server** (`mcp/autobot_server.py`, with scope checks `_check_scope:526`, rate limiting
`_is_rate_limited:535`, and Redis token validation `_validate_redis_token:423`) and an A2A agent
card (`a2a/agent_card.py:build_agent_card:128`). Both **advertise capability outward**; neither lets
an editor *drive* an AutoBot agent through a prompt/stream/permission loop.

*Visible benefit.* Implementing `initialize` / `session/new` / `session/prompt` / `session/update` /
`session/request_permission` would make AutoBot agents appear inside Zed, JetBrains, Neovim and
Emacs via the ACP Registry — real distribution for a protocol with 4k stars and vendor backing.

*Hidden cost.* ACP presumes one client, one human, one editor, one task — the opposite of AutoBot's
long-running autonomous shape. Sessions would need a mapping from ACP's stdio-scoped model onto
AutoBot's persistent server-side sessions, and ACP moved v1.0→v1.7 within a year on a cadence set by
editor-UX priorities.

*Verdict.* **Adopt-with-conditions, and not now.** Correct sequencing is items 0 → 2 → 1: a
host-authoritative session with replay is a *prerequisite* for an ACP adapter that behaves sanely,
because ACP's `session/load` replays whole history and `session/resume` needs a durable session to
resume into. Revisit once item 1 lands. Effort: **significant**.

---

### What We Already Do Better

- **WebSocket authentication.** AHP explicitly punts: *"Access to the AHP endpoint itself is a
  transport-layer concern and is outside the scope of the AHP wire protocol."* AutoBot has a
  concrete, uniform, tested convention — `enforce_ws_origin` (`api/ws_security.py`) plus
  `authenticate_websocket`, with the deliberate accept-then-close-4001 pattern
  (`api/websockets.py:718-724`, `api/live_events.py:224-231`, #12366) so clients get a real close
  frame instead of an ambiguous handshake 403. Guarded by `tests/test_websocket_auth_smoke.py` and
  `tests/test_websockets_auth_reject_12366.py`.
- **Presence and collaboration.** AHP's `SessionState` has an `activeClients` field and stops
  there. `websocket/presence.py:PresenceManager` keeps
  `Dict[session_id][user_id] -> Set[WebSocket]` (`:35`) — note it already models **one user with
  several concurrent connections**, i.e. the desktop-plus-phone case — with join/leave broadcast
  (`_broadcast_event:160`), `get_online_users:112`, and targeted `send_to_user:128`. It is wired
  end-to-end to `src/composables/useSessionCollaboration.ts`,
  `components/collaboration/ParticipantList.vue` and `PresenceIndicator.vue`. **"Who is here" is
  solved better than AHP specifies it; "what they see" is the part that is missing.**
- **MCP depth.** AHP's `mcp://` channel relays a deliberately narrow, capability-gated subset
  (`serverTools`, `serverResources`, `logging`, `sampling`). AutoBot runs a full MCP server with
  per-tool scope enforcement and throttling (`mcp/auth_throttle.py`).
- **Explicit durability as a typed choice.** `PersistStrategy` (`events/bus.py:40`) makes
  "in-memory vs fan-out vs durable" a decision at the call site. AHP's doctrine assumes durable
  state but offers no equivalent knob. The enum is the right design — one arm of it just is not
  implemented yet (see item 2).

### Gaps & Opportunities — prioritised

| # | Gap | Impact | Effort | Note |
|---|-----|--------|--------|------|
| 1 | `/api/ws` single-callback broadcast (Finding 0) | **Critical** — multi-client silently broken; chat history silently stops persisting | trivial | Pre-existing bug. File and fix independently of everything else. |
| 2 | `PersistStrategy.REDIS` logs critical and drops the event | **High** — the durable substrate is built (`events/stream_manager.py`) and unreachable through the unified bus | trivial–moderate | Unwired existing work, not new work. |
| 3 | No `last_event_id` / replay on reconnect | **High** — events in the disconnect window are lost with no signal | moderate | Depends on #2. |
| 4 | `event_id` is an in-process counter | **High** — resets on restart, diverges across workers | trivial | Source it from the Redis stream id. |
| 5 | Two competing event sockets (`/api/ws` vs `/api/ws/live`), frontend uses **both** | **High** — canonical-source violation; `events/bus.py:19-22` still lists Phase 2/3 as outstanding | moderate | `GlobalWebSocketService` → `/api/ws`; `LiveEventService` → `/ws/live`. |
| 6 | Session state is client-authoritative (Pinia + `localStorage`) | **High** — two clients cannot converge, by construction | significant | The real multi-client blocker. |
| 7 | No `session:`/`chat:` channel prefixes in `_VALID_PREFIXES` | Medium — no way to scope a subscription to a conversation | trivial | One-line grammar extension; unblocks #6. |
| 8 | No write-ahead reconciliation in the store | Medium | moderate | Only after #6. |
| 9 | No doctrine doc for the event/state layer | Medium — three-bus sprawl is the recorded cost of its absence | trivial | Best value-per-hour on the list. |
| 10 | 25 bespoke WebSocket routes | Medium | significant | Consolidate the event-shaped subset only. |
| 11 | No ACP server surface | Low *now*, high later | significant | Gated on #6. |
| 12 | No synchronized drafts / per-chat working directory | Low | moderate | AHP's `chat/draftChanged`; the per-chat-worktree idea maps onto AutoBot's own worktree discipline. |

### Specific Code/Files Affected

- `autobot-backend/event_manager.py:31,53` — `_websocket_broadcast_callback` scalar →
  `set[Callable]`; `register_websocket_broadcast` → `add`/`discard`. **(Gap 1)**
- `autobot-backend/api/websockets.py:671-697` — register/unregister per connection instead of
  overwriting a global; move `_add_to_chat_history` (`:459`) **out** of the broadcast handler so
  persistence no longer depends on a client being attached. **(Gap 1)**
- `autobot-backend/events/bus.py:76-84` — implement the `PersistStrategy.REDIS` arm against
  `RedisEventStreamManager` instead of `logger.critical` + `return`. **(Gaps 2, 4)**
- `autobot-backend/live_event_manager.py:23,84-88` — add `session`/`chat` to `_VALID_PREFIXES`;
  source `event_id` from the Redis stream id rather than `_event_counters`. **(Gaps 4, 7)**
- `autobot-backend/api/live_events.py:_handle_message` — accept `last_event_id` on `subscribe`;
  replay via `xrange`, else return a snapshot. **(Gap 3)**
- `autobot-frontend/src/services/LiveEventService.ts:148,251` — track the highest seen `event_id`
  per channel; send it on re-subscribe; surface a gap as a resync rather than a silent hole.
  **(Gap 3)**
- `autobot-frontend/src/services/GlobalWebSocketService.ts:146,153` — migration target: fold onto
  `/ws/live` once channel coverage is equivalent, retiring the duplicate path. **(Gap 5)**
- `autobot-frontend/src/stores/useChatStore.ts:136,199,279,252,274` — server-assigned session ids;
  snapshot+delta subscription; confirmed/pending/optimistic split replacing the id-match dedup.
  **(Gaps 6, 8)**
- `docs/developer/` — new `EVENT_STATE_DOCTRINE.md` (principles, design tests, anti-goals), linked
  from the `CLAUDE.md` trigger table. **(Gap 9)**

### Recommended sequence

**Gap 1 → 2 → 4 → 3 → 7 → 6 → 8 → 5 → 10 → 11.** The first four are small, independently
valuable, and mostly consist of connecting things AutoBot has already built. Gap 9 (the doctrine
doc) can land in parallel at any point and makes the rest easier to review.
