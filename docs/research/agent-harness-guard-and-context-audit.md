# Agent harness comparison — guards, context sizing, and ingest governance

**Date:** 2026-08-11
**Source:** an external self-hosted multi-agent harness (JVM stack, single-deployment,
multi-channel, permissive licence, a few months old and still stabilising its streaming
path). Repo name, vendor and locating metadata are withheld per the no-external-names rule
for committed docs; the URL was supplied in-session. Star counts and creation dates are
omitted deliberately — together they identify the repository as surely as its name does.
**Scope:** `chat_workflow/`, `agent_loop/`, `autobot_shared/repetition_guard.py`,
`security/command_patterns.py`, `context_window_manager.py`, `services/gateway/`,
`services/skill_management/`, `middleware/hooks.py`.
**Method:** the source is not adoptable as code — wrong language, wrong framework, wrong
stability profile — so only *designs* were considered. Every candidate was checked against
our own code before being filed; capabilities we already have are recorded in
"Already covered" and were deliberately **not** filed. All paths below are repo-relative
from the root, and all line numbers are against `Dev_new_gui` at `d018373e1`.
**Filed as:** #14027, #14028, #14029, #14030, #14031. Premise correction on #13587,
design input on #13250.

> **Corrected 2026-08-11 after review.** The first version of this doc carried seven
> off-by-a-few line citations and three grep claims that did not return what they said they
> returned — including one that asserted an *empty* result never obtained. All five findings
> survived correction, and two of them (#14028, #14029) got **stronger** once the evidence
> was stated accurately. The corrections are kept inline rather than rewritten away, because
> a doc that will be cited as evidence of what was audited has to show where its evidence
> was wrong. See "Corrections" at the end.

**The through-line:** AutoBot's loop-guard machinery is, where it runs, better than the
source's. The gaps are at the edges the loop does not own — the *normalization* of what a
guard matches on, the *sizing* of the context window, the *ingest* seam ahead of the router,
and a package of built guards with no production caller.

---

## Already covered — audited, confirmed present, NOT filed

| Capability | Where it lives | Note |
| --- | --- | --- |
| Identical-call loop detection | `autobot-backend/chat_workflow/graph.py:169` `_detect_tool_call_loop`; warn via `_inject_mid_conversation_warning` (`:348`); abort at `_LOOP_ABORT_THRESHOLD` (`:56`, checked `:1127`, also `:1157`, `:1504`) | warn-then-halt already graduated |
| Repetition guard | `autobot_shared/repetition_guard.py`, wired at `autobot-backend/chat_workflow/tool_handler.py:3137` `_enforce_repetition` (import `:3155`, call `:3166`) | **stronger than the source** — see below |
| Stagnation / novelty guard | `stagnation_halt_reason`, same seam | **no counterpart in the source** |
| Orphaned tool-pair sanitizing | `autobot-backend/chat_history/context_overflow.py:164`, applied `:251` | drops orphaned tool messages and dangling `tool_calls` |
| Fact forcing | `autobot-backend/chat_workflow/tool_handler.py:3096` | blocks the first edit to an uninvestigated file |
| Config protection | `autobot-backend/chat_workflow/tool_handler.py:3061` | blocks writes weakening linter/formatter gates |
| Provider failover | `autobot-backend/circuit_breaker.py`, `llm_shared/model_fallback_coordinator.py`, `llm_shared/provider_registry.py:204` `health_check_all` | |
| Execution leases | `autobot_shared/leader_lease.py` (Redis SETNX + TTL) | used by the distillation and connector schedulers |
| Lifecycle hook bus | `autobot-backend/middleware/hooks.py:15` — 25 hook points, **all 25** with live call sites (21 in `chat_workflow/llm_handler.py`, the rest in `chat_workflow/session_handler.py`) | **more than the source's 7 event types** |
| Multi-section context allocation | `autobot-backend/context_window_manager.py:279` `allocate_sections` (#13640) | **no counterpart in the source** |
| Feature flags | `autobot-backend/api/feature_flags.py` | |

### Where our design is better, and why

**Repetition keyed on `(call fingerprint, result hash)`.** The source keys on
`toolName + sha256(args)` alone, and therefore needs a hard-coded read-only tool allowlist
(`read_file`, `web_search`, …) to avoid halting legitimate repeated calls. Our pair key makes
that exemption *structural*: the count resets the moment the result moves, so a polling loop
survives any threshold with no allowlist to maintain. Their list will drift as tools are
added; ours cannot.

**The stagnation guard has no counterpart at all.** The source catches one call re-issued. It
has nothing for a run of *different* calls whose results carry no new information — a distinct
failure mode that `stagnation_halt_reason` scores by novel-token ratio over a window with an
accumulating vocabulary.

**One tunable posture.** `AUTOBOT_GUARD_PROFILE` resolves every guard's thresholds from a
single profile. The source hard-codes `WARN_AFTER`/`HALT_AFTER` constants per detector.

**Architecture-family-aware compression bypass** (#7351) — non-transformer families (SSM,
linear-attention, hybrid) skip the 4K/8K trigger. No equivalent.

---

## Filed gaps

### Gap 1 · #14027 — guard patterns match un-normalized input *(security, wave 1)*

`autobot-backend/security/command_patterns.py` is the single source of truth for
dangerous-command detection, and it matches raw text: `is_dangerous_substring` (`:394`) only
lowercases; `check_dangerous_patterns` (`:411`) searches the unmodified string;
`is_dangerous_command` (`:430`) composes the two. A homoglyph (fullwidth `m`), an
ANSI-wrapped command, or an embedded NUL bypasses every pattern.

`strip_ansi_codes` exists (defined `autobot-backend/utils/encoding_utils.py:199`, re-exported
`utils/command_utils.py:38`) but is applied to command **output**, never to the command
**before** matching. Grep for `NFKC|unicodedata.normalize` returns two repo-wide hits, neither
on this path (`auth_rbac_admin_guard_test.py:109`; `knowledge/adapters/okf_adapter.py:148`,
which is NFKD).

Reachable via three live paths that carry attacker-influenced text into a loop with shell
tools: the KB web crawler, document ingest, and the browser agent.

Fix: normalize (ANSI strip → C0 strip → NFKC → whitespace collapse) **for matching only**,
never mutating the executed string.

### Gap 2 · #14028 — inbound ingest has no bot-self filter, dedup, or recursion guard *(wave 1)*

**`services/gateway/` contains two disjoint adapter stacks**, and the finding applies to both:

| Stack | Entry point | Routes via |
| --- | --- | --- |
| `channel_adapters/` (`base.py`, `websocket_adapter.py`) | `Gateway.receive_message` (`gateway.py:263`), reading `self._channel_adapters` (`:73`) | `message_router.py` (`gateway.py:326`) — the only path that reaches it |
| `adapters/` — **9** platform adapters (web, slack, discord, whatsapp, teams, telegram, signal, matrix, imessage; `gateway_manager.py:67-75`) | `GatewayManager.normalize_message` (`:99`) | its **own** `route_message` (`:163`), which never touches `message_router.py`. Live callers: `api/telegram_bot.py:41`, `api/whatsapp.py:51` |

`grep -rnE "bot_id|is_bot|self_.*message|dedup|seen_.*id|recursion" autobot-backend/services/gateway/`
returns **zero hits**. Rate limiting is real but surfaces under different names
(`gateway.py:285`, `session_manager.py:194`, `config.py:33-34`) — and rate limiting bounds the
*volume* of a feedback loop without preventing one, and does not deduplicate a redelivered
message.

Open failure modes: self-reply loops (the platform echoes our own post back as a user turn),
duplicate delivery on webhook retry producing two agent turns and double tool side effects,
and unbounded agent-to-agent recursion. Nothing errors and nothing alerts — the loop quietly
bills tokens.

**The governance stage belongs on the platform seam** (`gateway_manager.py:99`/`:163`), not on
`message_router.py` — the 9 platform adapters never reach the latter. Applying it in one place
per stack is the only way a newly added adapter inherits it.

**Spun out of this:** two adapter stacks under one gateway, with two independent routing paths,
is itself a consolidate-never-fork finding. Recorded here; not separately filed.

### Gap 3 · #14029 — context-window sizing has no learned tier, and four static sources can disagree *(wave 1)*

The resolution chain in `autobot-backend/context_window_manager.py:575-584` is
**YAML → registry → YAML default**, not "YAML → 4096" as first written:

1. `config/context_windows.yaml` (`:117`), returning `context_window_tokens` (`:577`);
2. `_query_known_context_length` → `llm_shared.model_param_registry` (`:579`), scaled by
   `_CONTEXT_HEADROOM = 0.85` and capped at `_CONTEXT_HARD_MAX = 200_000` (`:26-27`);
3. otherwise the YAML `default` model's value, falling back to `4096` (`:584`; also `:169`,
   `:178`). Separately, `get_compression_threshold` falls back to `8192` (`:545`, `:554`).

**What is genuinely missing is the *learned* tier**, and the real finding is larger than a
single fallback: **four static sources can each state a context size, and nothing reconciles
them.** Besides the YAML and the registry —

- a per-model `max_model_len` table in `llm_shared/providers/vllm.py:246-270` (4096/8192
  literals), plus `self.max_model_len` from config (`:49`, used `:77`, `:157`);
- the `num_ctx` actually sent per request — `llm_shared/providers/ollama.py:120` from
  `ModelConfig.DEFAULT_NUM_CTX` (`chat_workflow/llm_handler.py:1008`,
  `chat_workflow/manager.py:2019`), and a hard-coded `num_ctx: 2048` in
  `knowledge/base.py:255`;
- `llm_shared/models.py:67` declaring the `num_ctx` field default.

Grep confirms the *parser* half is absent: `maximum context length|context_length_exceeded`
returns nothing on this path, and there is no `/api/show` call anywhere — the only Ollama
metadata call is a liveness check (`startup_validator.py:311`). `llm_shared/providers/ollama.py`
is otherwise a full provider (`chat_completion:489`, `stream_response:386`), so the accurate
claim is **no capability/metadata probe**, not "no Ollama calls".

Both directions fail silently — a 32k model sized as 4k is compressed for no reason (quality
loss, never an error), and one sized too high returns a 400 every turn until a human edits
YAML. This hits every local and self-hosted model, which is the deployment shape we ship.

The transferable trick: **the serving stack states its own limit in the text it rejects with.**
Parse it once and every later turn is correct. Two details make the parser correct rather than
merely present — anchor each pattern on the *limit keyword* so
`"requested 50000 … maximum … 32768"` yields 32768 and not 50000, and band the result so an
implausible parse falls through instead of raising the assumed window into a hard failure.
`_CONTEXT_HARD_MAX` already supplies the upper half of that band.

### Gap 4 · #14030 — skill distillation cannot see recurrence *(wave 2, gated)*

`autobot-backend/services/skill_management/skill_extractor.py:86` takes a single conversation;
the scheduler feeds them one at a time. Within one window, a habitual request and a one-off
task are indistinguishable, and the reviewer is *right* to decline writing a skill for a
one-off — so "I ask this every week" can never reach it. No prompt change recovers the signal;
it needs a cross-session pass keyed on distinct conversations **and distinct days**.

The transferable discipline is the second half: **recompute each sweep from scratch over the
lookback window instead of incrementing counters.** Re-runs become idempotent and an abandoned
routine decays out on its own, with no expiry job.

**Gated, deliberately.** `AUTOBOT_SKILL_DISTILLATION_ENABLED` defaults to `False`
(`skill_distillation_scheduler.py:46`). Building a recurrence miner for a pipeline nobody has
turned on adds maintained-but-dormant surface — the #13685 shape.

### Gap 5 · #14031 — the dormant-loop problem is known (#11221); what is new is narrower *(child of #13587)*

`AgentLoop` has no production instantiation. **This is already documented in-code and under a
closed issue** — `autobot-backend/agent_loop/__init__.py:11-15`:

> NOT WIRED IN PRODUCTION (#11221): ``AgentLoop`` is never instantiated by any production
> caller — the live tool seam is ``chat_workflow._dispatch_tool_call``.

**#11221 is CLOSED** ("decide wire vs port vs document"), resolved as *document*. So the
existence of the dormant loop is not a discovery, and this doc does not claim it as one.

What is new is narrower, and is what #14031 is actually for:

- `PreActionVerifier` is reachable only from that dormant loop
  (`agent_loop/loop.py:191-192`, `:1668`), and `pre_action_verifier_enabled` defaults to
  **`True`** (`agent_loop/types.py:266`) — so it reads as an *active* guard while executing on
  no request. A disabled-by-default dormant component is honest; an enabled-by-default one
  invites exactly the miscount below.
- `BeliefState` / `BeliefStateUpdater` likewise (`agent_loop/loop.py:28`, `:186`, `:644`,
  `:699`, `:1350`, `:1385`), with `belief_state_enabled` defaulting to `False`
  (`agent_loop/types.py:258`) — off *and* unreachable.
- **#13587's "Already covered — NOT filed" list miscounts both**, citing `agent_loop/loop.py`
  for the pre-action verifier and for durable run checkpointing. Documenting a dormant module
  (#11221) did not stop a later audit from reading it as live coverage.

For accuracy: `grep -rn "from agent_loop.loop import\|AgentLoop("` returns two non-test hits
besides the tests — `agent_loop/__init__.py:38` (package re-export) and `:28` (docstring
example). Neither is an instantiation, so the conclusion holds; the earlier "only test files"
wording did not.

#13590 (CLOSED) is the template for the fix, and it is worth stating as a rule: **do not wire
the dead entry point in — extract the decision logic into `autobot_shared/` as a
dependency-free pure function, call it from the live seam, and add a wiring assertion so the
next refactor cannot silently un-wire it.** `repetition_guard` and `fact_forcing` both took
that route. #13919 and #13997 are the same extraction over the rest of the package; one pass
beats three.

---

## Design input, not filed as an issue

**Two-tier safety floor** → posted on #13250. A frozen, startup-built pattern floor returning
`PASS` / `FORCE_HUMAN` / `HARD_BLOCK`, evaluated *before* any grant lookup. Today
`is_dangerous_command` (`security/command_patterns.py:430`) computes severity but uses it only
to pick the message wording — there is no tier meaning "no approval path may execute this".
Filed as a comment rather than an issue **on purpose**: as a standalone addition it becomes a
fifth approval mechanism, which is the problem #13250 exists to remove. #14027 is a practical
prerequisite — a floor matching un-normalized input inherits the same bypass.

## Deliberately NOT proposed — do not re-file

- **Progressive tool disclosure** — already evaluated and rejected at our scale.
- **The source's contradiction detector** — string-overlap only, self-labelled EXPERIMENTAL
  and shipped default-off. Our `ContradictionRecord` (defined `agent_loop/types.py:482`, used
  via `agent_loop/belief_state.py:22`) is a better starting point.
- **Its IM-channel set and publishing pipeline** — market-shaped, no fit.
- **Anything requiring its JVM framework stack.**

## Corrections

Applied 2026-08-11 after a `code-reviewer` pass that re-ran every citation. Recorded because
the failure mode is instructive, not just to log the churn.

| # | Was | Is |
| --- | --- | --- |
| 1 | `graph.py:1121` abort check | `:1127` (`:1121` is a comment) |
| 2 | repetition guard wired at `tool_handler.py:3163` | `_enforce_repetition` at `:3137`, call at `:3166` (`:3163` is the `ctx is None` no-op) |
| 3 | `context_overflow.py:163` / `:248` | `:164` / `:251` |
| 4 | `8192` fallback at `context_window_manager.py:519` | `:545` and `:554` (`:519` is a docstring) |
| 5 | `strip_ansi_codes` "exists at `command_utils.py:38`" | defined `utils/encoding_utils.py:199`; `:38` is a re-export |
| 6 | `skill_distillation_scheduler.py:44` | `:46` |
| 7 | `ContradictionRecord` in `belief_state.py` | defined `agent_loop/types.py:482` |
| 8 | "grep for `max_model_len\|num_ctx` returns nothing" | **false** — 12+ non-test hits. Only the error-message parser is absent. Correcting this *enlarged* #14029 from one bad fallback to four unreconciled sources |
| 9 | "the only Ollama call is a liveness check" | false — full provider; the true claim is no capability/metadata probe |
| 10 | #14029 chain "YAML → 4096" | YAML → registry → default, with `_CONTEXT_HEADROOM`/`_CONTEXT_HARD_MAX` |
| 11 | #14028 "10 platform adapters … route via `message_router.py`" | 9 adapters, on a **separate** stack that never reaches `message_router.py` |
| 12 | #14028 grep "returns only rate-limit hits" | returns **zero** hits; rate limiting surfaces under other names |
| 13 | #14031 "grep returns only test files" | two non-test hits (re-export, docstring); no instantiation |
| 14 | #14031 presented as a fresh discovery | already documented in-code under **#11221 (CLOSED)**; the new part is the enabled-by-default verifier and #13587's miscount |

Two lessons worth carrying, both instances of patterns already in our own guidance:

- **An empty result reads as a clean result — including one you never actually obtained.**
  Claim 8 asserted an empty grep. The original command had been truncated by `head`, so the
  absence was an artifact of the pipeline, not of the codebase. Paste the command *and* its
  real output, or do not claim the absence.
- **A citation is evidence only if it resolves.** Seven line numbers drifted by 1–26 lines
  because they were taken from a grep index rather than re-read at write time. For a doc meant
  to stop the next audit re-deriving this, an off-by-six citation is worse than no citation —
  it looks checkable and is not.
