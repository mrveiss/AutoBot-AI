# Research: plugin-kernel agent harness

Destination on landing: `docs/research/plugin-kernel-agent-harness.md` (rides as a passenger in the next code PR).

## Linked issues

- #19290 bug(chat): manual summarize endpoint hardcodes a hosted model — fails on local-only deployments and diverges from auto-compaction
- #19298 feat(chat): session files and agent snapshots carry no format version — shape changes rewrite user data in place
- #19299 feat(agents): no durable per-session objective — goal survives neither restart nor resume, and the work-item binding expires in 24h
- #19300 feat(chat): no /compact slash command — manual compaction is API-only
- #19301 feat(chat): an image-rejecting route fails the request — no placeholder-and-retry fallback
- #17469 bug(agent-loop): three timeout budgets declared in AgentLoopConfig and read by nothing (scope comment added)
- #17229 feat(agents): an agent run leaves no durable record designed to be read back (AC proposed)
- #19302 security(plugin-sdk): disable/unload/reload reverse nothing — a disabled plugin's hooks and tools still fire, and grants outlive unload
- #19303 bug(browser): the evaluate action runs caller script with no timeout and returns its result unbounded
- #18302 security(shell): the agent shell runs on the host unsandboxed — run each command in a fail-closed bubblewrap namespace (per-mode profile decision posted, needs-decision)

## Source Analysis: a plugin-kernel agent harness from a model vendor

### What It Is
An open-source, permissively licensed TypeScript agent harness published by a model vendor, in developer preview with breaking changes announced. It ships Web UI, CLI, desktop, headless runner, SDKs and an agent-client-protocol server, all as compositions of one plugin tree in a large monorepo. Star counts, dates and contributor counts are omitted deliberately — together they identify the repository. The vendor's own safety notice says it has had no security audit and is not production-ready.

### Architecture & Key Patterns
- **Plugin kernel.** Built on a context/effects framework: every part — model adapter, tool registry, session log, the agent loop itself — is a plugin contributing services, typed events and *reversible effects* to a shared context. Unloading a plugin unwinds its registrations. No privileged core.
- **Profiles and bundles.** A running instance is a plugin tree composed from ordered layers: profile → bundles → profile patch → home patch → CLI `--patch` overlays. A patch targets a config row by id. `--dump-config` prints the resolved tree.
- **Capability seams.** Every capability is a triad: Service Definition (interface) / Service Provider (implementation) / Consumer (often a model-facing tool). Filesystem and subprocess providers share one "execution world", so pointing them at a remote sandbox moves shell, PTY and LSP together.
- **Three event domains.** Durable session events (append-only log, survive reload); live `agent/*` events carrying the agent handle; capability events (`fs/*`, `tools/*`, `telemetry/*`) attaching policy without importing the loop. Request/tool hooks are *waterfalls* (listener must call `next()`).
- **Turn/step model.** Step = one model request + its tool calls; turn = zero or more steps. Explicit pre-step admission hook can rewrite/reject input; a rejected first claim closes the turn with no step.
- **"Model-visible means logged."** Every model request must be reconstructable from the session log; new model-visible inputs require new session events; content rewrites go through registered pure projections.
- **Versioned session storage.** JSONL generations `session.vN.jsonl[.zstd]`, adjacent one-step migrations (`vN → vN+1`), committed generations never renamed or deleted; write-open publishes a verified successor beside the source.

### Notable Implementation Details
- **Loop-hygiene guards** as separate plugins: repeat-identical-tool-call reminder (advisory), per-tool-call timeout policy returning a clear timed-out error to the model.
- **Spill family:** oversized tool results replaced by preview + locator to session-scoped storage, opt-in via `maxInlineTokens`; on storage failure the original result is kept (fail-open to correctness).
- **Compaction family:** auto summarization under token pressure, `/compact`, tool-result pruner run *before* summarization, and image offload to placeholders when an image route rejects a request.
- **Sandbox family:** three modes (read-only / workspace-write / full-access), per-platform backends (Linux bwrap→Landlock, macOS Seatbelt, Windows restricted token + ACL), one-time user-approved escalation on denial; explicitly "same-world only" — containers/VMs replace the capability instead.
- **Programmatic tool calling runtime:** model writes a program run against host-provided async bindings in a fresh sandboxed process; optional persistent per-owner REPL.
- **Durable goal:** one objective per session surviving restart/resume/fork, model tools + human `/goal`, and an opt-in round driver for automatic continuation.
- **Postmortems in-repo** (numbered), architecture decision notes, generated config/tool/event catalogs, a verifier that rejects any app entrypoint bypassing the launcher.

