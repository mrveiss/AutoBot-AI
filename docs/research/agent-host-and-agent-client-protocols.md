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

## Phase 2 — AutoBot Comparison

Not started. Awaiting explicit go-ahead.
