# Research: evidence-first recoverable agent runtime + vendor model gateway

Status: Phase 1 + Phase 2 complete (2026-10-11); issues filed (#18293–#18307, see "Filed" below).
Anonymized per research-skill rule — source identity lives only in the chat reply.

## Source Analysis: a multimodal-model vendor's open agent harness and research releases

### What It Is
A vendor that trains its own text/image/video models sells them through a free-tier
chat-completions-compatible gateway and publishes ~28 public repos. Most are model cards,
paper landing pages or integration "skills" for third-party agents. The one with real
engineering substance is an **agent harness**: TypeScript/Node 24, pnpm monorepo, Apache-2.0,
~107 stars, self-described *developer preview (pre-alpha)*, macOS-only local checks,
PRs from invited internal developers only. A 35-page "as-built" tech report describes
how it is designed. Two short articles describe a **planner/helper multi-agent mode** that
improves itself from traces.

### Architecture & Key Patterns
- **Trusted Core, proposal-only edges**: clients (Web/CLI/TUI/SDK), models, tools and
  extensions can only *propose*. One core owns event order, policy, approvals, budgets and
  the final say on any external effect.
- **Append-only event ledger as the only authority**: model context, restart recovery, the
  UI trace timeline and evaluation are all computed from the same ledger. Snapshots are
  caches only. No consumer is allowed its own editable copy of the history.
- **"Effect Sandwich"**: a durable intent event → policy/approval → bounded execution →
  a durable outcome event. Each tool declares a replay contract (safe / idempotent /
  never-replay), and `unknown` is a first-class outcome after a crash.
- **Nested state machines with generation fencing**: an outer queue (concurrency, cancel,
  takeover) wraps an inner turn machine. A generation number stops a replaced worker
  from committing stale results.
- **Stamped context**: every model request carries a version/hash/provenance stamp built from
  durable resources, so context engineering can be reproduced and A/B-tested.
- **Shared sessions across surfaces**: a task started on the Web resumes in the terminal
  (`/resume <id>`) with its full history.
- **Plugin governance**: install shows version, source, integrity digest, capability hash
  and license. Enabling a plugin binds those hashes. Lifecycle: install, enable, update,
  roll back, remove, plus a check for leftover residue.
- **Approvals**: allow once, allow for the session, a persistent grant, or deny. Modes are
  manual / smart / off. The denial *reason* (rejected, timeout, no client connected, policy,
  stopped) goes to both the record and the model. Even with full permissions, the agent's
  own `secrets/`, `auth/` and `profiles/` stay read-only.
- **Command sandbox**: bubblewrap on Linux, Seatbelt on macOS. It fails closed with
  `SANDBOX_UNAVAILABLE`.
- **Loop verifier**: separates repeated *writes* from read-only polling, using the policy
  recorded for each call, and has a separate no-progress check.
- **Device protocol (MHS/MOS)**: its own WebSocket protocol for hardware. Devices register
  state, tools and data sources, and a hub checks every call against what the device
  declared. Real-time safety stays in the device layer.
- **Planner/helper MAS mode**: the planner writes *briefs* (a job plus checks the result
  must pass). The harness rejects briefs that break its rules. A learned *helper profile*
  (what the helper is good and bad at) guides delegation. Behaviours that prompts failed to
  change became **harness-enforced rules**, e.g. "the planner's terminal stays closed until
  the helper reports", which raised the delegation rate from 7% to 95%.
- **Codified prompting (paper repo)**: plans written as typed pseudocode with assertions.
  A failed assertion triggers a replanner agent.

### Notable Implementation Details
- Uncertainty is treated as state: after a crash mid-effect the outcome is `unknown`, and
  only effects marked safe or idempotent are replayed.
- "A worker process is not a sandbox": process isolation is described as fault containment
  only, never as a security boundary.
- Measure harness value causally: keep model, task, prompt, tools, budget and environment
  fixed, change one harness mechanism at a time, and keep the failures.
- "About 12% of 'done' reports failed their re-check": trust the re-check, not the report.
- A profile changes the behaviour it describes (round 1 over-delegated), so every learned
  change is re-tested on fresh tasks before it is kept.
- Research note (design only, nothing measured): a three-tier KV cache (GPU L1 / host L2 /
  cluster-shared L3 over RDMA) with recovery of the longest usable prefix, gated on benefit.

### Strengths
- Clear invariants, stated explicitly: one authority, a ledger as truth, effects recorded
  separately from messages.
- An honest evidence boundary in the README: it says what it is *not* (not a sandbox for
  plugins, not production, not a device certification).
- Learning that reaches enforcement, not just the prompt (rules derived from traces).
- Denial reasons and approval scopes are defined in detail and fed back to the model.

### Weaknesses / Limitations
- **The maturity claims contradict each other**: the tech report says the system is
  "complete / as-built release", while the README says pre-alpha with unstable APIs.
- Ordinary plugins run as **trusted in-process code** with no isolation, and the report's
  claim that "community code runs isolated" is aspirational relative to the README.
- Only checked on macOS. Linux and Windows have not been accepted.
- The structured-decision layer ("cerebellum") is still "integration in progress".
- The MAS results are internal, use a small sample (SWE-bench 15 issues), and rounds 4–5
  are targets, not results. The tech report gives no throughput, latency or success data.
- External contributions are closed. Most of the org is marketing, paper landing pages,
  or third-party wrappers around a free gateway (including a mass-signup "register bot" by
  a third party — a free-tier abuse signal).

### Visible vs Hidden Metrics
- **Visible:** 21.7% pass / 42.7 score on a public agent-system leaderboard (independently
  hosted, but the vendor submitted the run). MAS mode: 48% lower cost at the same
  score, and 13/15 vs 9/15 on SWE-bench (self-reported, internal, small n). Self-improving
  pipeline: compact model 0.241→0.556 partial credit on 198 held-out tasks (self-reported).
  Gateway: free omni-modal API with about 5.2k stars on the catalog repo.
- **Hidden:** adopting the *runtime* means a Node 24 / pnpm stack, pre-alpha APIs, a
  single-vendor contribution policy and macOS-only validation. The ledger-as-only-truth
  approach costs a lot of migration and storage: every consumer must be rewritten as a
  projection. The gateway risks lock-in, quota and pricing changes ("may change over
  time"), and its data residency is unclear (SG/CN sites).
- **Weighing:** the *code* is not worth adopting, because it is a different stack, pre-alpha,
  and plugins are not isolated. The *ideas* are worth taking: Effect Sandwich with replay
  contracts, generation fencing, stamped context, denial reasons fed back to the model,
  rules enforced by the harness and learned from traces, and checking delegated "done"
  reports. These ideas carry low lock-in and can be added one at a time.

### Untrusted-content scan
Fetched READMEs, tech report, MAS article and security guide: no instructions addressed
to an agent were found. The report's own note that embedded source instructions were
"treated as design content" is a disclaimer by the authors, not an injection.

---

## AutoBot Comparison: the reference work → AutoBot

Audited against `origin/main` @ f2e93ea392 by three read-only sweeps (2026-10-11).
**V** = re-verified by hand at origin/main this session; every other citation is as the sweep
reported it and must be re-checked before it becomes an issue body.

### What We Can Adopt

| # | Candidate | AutoBot today (audit) | Visible benefit | Hidden cost | Verdict | Effort |
|---|---|---|---|---|---|---|
| A1 | **One tool-effect SSOT** (read_only / mutating / destructive / replay: safe·idempotent·never) | Four separate classifications: `chat_workflow/code_exec/tool_policy.py:11,87`, `autobot_shared/tool_catalogue.py:46-56,82`, `tools/parallel/analyzer.py:24,38`, `autobot_shared/repetition_guard.py:43` (`POLLABLE_TOOLS` names). No replay flag anywhere. | One declaration feeds approval, parallel scheduling, loop detection and recovery | Retagging every tool. The forks must be retired, not wrapped with a fifth | **adopt**. This is the prerequisite for A2, and it also fixes the repeated-write vs polling gap | moderate |
| A2 | **Effect bracketing**: an intent record before and an outcome record after each mutating tool; `unknown` after a crash; replay only if safe or idempotent | ABSENT. Checkpoints are written only after the whole iteration (`agent_loop/loop.py:323`). In the chat graph, `execute_tools` is a single LangGraph node (`chat_workflow/graph.py:955`). `resume_run` has no production caller | A crash in the middle of a tool call becomes detectable, and no command runs twice by accident | One extra durable write per mutating call. Needs a UI path for resolving `unknown` | **adopt-with-conditions**: put it on the live chat path, not on the unwired AgentLoop (#14031); mutating tools only | significant |
| A3 | **Run-generation fencing**: a monotonic generation stored in Redis, checked with compare-and-set before checkpoint, persist or result commit | PARTIAL. HTTP idempotency already uses a real fencing token (`autobot_shared/idempotency.py:46,87,136`). Leases and claims exist (`leader_lease.py`, `scope_enforcement.py:382`). There is no generation per run or turn. `_checkpoint_run` is a plain SET, and `cancel()` only changes local state | A cancelled, taken-over or resumed run cannot overwrite a newer one | Small: one INCR plus a Lua CAS. The `idempotency.py` pattern can be reused | **adopt** | moderate |
| A4 | **Context manifest per turn**: template id+hash, KB chunk ids, memory ids, tiered-context sources, final prompt hash | ABSENT. Only display citations (`chat_workflow/manager.py:479-485`). Prompt hashes are used as cache keys only (`prompt_manager.py:703`). Langfuse ships raw prompts off-box when enabled | Turns become reproducible, and same-model A/B (#17279) gets a real input key | Storage per turn. Must store ids and hashes, never raw prompt text (disclosure) | **adopt-with-conditions**: ids and hashes only | moderate |
| A5 | **Typed denial reason returned to the model** (user_denied · timeout · no_client · policy · task_stopped, plus the user's comment) | PARTIAL. Policy denials are tagged (`tool_permission_gate.py:62-89`). For a user denial, the model gets the generic `"Command was denied or failed"` (`tool_handler.py:1849` **V**), because `approval_result` has no `error` key on a denial. The user's comment reaches UI metadata only | The model stops retrying something the user refused and can act on the user's stated reason | Little | **adopt** | trivial |
| A6 | **Delegation briefs with checks, re-checked by the parent** | PARTIAL (weak). `delegate` takes a free-text `task` and returns `str` (`delegation.py:216`); it is off by default (`:69`). `SuccessCriteriaEvaluator` exists but works per workflow only. Unknown criteria count as met (`orchestration/workflow_planning.py:498-500`, fail-open) | The parent checks the child's claim instead of trusting it (the reference work saw about 12% false "done" reports) | Low value while delegation is off. Belongs under the existing umbrella #17275 | **adopt-with-conditions**: as a child of #17275; the fail-open at `:500` is a separate defect, fix it now | moderate |
| A7 | **Rules enforced by the harness, learned from traces, adopted only after a paired A/B** | Hand-written runtime guards EXIST (`tool_dispatch_guards.py`). The trace → rule → paired eval loop is ABSENT. The eval harness scores drift, not task success (#17279), and the live candidate runner is a stub (`eval/candidates.py`) | The reference work's biggest reported wins came from this | With no trustworthy success metric, the loop would optimise noise | **rejected-by-hidden-metrics for now**; revisit after #17279 lands | significant |

### What We Already Do Better
- **Evidence discipline**: `agents/ac_verifier.py` / `ac_criteria.py:296` require a `file:line` citation that exists on origin/main before giving a verdict, and they return "can't tell" otherwise. That is stricter than the reference work's "trust the re-check" rule. The doctrine that separates nothing-found from did-not-look has no counterpart there.
- **No-progress detection**: a novelty-based stagnation halt (`agent_loop/fingerprint.py`, `repetition_guard.py:171-221`) plus a check keyed on fingerprint × result hash. That is richer than their repeated-write check; only the per-tool metadata is missing (A1).
- **Approval-pending semantics**: #13481 separates "stopped waiting, still actionable" from failure (`tool_handler.py:1858` **V**). The reference work folds timeout into denial.
- **Egress policy**: all outbound HTTP goes through a guarded fetch with recorded decisions. The reference work has no equivalent at the network layer.
- **Persistent per-project approval memory** (`services/approval_memory.py:247`) and five admin-gated permission modes.
- **Event doctrine**: one bus with declared stores of record (`store_authority`). We deliberately do not take the single ledger as the only truth (see below).

### Rejected
- **Ledger as the only authority** for context, UI, recovery and evaluation: AutoBot has at least 7 independently written history stores, and of the history stores, `store_authority.py` declares only `chat_sessions` (`:217-228`; it declares 17 concepts in total, per #17450). Migrating all of them is a large, cross-cutting change, and EVENT_STATE_DOCTRINE `:55` names agent context as an anti-goal. **Rejected by hidden metrics.** The adoptable remainder is to declare a system of record for each of the other stores, which is a store_authority follow-up.
- **The runtime code itself, the model gateway, and the device protocol**: a different stack, pre-alpha, vendor lock-in.

### Gaps & Opportunities (by impact)
1. **Security, already filed, so these are sightings, not new issues:** plugin `trust_tier` is self-declared and an `official` claim auto-grants capabilities (`plugin_manager.py:276` **V**). Lives in #17280. Granted capabilities are never checked: #17459.
2. **The main agent shell runs on the host PTY with no OS sandbox.** `SecureCommandExecutor(use_docker_sandbox=False)` is the default; only `compose` is sandboxed, and it fails closed. Under BYPASS, the shell can write the agent's own secrets, `.env` and permission state; the file tools refuse these, the shell does not. **Needs a decision**: bubblewrap vs Docker per command vs keeping host execution. Overlaps the sandboxed-VM research (#11059 and related).
3. A5, then A1 → A3 → A2, then A4. That order is cheapest-first, and each step unblocks the next.
4. **ACP sessions cannot resume Web sessions** (`acp/protocol.py:100`, `loadSession: False`). A small gap for cross-surface work.

### Incidental defects found by the sweeps (verify and dedupe before filing)
| Defect | Evidence | State |
|---|---|---|
| The `AUTOBOT_VLLM_PREFIX_CACHING` toggle is inert: `LLM(...)` is never passed `enable_prefix_caching` | `llm_shared/providers/vllm.py:96-104` **V**; setting at `ssot_config.py:1917` **V**. With `vllm>=0.29` (`requirements-gpu.txt:25`), whether prefix caching defaults on depends on the vLLM version, so the impact is unknown until checked against the installed version | not filed (searched "prefix caching vllm") |
| Workflow success criteria fail open on an unknown type | `orchestration/workflow_planning.py:498-500` | sweep-reported |
| `RLRouter.record_outcome` has no production caller, so the Q-table never learns | `agents/agent_orchestration/rl_router.py:140` | sweep-reported |
| `CostRouter` cannot be reached (`registry.get_active_router` has no caller) | `llm_shared/tiered_routing/cost_router.py:55` | sweep-reported; overlaps #16524 |
| The GOAP plan builder has no production caller, so the replan branch cannot run | `orchestration/workflow_planning.py:518` | sweep-reported |
| ACP `request_permission` has no call sites | `acp/server.py:195-232` | sweep-reported |
| Permission modes PLAN and ACCEPT_EDITS are not enforced by the matcher | `services/permission_matcher.py:292-301` | sweep-reported |
| Marketplace uninstall removes only a Redis set member: files stay and capabilities are not revoked | `api/marketplace.py:551` | sweep-reported; may belong to #17280 |

### Specific Code/Files Affected
- A1: `autobot_shared/tool_catalogue.py` becomes the SSOT. The forks in `code_exec/tool_policy.py`, `tools/parallel/analyzer.py` and `repetition_guard.py` (`POLLABLE_TOOLS`) are retired onto it.
- A2/A3: `chat_workflow/graph.py` (`execute_tools`), `chat_workflow/tool_handler.py`, and a new effect journal store declared in `autobot_shared/store_authority.py`. Fencing reuses the CAS in `autobot_shared/idempotency.py`.
- A4: `chat_workflow/manager.py` (turn persistence), `prompt_manager.py` (expose template hash), `tiered_context_sources.py` (emit source ids).
- A5: `chat_workflow/tool_handler.py:1824` `_handle_approval_failure` and `services/agent_terminal/models.py` (the denial result shape).
- A6: `chat_workflow/delegation.py`, `orchestration/success_criteria.py`, `orchestration/workflow_planning.py:500`.

### Issue overlap map (searched 2026-10-11, open + closed)
| Item | Existing home | Placement |
|---|---|---|
| A1 tool-effect SSOT | #13587 umbrella ("governance is name-scoped"); adjacent: #13589, #17463 (three approval policies), closed #11662 (consolidated only the code-exec classification) | new child of #13587 |
| A2 effect bracketing | #17227 (internal tool dispatch has no replay protection); #17234 (owner ruling on the default); closed #11175 (AgentLoop resume, unwired) | append to #17227 as its mechanism; link #17227 as a sub of #13587 |
| A3 run-generation fencing | none. Adjacent: #17227, #17273 (a disconnected client leaves the turn running) | new child of #13587, blocked_by A1 |
| A4 per-turn context manifest | #17271 umbrella; #17277 (prompt drift) and #17279 (eval) would consume it | new child of #17271, related to #17277 |
| A5 typed denial reason | none direct. #13413 umbrella (approval-surface gaps); adjacent: #17463, #13250 | new child of #13413 |
| A6 delegation briefs and re-check | #17275 umbrella (durable delegation) | new child of #17275 |
| A6 fail-open criteria (`workflow_planning.py:498-500`) | #17495 instance 3, already filed | sighting only |
| A7 harness rules learned from traces | blocked by #17279 | defer; if filed, child of #17271 blocked_by #17279 |
| Ledger: undeclared history stores | #17450 (persisted concepts with no declared system of record) | append the 6 history stores to #17450 |
| Host-PTY shell with no sandbox, shell writes secrets under BYPASS | none. Adjacent: #13595 (file tools have no workspace boundary), #13589 | new security issue under #13587, `needs-decision` |
| Plugin trust_tier self-declared | #17280; #17459 | sighting only |
| Marketplace uninstall residue and no capability revoke | #13231 (covers cleanup) | append "revoke capabilities" to #13231 |
| ACP cannot load sessions | closed #14825 (ACP surface) | new standalone issue |
| vLLM prefix-caching toggle inert | none | new bug; first check prefix-caching defaults on the installed vLLM version |
| CostRouter unreachable | #16524 umbrella (LLM pipeline) | new child of #16524 |
| RLRouter never learns | none; adjacent #13594 (capability profiles are literals) | new child of #13587 |
| GOAP builder unreachable; ACP request_permission dead; PLAN/ACCEPT_EDITS not enforced | none found; PLAN/ACCEPT_EDITS may fall under #17463 | check #17463's body before filing |

### Are the 7 history stores forks? (verified at origin/main, 2026-10-11)
**One real fork: conversation turns are written to two independent durable stores.**
| Store | Holds | Read by | Fork? |
|---|---|---|---|
| `chat:session:{id}` plus the session JSON file (`chat_history/`) | Full GUI message list | UI reload | **Fork A.** Declared in `store_authority` as `chat_sessions` |
| `data/conversation_transcripts/{id}.json` (`chat_workflow/conversation.py:112,170`) | `{timestamp,user,assistant}` per exchange, no TTL | LLM context fallback (`:60-69`) | **Fork B.** Undeclared second durable copy of the same turns |
| `chat:conversation:{id}` Redis, `conversation_history_ttl` 24h (`:87-99`) | Last turns for LLM context | LLM context (`:37-66`) | Not a fork: a TTL cache of B, warmed from B (`:75`) |
| LangGraph `AsyncRedisSaver`, 30-day TTL (`graph.py:1608`) | Per-turn execution state (`ChatState`: user_message, llm_response, workflow_messages) | Approval interrupt/resume | Not a fork: a different concept that overlaps only the current turn |
| `autobot:run:checkpoint:*` (`agent_loop/loop.py:103`) | AgentLoop `TaskContext` | `resume_run`, no production caller | Not live (#14031) |
| Event streams and channel replay streams | Capped delivery buses | UI | Not forks: projections, per EVENT_STATE_DOCTRINE |

**Evidence that A and B diverge in practice:** `chat_history/session_reply_backfill.py` exists because, before #13214,
streamed replies reached B but never A, so turns were lost from the UI. The repair reconstructs A from B, and
its docstring calls B "the actual source of truth for anything old enough to need this repair". That contradicts
`store_authority`, which names A. The B path literal is copied in two places (`session_reply_backfill.py:59`
says so). Open #13293 is the backfill chore only; no issue covers retiring the fork. **To file:** one store of
record for conversation turns (A), with LLM context projected from A, B retired onto it, and the fork recorded under #17450.

### Filed (2026-10-11)
#18293 (turn-store fork, under #17450) · #18294 (tool-effect SSOT, under #13587) · #18296 (RLRouter never learns) ·
#18297 (routing strategy inert, under #16524) · #18298 (GOAP unreachable) · #18299 (ACP approvals never reach client) ·
#18300 (PLAN/ACCEPT_EDITS inert, under #13413) · #18301 (vLLM prefix-caching toggle inert) · comment on #13231 (uninstall keeps grants).
Sightings not refiled: #17495 instance 3, #17280, #17459.

## Linked issues

Issues this research produced or is the analysis for (#18967). Each one links back to this document.

- #18293 — canonical(state): every chat turn is persisted twice — chat_sessions and an undeclared transcript store, already diverged once (closed)
- #18294 — canonical(tools): tool-effect classification is forked across four name lists that already disagree — derive all from tool_catalogue (closed)
- #18296 — bug(agents): the Q-learning router is consulted on every request but never learns — record_outcome has no caller
- #18297 — bug(llm): AUTOBOT_LLM_ROUTING_STRATEGY is inert — the live path bypasses get_active_router, so CostRouter and LatencyRouter are unreachable
- #18298 — bug(orchestration): GOAP replanning can never run — build_goap_workflow_plan has no caller, so no plan ever carries is_goap_plan
- #18299 — bug(acp): approvals in an ACP-driven turn never reach the client — request_permission has no call site
- #18300 — security(permissions): PLAN and ACCEPT_EDITS modes are inert — PLAN promises gated writes but behaves as DEFAULT
- #18301 — bug(llm): the vLLM prefix-caching setting is never passed to the engine — the toggle has no effect
- #18302 — security(shell): the agent shell runs on the host unsandboxed — run each command in a fail-closed bubblewrap namespace
- #18303 — feat(approval): the user's denial reason reaches the model as a typed result, not "Command was denied or failed"
- #18304 — feat(agent): run-generation fencing — a cancelled or superseded run can never checkpoint, persist or commit a result
- #18305 — feat(observability): a per-turn context manifest — ids and hashes of everything that fed the prompt, never raw text
- #18306 — feat(delegation): briefs carry acceptance checks and the parent re-checks the child's structured result (deferred)
- #18307 — feat(agent): harness rules learned from traces, adopted only after a paired A/B (deferred)