### Strengths
- Extreme replaceability: any row of the tree can be patched; one provider swap changes the whole product.
- Rigorous replay story — model context is a pure function of the durable log.
- Defence-in-depth hygiene (spill, prune, compaction, timeouts, repeat-call reminders) all small, independent and removable.
- Strong documentation discipline (generated catalogs, decision notes, bilingual docs).

### Weaknesses / Limitations
- Developer preview; compatibility-breaking changes promised; no security audit (self-stated).
- Sandbox is same-kernel confinement; no isolation from host for untrusted workloads.
- Very high conceptual surface: the turn-flow description alone involves ~15 event types and multiple async admission phases; correctness depends on every listener calling `next()` and preserving decision fields.
- Single-user/local-first design; no multi-tenant, RBAC or fleet concepts visible.
- Plugin ecosystem discovery via a GitHub topic tag — supply-chain trust is left to the user.

### Visible vs Hidden Metrics
- **Visible:** large community metrics (repo metadata, unverified as to engagement quality); broad surface (several apps, two SDKs, dozens of packages); "everything replaceable".
- **Hidden:** cost of reversible-effect discipline on every contributor; ordering bugs in waterfall hooks; layered patch precedence that is hard to debug without `--dump-config`; session-format migration chain grows forever; a very large lockfile and a monorepo whose churn makes tracking upstream expensive; same-world sandbox gives a false sense of isolation.
- **Weighing:** the *patterns* (log-derived context, spill-with-locator, pruner-before-compaction, repeat-call guard, per-call timeouts, versioned session migrations) are cheap to adopt and independent of the framework. The *kernel* (reversible-effect plugin tree, layered patches) would be a rewrite for a Python/FastAPI multi-service system and its hidden costs outweigh the replaceability win for AutoBot.

## AutoBot Comparison: reference work → AutoBot

Audit: read-only sweep of `autobot-backend/` and `autobot_shared/` on origin/main (2026-10-23), plus `gh issue list --search` on open and closed issues for every pattern. Second sweep covered the SLM node agent, NPU worker and browser worker: none runs an agent loop; the SLM agent runs fixed-argv commands with timeouts; the browser worker's `evaluate` action is unbounded in time and size (#19303).

### Pattern-by-pattern verdict

