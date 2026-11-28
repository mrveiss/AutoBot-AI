# Local agent-team desktop workspace — provider-agnostic agents, failover, mailbox and queues

**Date:** 2026-10-27
**Source:** a public, source-available (noncommercial licence) desktop application from a
small vendor, about ten weeks old at the time of reading and in active daily development. It
runs a team of persistent coding/assistant agents on the user's machine by wrapping existing
vendor CLIs and agent runtimes. Repo name, author and locating metadata are withheld per the
no-external-names rule for committed docs.
**Status:** Phase 1 (source analysis) complete. Phase 2 (comparison against AutoBot) awaits
maintainer go-ahead.

## Source analysis

### What it is

A local-first Electron desktop app (plus web and mobile clients) that gives each "agent" a name,
instructions, a dedicated working directory and one stable conversation, and backs it with an
interchangeable runtime: several vendor coding CLIs driven over stdio/JSONL or stream-JSON, any
Agent Client Protocol (ACP) agent, OpenAI-compatible endpoints, or local model servers. Agents
message each other, delegate, share files, and work through crash-safe FIFO queues. It ships an
embedded controllable browser, optional OS-level computer use, routines with webhook triggers,
shared "channel" chats, and remote access to the desktop host from phones over WebRTC. Labelled a
development preview; agents run with full local access and no per-action approval after a
first-launch consent.

### Architecture

- **Electron main** owns lifecycle, window security, typed IPC; **backend** layer owns provider
  adapters, persistence, scheduling, transfers, browser host; **preload** exposes one typed API;
  **SolidJS renderer** for UI. Bun monorepo with `contracts` (process-boundary schemas and limits),
  `i18n`, `ui`, `logging`, `telemetry` packages.
- **Persistence:** one SQLite database as an **event/command log with read projections** —
  agents, conversations, provider-session bindings, queues, reactions, attachment indexes. Every
  schema change ships a migration test; a schema-history JSON plus parity test guards drift.
- **Provider drivers:** one adapter per runtime (app-server over JSONL, agent SDK over stream
  JSON, ACP client with per-vendor "flavors", an RPC driver for a further CLI). Runtimes are
  downloaded and pinned into a machine-wide store, update-checked hourly, with a lockfile only as
  first-install fallback and a blocklist of known-bad runtime versions.
- **Remote/team:** an authenticated Team API bound to localhost, carried to clients over WebRTC
  (RPC + events + binary) with self-hostable signalling/TURN; account service on serverless
  workers. Capability negotiation (`media-attachments`, `routine-flows-v1`, …) gates features
  against older hosts.
- **Services pattern:** backend effects run through a typed effect/service layer with explicit
  change rules and required-verification lists per module.

### Notable implementation details

1. **Stable conversation across runtimes.** The user-facing conversation is owned locally; native
   provider session IDs are a private binding used only to resume runtime state. Switching runtime
   keeps workspace and history.
2. **Backup-model failover.** When a plan hits its limit or a provider is overloaded/down, the turn
   lifecycle moves the agent to a configured backup model; an end-to-end script exercises it.
3. **Per-agent context monitoring with automatic compaction** before a thread exhausts the model
   window, with per-provider context-category accounting.
4. **Mailbox with transactional attachments.** Generated attachments become visible only after the
   conversation+mailbox commit succeeds; file deletions go through a retrying **deletion outbox**;
   each transfer carries a manifest (owner, recipients, size, SHA-256). Path-containment checks
   keep managed paths inside their roots.
5. **Queue semantics:** FIFO per agent with pause/resume/cancel, crash-safe persistence, a drain
   scheduler and a delivery gate; channel chats have exactly one task owner with explicit
   Stop/Resume/Reassign/Archive/Restore.
6. **Delegation policy in instructions:** an agent must try every path before refusing; when work
   is outside its profile it lists teammates and delegates to the one whose description fits;
   acknowledgements must not loop; progress updates report outcomes, not setup narration.
7. **Process confinement** for some runtimes (confined config dirs so the user's own CLI settings
   are never touched), MCP secret redaction, encrypted per-route webhook secrets.
8. **Routine flows:** a canvas linking one agent's routine result onward to other agents, stored on
   the host and exposed to remote clients through a capability.

### Strongest candidates — how the source actually does it

