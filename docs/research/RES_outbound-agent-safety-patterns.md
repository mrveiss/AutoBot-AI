# Outbound agent safety patterns: egress governor, pause, AI lines, outgoing-content check

**Date:** 2026-11-19 · **Type:** technical research (anonymized) · **Baseline:** `origin/main` @ f98f24e811 · **Umbrella:** #21866

## Source analysis (anonymized)

The reference work is a self-hosted, open-source autonomous outbound-sales agent: it discovers businesses, profiles their websites for buying signals, finds a decision maker, verifies an address, drafts personalised email, sends it and triages replies. Single process, SQLite store, FastAPI dashboard, an MCP server for coding agents, an entry-point extension API. Copyleft licence.

Patterns of note:
- **Deterministic scheduler decision.** A fixed priority (replies > send > write > prospect > analyse) decided from counts, never a model call.
- **Observation rows.** Every signal is a row with value, confidence and provenance, so a new signal needs no migration and history comes free; a person confirms which signals are collected.
- **Deterministic pre-send gate.** Plain-code checks before any send: banned phrases, unrendered placeholders, length and link caps, recipient/record mismatch. Unattended sends with foreign-domain links or quoted instructions are held.
- **Approval by default.** Every message waits for a person; switching autopilot off recalls auto-approved, unsent messages.
- **Agent route allowlist.** The coding-agent token reaches only listed read/estimate/pause routes; a new route is human-only by default.
- **Restrict-only extension rules.** An extension may hold or cancel a send, never force one.

Hidden costs: copyleft licence on any in-process use, a full parallel stack (store, dashboard, auth, secrets, scheduler), a model path through a personal chat-subscription CLI, and the legal and deliverability load of cold email.

## AutoBot comparison

Rule applied: anything adopted is rebuilt on AutoBot's own stack; the reference work is never installed, vendored or run.

### Already stronger in AutoBot
- Unified Approvals (`models/approval.py`, `services/approval_execution.py`) and three AI lines per tool action (`services/ai_line_enforcement.py`, #18430).
- Untrusted-content framing and inspection (`autobot_shared/prompt_rules.py:frame_untrusted_block`, `security/content_firewall.py`).
- Heartbeat with pause and budget gate before every run (`llc/scheduler/heartbeat_scheduler.py`, `llc/scheduler/dispatch_gate.py`), per-agent budgets (`llc/scheduler/budget_watchdog.py`).
- Default-deny tool permissions (`services/mcp_dispatch.py`) and confined CLI-agent API (`llc/agent_api_call.py`).

### Gaps filed
| Gap | Evidence | Issue |
|---|---|---|
| Email sends bypass the egress governor | `integrations/microsoft365_integration.py:424`, `operator_dashboard/gmail_service.py:106,166` | #21867 |
| Pause does not stop sends from in-flight runs | `services/gateway/egress_governor.py` reads no pause flag | #21868 |
| CLI-adapter agents ignore AI lines | `llc/adapters/claude_code_adapter.py:162-176`; no `ai_line` in `llc/adapters` | #21869 |
| No deterministic outgoing-content check | no banned-phrase / link-allowlist code; `pre_action_verifier_guard` is model-based | #21870 |
| AI-line downgrade recall unverified | — | #21871 |
| Sales / outreach department | `llc/built_in_templates/` has none | #21872 (needs-decision) |

### Deliberately not adopted
- The reference work as plugin, sidecar or vendored code.
- Personal chat-subscription CLI as the model path for unattended work.
- A second store, dashboard, token auth, secret store or scheduler.
- Scrape-and-guess contact discovery and autonomous cold email as a default.

## Linked issues
- #21866 Umbrella: govern Company OS agents' outbound actions end to end
- #21867 Email sends bypass the egress governor
- #21868 Pause stops new runs only
- #21869 CLI-adapter agents' tool permissions ignore the AI lines
- #21870 Deterministic check on outgoing message content
- #21871 Does lowering an AI line recall auto-approved items
- #21872 Sales / outreach department template decision