| # | Pattern | AutoBot today | Existing issue | Delta | Verdict |
|---|---|---|---|---|---|
| 1 | Model context derived from an append-only log | PARTIAL — session file rewritten whole (`chat_history/file_io.py` `_atomic_write`); LLM context projected as `{user, assistant}` prose pairs (`chat_history/turn_projection.py`); system/RAG prompt not logged | #17229 (no durable run record), #17277 (prompt drift) | Exact per-request reconstruction | adopt-with-conditions — as an AC on #17229, not a new log |
| 2 | Tool-result spill + locator, keep original on failure | EXISTS, off by default — `agent_loop/tool_output_spill.py` `spill_if_oversized`, `read_spilled_output`; write failure keeps full output | #16617 umbrella (+#16618, #16620–#16624) | Enable by default — tracked | already covered |
| 3a | Prune tool results before summarizing | PARTIAL — `_clip_tool_results` at 400 chars, summarized region only (`chat_history/context_overflow.py`) | #16624, #16621 | — | already covered |
| 3b | Manual `/compact` | PARTIAL — `POST /chat/summarize` exists; no slash command (`slash_command_handler.py` `CommandType`); endpoint pins a hosted model | **#19290 (filed this session)** for the model literal | Slash command wiring | adopt (trivial), after #19290 |
| 3c | Image placeholder when a route rejects images | ABSENT (no hit for image-placeholder / vision-rejection patterns) | none | Whole feature | adopt-with-conditions — only once image input reaches chat routes; low priority |
| 4a | Repeat-identical-tool-call guard | EXISTS — `autobot_shared/repetition_guard.py`, `chat_workflow/tool_dispatch_guards.py` `enforce_repetition`, `agent_loop/loop.py` `_check_tool_call_repetition`; halts rather than reminds | — | Soft reminder first | rejected-by-hidden-metrics — a reminder costs extra turns; the hard halt plus stagnation guard is stricter |
| 4b | Per-tool-call timeout returning a clear error | PARTIAL — `tools/parallel/executor.py` `_execute_tool_with_timeout`; `tool_timeout_ms` declared, unread; live chat dispatch has turn timeout only | #17469 (agent loop only) | Live chat dispatch path | adopt — extend #17469's scope (comment), not a new issue |
| 5a | OS confinement of shell commands | ABSENT — agent terminal runs in a host PTY (`services/agent_terminal/command_executor.py`) | #18302 (bubblewrap, fail closed — owner decision 2026-10-11), #18211, #13595 | — | already covered |
| 5b | One-time user-approved escalation on a sandbox denial | ABSENT | — | — | **rejected by recorded decision** — #18302 says no user can widen the profile |
| 5c | read-only / workspace-write / full modes | PARTIAL — `PermissionMode` (`autobot_shared/ssot_config.py`) gates approvals, not confinement | #18302 | Map modes onto the bwrap profile | needs-decision — options posted on #18302 (recommended: per-mode profiles, PLAN read-only) |
| 6 | Durable per-session goal with model tools and auto-continuation | ABSENT — nearest is `SessionWorkItemBinding` (`chat_workflow/session_work_item.py`, Redis, 24 h TTL) and LLC `update_goal` (company goals) | none | Whole feature | adopt-with-conditions — build on the work-item binding (one system of record via `store_authority`), never a parallel goal store; continuation needs the #18134 tree bound first |
| 7 | Versioned session format, adjacent migrations, never overwrite source | ABSENT — no version field in session JSON; repairs are in-place backfills (`chat_history/session_scope_backfill.py`); `TaskContext.SNAPSHOT_VERSION` rejects instead of migrating | none | Whole feature | adopt — directly serves the no-data-loss-on-update rule |
| — | Reversible plugin registrations | ABSENT host-side — `loader.py` `unload_plugin` removes registry entries only; `call_hook` (`hooks.py:248-292`) ignores status; `disable()` (`base.py:213`) flips a field; `revoke_capabilities` uncalled; reload does not re-import | **#19302 (filed)**; related #17421, #17459, #13231 | Host-tracked, host-reversed registrations | adopt — the reference work's reversible-effect idea, scoped to hooks/tools/grants only |

### What We Already Do Better
- **Approval and permission plane:** risk tiers, approval memory, five permission modes and DB-persisted approval gates (`secure_command_executor.py`, `chat_workflow/tool_permission_gate.py`) — the reference work has prompt-level approvals only.
- **Repetition guard keyed on (call, result) with a stagnation guard and pollable-tool exemptions** — stricter than an advisory reminder.
- **Multi-tenant, multi-node, RBAC** — the reference work is single-user and local-first.
- **Spill anchor bound to its run** (`bind_task`) — the reference work's locator carries no such binding in its docs.

### Gaps & Opportunities (prioritized)
1. **Versioned session storage with adjacent migrations** (pattern 7) — new issue; moderate effort; protects user data across updates.
2. **Durable per-session goal** (pattern 6) — new issue; significant effort; depends on #18134.
3. **`/compact` slash command** (pattern 3b) — new issue or append to #16617; trivial after #19290.
4. **Live chat per-tool timeout** (4b) — comment on #17469.
5. **Exact request reconstruction** (1) — AC on #17229.
6. **Image placeholder fallback** (3c) — new issue, low priority.

### Specific Code/Files Affected
- `autobot-backend/chat_history/session.py`, `file_io.py` — version field + migration chain (7)
- `autobot-backend/chat_workflow/session_work_item.py`, a new goal tool beside `llc/agent_tools.py` (6)
- `autobot-backend/slash_command_handler.py`, `api/chat.py` summarize handler (3b, #19290)
- `autobot-backend/chat_workflow/tool_dispatch_guards.py` / dispatch path (4b)
- `autobot-backend/chat_history/context_overflow.py` (3c)
