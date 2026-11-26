# Personal-agent action authorization and provenance

**Date:** 2026-11-26 · **Type:** technical research (anonymized) · **Baseline:** `origin/main` @ 9c4fa9120c · **Umbrella:** #22282

## Source analysis (anonymized)

The reference work is an open-source, single-owner personal agent in research preview. It runs on the owner's machine or a one-person server, as one application process plus a database, a sandboxed Linux workspace container and a separate browser container. It does errands in mail, calendar, chat apps and real websites, and asks before any action the owner's words do not cover.

Patterns of note:
- **Judgment versus authority.** The model plans. Server code decides what runs: app actions, side-effecting browser steps and every shell command pass one checker.
- **A checker fed only owner evidence.** Its input is the owner's own messages, saved schedule inputs, standing instructions and rules, plus the exact action (for a browser step: site, control, typed values). It never receives page, email or tool-result text. It names the owner message that allows an action. Reads and drafts run directly.
- **Standing rules and instructions** written by the owner in plain language are held by the checker across chat, scheduled and background runs. Content the agent reads cannot change them.
- **One untrusted-data frame** for app, browser, web and sandboxed-code results, with close tags neutralized. It deliberately does not pattern-scan for injection phrases and relies on server limits instead.
- **Quote-backed memory.** Automatic learning reads only the owner's messages, and a note is kept only with a verbatim supporting quote from one of them, so injected content cannot write a memory. Each note has an origin, status and source, and the owner can see, edit and forget it.
- **Trusted versus learned skills.** Shipped task guides are trusted guidance loaded on demand. Procedures the agent writes for itself are delivered as untrusted data.
- **Secrets outside the model.** The server types origin-bound saved credentials, authenticator codes and card details into the site, and the model sees only account names and status.
- **One use, one result.** A claim row is written before each private step or confirmed action, so each runs at most once. An uncertain outcome is reported, never retried.
- **Restricted proactive worker.** Event-triggered preparation runs with no writes, browser steps or commands, and matters are deduplicated by a stable key.
- **Enforced layering.** A CI script fails cross-layer imports, and only the composition root may read the environment.

Visible metrics (self-reported, simulated apps and sites, not independently verified): high errand completion, zero unsafe actions in several hundred runs, high long-memory recall, and zero planted false memories. Hidden costs: one LLM call per side-effecting step; checker quality tied to model tier (its own small-model checker passed 8 of 240 unsafe actions); a hosted connection service and telemetry on by default; dependence on a third-party agent runtime; preview-stage churn. Verdict: adopt the patterns, not the code.

## AutoBot comparison

Rule applied: anything adopted is rebuilt on AutoBot's own stack; the reference work is never installed, vendored or run.

### Already stronger in AutoBot
- One enforcement seam: `services/ai_line_enforcement.py:339` `enforce_line()` on chat (`chat_workflow/tool_handler.py:3160-3166`), MCP and integrations (`tool_handler.py:1006`), the agent terminal (`services/agent_terminal/ai_line_gate.py:67`) and realtime voice (`services/realtime_mcp_bridge.py:326`). It is deterministic, with no LLM call per step.
- A claim-once approval decision (`services/approval_gate_service.py:452` `_claim`, conditional UPDATE … RETURNING) and fingerprint-deduplicated holds (`ai_line_enforcement.py:259`).
- Multi-company RBAC, four-eyes approvals, and per-agent and per-company hard budgets before dispatch (`llc/scheduler/budget_watchdog.py:103`, `llc/scheduler/dispatch_gate.py:177`).
- Every chat tool output, errors included, is framed and neutralized (`chat_workflow/tool_call_loop.py:45`).

### Defects found in current code
- One approval allows repeat runs of a non-command chat tool. The fingerprint is consumed only for `execute_command` (`chat_workflow/tool_dispatch_guards.py:371-373`) → #22283.
- Realtime voice MCP results reach the model unframed (`services/realtime_mcp_bridge.py:340,488`) → #22284.
- Untrusted framing is defined three times, and two schemes do not neutralize a forged close marker on their own (`autobot_shared/prompt_rules.py:85`, `knowledge/query_sanitizer.py:404`, `security/content_firewall.py:298`) → #22285.
- Per-turn fact extraction calls a method no class defines; re-found here and already tracked as #18075.

### Gaps filed
| Pattern | AutoBot today | Issue |
|---|---|---|
| Authorization judge fed only the person's words plus the action, failing closed | The verifier sees model-written args and reason and fails open; no check against what the person asked | #22286 |
| Owner-authored standing rules | Action-key lines only (`llc/models/ai_line.py`); plain-language rules are prompt text | #22287 |
| Verbatim-quote memory provenance | Learning input mixes user and assistant text (`chat_workflow/stop_hook.py:73`); facts keep no source message | #22288 |
| Browser sign-in by secret handle | No credential or TOTP handling in the browser tool | #22289 |
| Layer-import matrix and env-read confinement | Only extensions-versus-core and infra guards | #22290 |
| Learned skills delivered as untrusted data | Skills enter the system prompt as trusted text (`prompt_manager.py:337`) | delta on #18367 |

### Deferred
- A restricted tool profile and matter-key dedup for event-triggered runs. Today's wake sources are internal only (`llc/models/enums.py:194-208`), so this waits for an external event source.
- Capability evals against fake apps and lookalike sites, gated in CI. This is behind #16157 and CI capacity.

### Deliberately not adopted
- An LLM check on every step including reads; a hosted connection service; the reference work's agent runtime and desktop shell.

## Linked issues
- #22282 Research: personal-agent action authorization and provenance — adoption tree
- #22283 One yes allows repeat runs of a non-command chat tool
- #22284 Realtime MCP tool results reach the voice model unframed
- #22285 Untrusted framing defined three times
- #22286 Authorization judge fed only the person's words plus the action
- #22287 Owner-authored standing rules enforced by the judge
- #22288 Keep a learned note only with a verbatim quote
- #22289 Sign in by secret handle
- #22290 Backend layer-import matrix and env-read confinement ratchet
- #18367 Skill-proposal receiver (delta: learned skills as untrusted data)
- #18075 Per-turn fact extraction calls a method no class defines (re-found)