**A. Failover only for a turn that has not acted yet.**

- Each agent stores an ordered list of up to 8 backup models.
- When a turn fails, the error is sorted into one of six causes: billing, provider_unavailable,
  rate_limit, authentication, network, timeout.
- The switch happens **only if the turn did no work yet** — no text was written and no tool ran.
  In that case the turn's messages go back on the queue, the failed model is skipped for 10
  minutes, and the next drain reruns the turn on the backup with no error banner.
- A turn that already wrote text or ran a tool fails with its error instead, because replaying
  side effects on another model is unsafe.
- Each message is retried at most once per failed model.
- Two kinds of hold:
  - **Plan usage limit:** holds every agent on that account and model until the limit resets.
  - **Provider error:** holds nothing; it only skips that model for a while.
- A remembered "return" model moves the agent back once the hold ends. A model the user picks by
  hand clears the return.
- Background tasks, a refused turn start, and a provider that fails to start never fail over.
- *Transferable idea:* the "not acted yet" test is the idempotency guard that makes automatic
  failover safe.

**B. Provider/runtime changes wait for a turn boundary.**

- A runtime change asked for mid-turn is stored on the agent as a pending runtime.
- It is applied just before the next queued message starts, and only if no work has started.
- Then every provider session of that agent is retired, and each thread gets a **history handoff**
  on the new provider.
- Automatic moves (usage limit, provider error) still wait until the agent is idle.
- The conversation is the app's own. Provider session ids are a private resume binding, never the
  identity of the conversation.

**C. Compaction belongs to the runtime; the app only coordinates it.**

- The app does not add its own summarise call.
- For runtimes with an explicit compact operation, it triggers one at a usage-based threshold
  (80% of the window, measured from the last reported usage) and reserves the queue meanwhile.
- A guard requires minimum growth before compacting again, so it never compacts in a loop.
- Runtimes that compact natively are left alone.
- A runtime that only reports how full its context is falls back to **session rotation**: save the
  work steps, close the session, and open a new one that receives the history handoff.
- Stated rules: a missing usage report is not zero usage; cumulative account usage is not context
  occupancy; no fixed context-window constant.
- Shared-channel context goes in as a **self-contained, bounded packet**: purpose,
  responsibilities, the current request, shared decisions, recent messages, plus a versioned
  summary of older messages with sequence and source ids. Compaction or a provider swap therefore
  never loses shared decisions.

**D. A queue that one scheduler controls.**

- One drain scheduler per agent decides all work. Each side task is drained as its own lane.
- Holds are named — usage limit, hidden agent, waiting for a provider change — and recorded, not
  implicit.
- Queue edits and agent deletion record file removals inside the mailbox transaction. A deletion
  outbox retries any removal that fails.
- Channel commands go through an orchestration log with command receipts. Messages have stable ids
  and a sequence number per channel, so any projection can be rebuilt from its events.

### Strengths

- Clean ownership statements: one DB is the source of truth; each store's responsibility is named.
- Strong migration discipline (a migration test per schema change, schema parity test).
- Provider independence done at the right seam — the conversation is ours, the runtime is rented.
- Capability negotiation instead of version checks between host and clients.
- Practical failure handling: failover on quota/outage, deletion outbox, commit-gated visibility.

### Weaknesses

- **No safety boundary by design:** full access, no approvals, network unrestricted. The project
  states this is a product decision, not a security boundary.
- Heavy dependence on third-party CLIs and their terms; each vendor runtime change is the
  adopter's breakage. A blocklist file exists precisely because upstream releases break it.
- Very large surface for a young project (desktop, web, two mobile apps, three chat-platform apps,
  serverless account API, signalling/TURN, status site) — maintenance load is high.
- Noncommercial licence: code cannot be reused; only ideas are adoptable.
- Electron + embedded browser + computer-use driver in one privileged process tree.

### Visible vs hidden metrics

- **Visible:** many supported runtimes, failover, cross-device access, ~1.7k stars in ten weeks
  (self-reported popularity; no independent benchmarks — there are no performance claims at all).
- **Hidden:** continuous churn tracking upstream CLIs (hourly update checks, version blocklist);
  terms-of-service exposure per vendor subscription; no approval layer means any prompt injection
  in browsed content has full local reach; large multi-platform ops surface; licence forbids code
  reuse.
