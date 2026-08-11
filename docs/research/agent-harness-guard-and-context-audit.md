---
tags:
  - research
  - agents
  - security
aliases:
  - Agent Harness Guard and Context Audit
---

# Agent harness comparison — guards, context sizing, and ingest governance

Comparative audit of AutoBot's agent execution seam against an external
self-hosted multi-agent harness (JVM stack, single-deployment, multi-channel).
The source is not adoptable as code — wrong language, wrong framework, and a
release cadence still stabilising its streaming path — so only *designs* were
considered. Every item below was checked against AutoBot's own code before being
filed; capabilities AutoBot already has are recorded in "Already covered" and were
deliberately **not** filed.

**The through-line:** AutoBot's loop-guard machinery is, where it runs, better
than the source's. The gaps are at the edges the loop does not own — the
*normalization* of what a guard matches on, the *sizing* of the context window,
the *ingest* seam ahead of the router, and the fact that a whole package of built
guards has no production caller.

Filed: #14027, #14028, #14029, #14030, #14031. Premise correction on #13587,
design input on #13250.

---

## Already covered — audited, confirmed present, NOT filed

Each verified against the code on `Dev_new_gui`, 2026-08-11.

| Capability | Where it lives | Note |
|---|---|---|
| Identical-call loop detection | `chat_workflow/graph.py:169` `_detect_tool_call_loop`; warn via `_inject_mid_conversation_warning` (`:348`), abort at `_LOOP_ABORT_THRESHOLD` (`:56`, `:1121`) | warn-then-halt already graduated |
| Repetition guard | `autobot_shared/repetition_guard.py`, wired at `chat_workflow/tool_handler.py:3163` | **stronger than the source** — see below |
| Stagnation / novelty guard | `stagnation_halt_reason`, same seam | **no counterpart in the source** |
| Orphaned tool-pair sanitizing | `chat_history/context_overflow.py:163`, applied `:248` | drops orphaned tool messages and dangling `tool_calls` |
| Fact forcing | `chat_workflow/tool_handler.py:3096` | blocks the first edit to an uninvestigated file |
| Config protection | `chat_workflow/tool_handler.py:3061` | blocks writes weakening linter/formatter gates |
| Provider failover | `circuit_breaker.py`, `llm_shared/model_fallback_coordinator`, `provider_registry.health_check_all` | |
| Execution leases | `autobot_shared/leader_lease.py` (Redis SETNX + TTL) | used by the distillation and connector schedulers |
| Lifecycle hook bus | `middleware/hooks.py` — 25 hook points, all with live call sites in `chat_workflow/llm_handler.py` and `session_handler.py` | **more than the source's 7 event types** |
| Multi-section context allocation | `context_window_manager.py` `allocate_sections` (#13640) | **no counterpart in the source** |
| Feature flags | `api/feature_flags.py` | |

### Where our design is better, and why

**Repetition keyed on `(call fingerprint, result hash)`.** The source keys on
`toolName + sha256(args)` alone, and therefore needs a hard-coded read-only tool
allowlist (`read_file`, `web_search`, …) to avoid halting legitimate repeated
calls. Our pair key makes that exemption *structural*: the count resets the moment
the result moves, so a polling loop survives any threshold with no allowlist to
maintain. Their list will drift as tools are added; ours cannot.

**The stagnation guard has no counterpart at all.** The source catches one call
re-issued. It has nothing for a run of *different* calls whose results carry no
new information — a distinct failure mode that `stagnation_halt_reason` scores by
novel-token ratio over a window with an accumulating vocabulary.

**One tunable posture.** `AUTOBOT_GUARD_PROFILE` resolves every guard's thresholds
from a single profile. The source hard-codes `WARN_AFTER`/`HALT_AFTER` constants
per detector.

**Architecture-family-aware compression bypass** (#7351) — non-transformer
families (SSM, linear-attention, hybrid) skip the 4K/8K trigger. No equivalent.

---

## Filed gaps

### #14027 — guard patterns match un-normalized input *(security, wave 1)*

`security/command_patterns.py` is the single source of truth for dangerous-command
detection, and it matches raw text: `is_dangerous_substring` (`:394`) only
lowercases; `check_dangerous_patterns` (`:411`) searches the unmodified string. A
homoglyph (fullwidth `m`), an ANSI-wrapped command, or an embedded NUL bypasses
every pattern.

`strip_ansi_codes` exists (`utils/command_utils.py:38`) but is applied to command
**output**, never to the command **before** matching. Grep for
`NFKC|unicodedata.normalize` finds nothing on this path.

Reachable via three live paths that carry attacker-influenced text into a loop
with shell tools: the KB web crawler, document ingest, and the browser agent.

Fix: normalize (ANSI strip → C0 strip → NFKC → whitespace collapse) **for matching
only**, never mutating the executed string.

### #14028 — inbound ingest has no bot-self filter, dedup, or recursion guard *(wave 1)*

`services/gateway/` normalizes inbound payloads from 10 platform adapters
(`gateway.py:263` `receive_message`, `adapters/base_adapter.py:23`) and routes them
to agents via `message_router.py`. Grep across the whole package for
`bot_id|is_bot|self_.*message|dedup|seen_.*id|recursion` returns **only rate-limit
hits**.

Rate limiting bounds the *volume* of a feedback loop; it does not prevent one and
does not deduplicate a redelivered message. Open failure modes: self-reply loops
(the platform echoes our own post back as a user turn), duplicate delivery on
webhook retry producing two agent turns and double tool side effects, and
unbounded agent-to-agent recursion. Nothing errors and nothing alerts — the loop
quietly bills tokens.

### #14029 — context windows are a static catalog with a 4096 fallback *(wave 1)*

`context_window_manager.py` resolves from `config/context_windows.yaml` (`:117`)
with hard-coded fallbacks of `4096` (`:169`, `:178`, `:577`, `:584`) and `8192`
(`:519`). No probe, no parser: grep for
`max_model_len|maximum context length|num_ctx|context_length_exceeded` returns
nothing; the only Ollama call is a liveness check (`startup_validator.py:311`).

Both directions fail silently — a 32k model catalogued as 4k is compressed for no
reason (quality loss, never an error), and one catalogued too high returns a 400
every turn until the YAML is hand-edited. This hits every local and self-hosted
model, which is the deployment shape we ship.

The transferable trick: **the serving stack states its own limit in the text it
rejects with**. Parse it once and every later turn is correct. Two details make
the parser correct rather than merely present — anchor each pattern on the *limit
keyword* so `"requested 50000 … maximum … 32768"` yields 32768 and not 50000, and
band the result (~512 … ~10M) so an implausible parse falls through instead of
raising the assumed window into a hard failure.

### #14030 — skill distillation cannot see recurrence *(wave 2, gated)*

`services/skill_management/skill_extractor.py:86` takes a single conversation;
the scheduler feeds them one at a time. Within one window, a habitual request and
a one-off task are indistinguishable, and the reviewer is *right* to decline
writing a skill for a one-off — so "I ask this every week" can never reach it. No
prompt change recovers the signal; it needs a cross-session pass keyed on distinct
conversations **and distinct days**.

The transferable discipline is the second half: **recompute each sweep from
scratch over the lookback window instead of incrementing counters.** Re-runs
become idempotent and an abandoned routine decays out on its own, with no expiry
job.

**Gated, deliberately.** `AUTOBOT_SKILL_DISTILLATION_ENABLED` defaults to `False`
(`skill_distillation_scheduler.py:44`). Building a recurrence miner for a pipeline
nobody has turned on adds maintained-but-dormant surface — the #13685 shape.

### #14031 — pre-action verifier and belief state run nowhere *(child of #13587)*

`grep -rn "from agent_loop.loop import\|AgentLoop("` returns **only test files**.
`AgentLoop` has no production caller; the live path is `chat_workflow/graph.py` +
`chat_workflow/tool_handler.py`. So `PreActionVerifier` (sole caller
`agent_loop/loop.py:191-192,1668`, `pre_action_verifier_enabled` defaulting to
**True**) and `BeliefState` (sole caller `agent_loop/loop.py:28,186,…`,
`belief_state_enabled` defaulting to **False**) execute on no request.

This corrects #13587's own "Already covered" list, which cited
`agent_loop/loop.py` for both the pre-action verifier and durable run
checkpointing. The capabilities are real and well built; they are not *covered*,
because they never run. A guard whose enable flag defaults to `True` inside a dead
module is exactly how this survives an audit.

#13590 (CLOSED) is the template for the fix, and it is worth stating as a rule:
**do not wire the dead entry point in — extract the decision logic into
`autobot_shared/` as a dependency-free pure function, call it from the live seam,
and add a wiring assertion so the next refactor cannot silently un-wire it.**
`repetition_guard` and `fact_forcing` both took that route. #13919 and #13997 are
the same extraction over the rest of the package; one pass beats three.

---

## Design input, not filed as an issue

**Two-tier safety floor** → posted on #13250. A frozen, startup-built pattern floor
returning `PASS` / `FORCE_HUMAN` / `HARD_BLOCK`, evaluated *before* any grant
lookup. Today `is_dangerous_command` computes severity but uses it only to pick
the message wording — there is no tier meaning "no approval path may execute
this". Filed as a comment rather than an issue **on purpose**: as a standalone
addition it becomes a fifth approval mechanism, which is the problem #13250
exists to remove. #14027 is a practical prerequisite — a floor matching
un-normalized input inherits the same bypass.

## Deliberately NOT proposed — do not re-file

- **Progressive tool disclosure** — already evaluated and rejected at our scale.
- **The source's contradiction detector** — string-overlap only, self-labelled
  EXPERIMENTAL and shipped default-off. Our `ContradictionRecord` in
  `agent_loop/belief_state.py` is a better starting point.
- **Its IM-channel set and publishing pipeline** — market-shaped, no fit.
- **Anything requiring its JVM framework stack.**

## Method note

Greps excluded `.worktrees/`, `.claude/`, `venv/`, `node_modules/`. Two items
listed as unverified in the working draft were closed out before filing: the hook
bus was confirmed fully invoked (25 declared, all with live call sites — so no gap
exists there), and the inbound trigger path was confirmed to exist, which is what
turned #14028 from a question into a finding.