- **Weighing:** the hidden costs fall mainly on whoever wraps vendor CLIs. For AutoBot the
  transferable value is in the patterns — local conversation ownership with private runtime
  bindings, failover on quota/outage, commit-gated attachments with a deletion outbox, capability
  negotiation, delegation policy — not in the product shape. Its no-approval stance conflicts
  directly with AutoBot's approval-gate rules and must not be imported.

## AutoBot comparison

Audit against `origin/main`, 2026-10-27, read-only. Every one of the 10 candidate capabilities is
**partial** in AutoBot: building blocks exist, and several are built but not on the main path.
Three key claims were re-checked directly: `llm_shared/rate_limit_backoff.py:41`,
`llc/services/attachment_service.py:144` vs `:209`, `chat_workflow/manager.py:2132`.

### What we can adopt

| # | Idea (source pattern) | AutoBot today (evidence) | Missing delta | Visible benefit / hidden cost | Verdict | Effort |
| --- | --- | --- | --- | --- | --- | --- |
| A1 | Safe failover: only if the turn has not acted; errors sorted into causes; failed model skipped for a while | `llm_shared/model_fallback_coordinator.py:137` `execute_with_fallback`, `:202` `_on_rate_limit`; `provider_degradation.py:137`; called only from `api/openai_compat.py:530` and `api/anthropic_compat.py:375` | (a) only rate-limit patterns trigger it (`rate_limit_backoff.py:41`), no overload/5xx/connection causes; (b) the main chat path posts straight to the Ollama endpoint and returns an error on non-200 (`chat_workflow/manager.py:2132-2139`); (c) no "has this turn acted?" guard, so agent runs that already called tools cannot fail over safely | Chats survive provider outages / one more classifier and a guard; risk of double side effects if the guard is wrong | **adopt** — wire the existing coordinator into the chat path and add the not-acted guard plus the cause classifier; reuse, never a second fallback stack | moderate |
| A2 | Provider session id as a private, durable binding; runtime switch applied at a turn boundary with a history handoff | `llc/adapters/claude_code_adapter.py:66` session key per agent in Redis with a 4 h TTL; `llm_shared/provider_registry.py:88` in-memory `_conversation_overrides` | binding keyed by agent, not (conversation, runtime); not durable (Redis TTL); overrides live in one process's memory; no handoff that rebuilds the new runtime's context from local history | Switching provider keeps the conversation / one new table plus migration; must follow the store-authority rule (one durable store) | **adopt-with-conditions** — the durable store is chosen through `system_of_record`; Redis stays a projection | moderate |
| A3 | Compaction coordinated per agent run, with a minimum-growth guard and session rotation for runtimes that cannot compact | `chat_history/context_overflow.py:608` `ContextOverflowProtection` (80% warn, 90% summarise), wired at `api/chat.py:805` | chat sessions only — the agent loop and LLC agent runs have no token accounting; `api/chat.py:807` falls back to `"gpt-4"` when the model is unknown, so the limit can be wrong; no minimum-growth guard | Long agent runs stop dying at the window limit / per-runtime usage reporting differs, which means an adapter seam to maintain | **adopt** for LLC agent runs; fixing the `"gpt-4"` fallback is a bug on its own and is fixed regardless | moderate |
| A4 | Commit-gated attachments plus a retrying deletion outbox plus a SHA-256 manifest | `llc/services/attachment_service.py`: writes the file (`:144`) before the commit (`:209`); `delete()` unlinks before the commit (`:297`); `_delete_local` (`:153`) only logs failures; path containment via `autobot_shared/security/path_validator.py:96` | stage → commit → publish ordering; an outbox row for deletions with retries; content hash on the attachment row | No orphan or ghost files / one outbox table and a sweeper task | **adopt** — this is a correctness defect, not a feature | trivial–moderate |
| A5 | Agent-to-agent delegation guided by profile ("list teammates, delegate to the fitting one") | `llc/api/agent_api.py:461` `search_peer_agents`; handoffs only human↔agent (`llc/services/handoff.py:90`, `:137`); `llc/agent_tools.py:140` `_create_task` has no assignee | agent→agent handoff; an assignee on created tasks; adapters and templates never tell agents that peer search exists | Specialist agents actually used / delegation loops (the source adds an explicit no-acknowledgement-loop rule) | **adopt** — wire the existing peer search in first; no new mailbox subsystem | moderate |
| A6 | Webhook routes that trigger agent routines | `services/trigger_service.py:441` HMAC checks; triggers only launch workflows (`:724` `_launch_workflow`); LLC routines are cron or manual only (`llc/api/routines.py:282`) | a webhook can target an LLC routine; replay protection (timestamp/nonce); `trigger_service.py:69` stores the secret in **plaintext** when the encryption service is unavailable | External events wake agents / more untrusted ingress, which needs the threat-model review | **adopt-with-conditions** — fix the plaintext fallback first, as a security defect | moderate |

### Rejected by hidden metrics

- **Wrapping many vendor coding CLIs and ACP agents as backends** (AutoBot has 5 adapters,
  `llc/adapters/__init__.py:55-59`, and no ACP client). The hidden cost is upstream churn, version
  blocklists and terms-of-service exposure per vendor. The `codex_subscription_adapter.py` stub
  should be finished or tracked, but there is no general ACP-client expansion.
- **Full access with no approvals.** This directly conflicts with AutoBot's approval gates (#17038).
- **One host-wide capability set** (only per-feature `/capabilities` endpoints today; the frontend
  never calls `/chat/capabilities`). The idea is good, but the payoff is low until there are
  multiple client versions in the field. Recorded, not proposed.

### What we already do better

- **Approval gates and a threat model** versus the source's stated "not a security boundary".
- **Migration CI gates:** an ORM-vs-migration drift test
  (`tests/migrations/test_orm_columns_match_migrations_17996.py`), a downgrade round-trip and a
  schema-authority test run in `migration-gate.yml`. The source has a test per migration; we have
  stronger gates but cover fewer migrations (40 tests for 110 migrations, and column-only parity).
  This gap is worth noting but is not adopted from this source.
- **Queue durability:** LLC work items live in Postgres with pause/resume
  (`llc/services/controls_service.py:86`, `:139`), auto-pause on quota
  (`llc/scheduler/heartbeat_scheduler.py:739-769`) and crash recovery
  (`llc/scheduler/session_checkpointer.py` `recover_incomplete_runs`). The only gap against the
  source is cancelling an item that is queued but not yet running.

### Specific code and files affected

- `chat_workflow/manager.py` (~2126-2142): route through the fallback coordinator instead of a raw POST.
- `llm_shared/rate_limit_backoff.py`, `model_fallback_coordinator.py`: a cause classifier and the
  not-acted guard.
- `llc/adapters/claude_code_adapter.py` and a new durable runtime-binding store: per-conversation
  binding, history handoff.
- `chat_history/context_overflow.py`, `api/chat.py:807`, LLC heartbeat runs: per-run token
  accounting and the model-limit fix.
- `llc/services/attachment_service.py`: stage/commit/publish ordering, deletion outbox, sha256 column.
- `llc/agent_tools.py`, `llc/services/handoff.py`, adapter instruction templates: agent→agent
  delegation.
- `services/trigger_service.py`: plaintext fallback, replay protection, routine targets.

## Linked issues

- #19752 Umbrella: agent-runtime reliability — safe failover, runtime binding, run compaction, transactional attachments, delegation, webhook routines
- #19753 feat(llm): fail over on provider outage, not only rate limits — wire the chat path through the fallback coordinator, with a not-acted guard
- #19754 feat(llc): durable per-conversation runtime binding — native session ids private, provider switch at a turn boundary with history handoff
- #19755 feat(llc): agent runs have no context accounting or compaction — compact or rotate at the threshold with a minimum-growth guard
- #19756 bug(llc): attachment files are written before the DB commit and unlinked before it — orphan files, no retry on failed deletes
- #19757 feat(llc): agents cannot delegate to a teammate — task assignee, agent→agent handoff, instructions that name peer search
- #19758 feat(llc): webhook triggers cannot start an LLC routine, and signatures have no replay protection
- #19759 security(triggers): webhook trigger secret is stored in plaintext when the encryption service is unavailable — fail closed
- #19760 bug(chat): context-limit lookup falls back to a hard-coded vendor model name — compaction threshold uses the wrong window
