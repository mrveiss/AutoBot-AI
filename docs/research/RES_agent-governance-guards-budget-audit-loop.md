# Agent governance guards: pre-request budget, audit hash chain, loop guard, versioned agent spec

**Date:** 2026-11-15 · **Type:** technical research (anonymized) · **Baseline:** `origin/main` @ c2b5a4fa95

## Source analysis: a self-hosted, open-source company agent platform (the reference work)

### What it is

A self-hosted platform from a vendor where teams build agents in a browser (instructions, model, capabilities), publish versioned agents to chat, messaging channels, an API, a web widget, voice and desktop, and govern them with roles, single sign-on, budgets, approvals, an audit trail and a credential vault. a Python backend on a typed agent framework with PostgreSQL/pgvector and Redis, a React frontend, single-host Docker Compose as the supported deployment. Young (months old) with a very high release cadence.

### Architecture and key patterns

- **Agent is data, not code:** a versioned typed spec is the contract between the builder UI and the runtime. It holds references only (model profile, tool id, collection — never a secret), evolves additively (new fields carry defaults), is validated at publish time and exports to YAML.
- **Capability registry:** each capability is a package; configuration can only compose what code registered.
- **Mandatory, unregistered guards:** budget and approval are attached by the agent factory to every agent and cannot be configured off.
- **Layering:** routes → services → repositories; background jobs enqueued in the request's own transaction.

### Notable implementation details

- **Budget — accounting split from enforcement:** a spend ledger records; a guard refuses *before* each model request (checking after lets a runaway loop overshoot by one call). Prices come from a bundled offline price snapshot that models context-length tiers and cache rates; a hand-kept flat table had under-reported long-context cost by 2×.
- **Approval gate wraps tool execution**, keyed on a tool's stable id; translation from the model-visible (renamable) name lives in one function.
- **Hash-chained audit:** `entry_hash = SHA-256(prev_hash ‖ canonical fields)`, per-chain lock, one hash function shared by writer and verifier, a verify command, and a documented lock order to avoid deadlocks.
- **Loop guard:** detects one call repeated N times *or* a 2–3-call cycle in the current run; the first sighting adds a one-request warning that never enters history; a repeat ends the run with a distinct status naming tools, never arguments.

### Strengths / weaknesses

- Strengths: rationale written beside the code; governance non-optional by construction; clean agent-as-data contract.
- Weaknesses: commits concentrated in one maintainer; very wide feature surface (some demos are illustrative only); multi-tenant shape; framework lock-in.

### Visible vs hidden metrics

- **Visible (self-reported):** model-provider count, MCP listing count, tutorials — none independently benchmarked; MCP listings are unvetted registry metadata.
- **Hidden:** operating a large monolith, upgrade churn, framework lock-in, maintainer concentration.
- **Weighing:** the *patterns* are cheap to borrow; adopting the product would carry the hidden costs.

## AutoBot comparison

### What we can adopt

| # | Pattern | Already-exists audit | Missing delta | Verdict | Effort |
|---|---|---|---|---|---|
| A1 (#21636) | Pre-request enforcement of the Company OS dollar budget | `llc/adapters/autobot_agent_adapter.py` forwards usage to `BudgetService.ingest_cost_event` *after the task completes*; `llm_shared/token_budget.py` (#11541) is pre-request but per-run tokens, fail-open, not tied to the agent's budget row; `BudgetService.check_budget` (`llc/services/budget.py`) has no LLM-path caller | Consult the agent's remaining budget in the existing pre-request gate in `llm_shared/base_provider.py` — one gate, not a second | adopt | moderate |
| A2 (#21637) | Tier-aware pricing (context tiers + cache rates) | `autobot_shared/model_pricing.py` notes its flat schema cannot express the >100K-context tier or cache prices | Pricing schema with tiers and cache rates, read by budget and analytics | adopt (precondition for A1's accuracy) | moderate |
| A3 (#17219) | Tamper-evident audit hash chain | Tracked by #17219: writers claim tamper resistance; `services/audit/store.py` is immutable by convention only | Chain hash + verify on the canonical store; `services/audit/purge.py` / `retention.py` must re-anchor, not break, the chain; fixed lock order | adopt-with-conditions — lands under #17219 | moderate |
| A4 (#21638) | Cycle detection + two-strike loop guard | `agent_loop/loop.py` `_check_tool_call_repetition` counts identical calls (#3255); `chat_workflow/tool_call_loop.py` window of 3 identical iterations | Detect 2–3-call cycles; ephemeral first warning, then a distinct stop status naming tools only | adopt | trivial–moderate |
| A5 (#21639) | Agent as a versioned, publish-validated spec | No per-agent revision model in `llc/models/` (only plan revisions in `company_os_plan.py`, company-level export snapshots); `api/agent_config.py` edits in place | Revisioned agent definition: references never values, additive fields, publish validation, rollback | adopt-with-conditions — after the companies rename; design first | significant |

### What we already do better

- Semantic stagnation detection (#6627) and per-severity retry budgets (#6628, #8649) go beyond syntactic loop detection.
- Single-organisation model: companies are internal entities, avoiding per-tenant isolation cost.
- Human approval queue for data/credential mutation (#17038, `api/approval_gates.py`).
- Outbound HTTP through a guarded fetch under an egress policy.
- Not audited: whether AutoBot's tool gating survives a tool rename (`autobot_shared/tool_catalogue.match_tool_name`) — *did not look*.

### Gaps by impact

1. A1 + A2 — a budget that is both pre-request and correctly priced.
2. A3 — makes an existing security claim true (#17219).
3. A4 — cheap reliability win.
4. A5 — design-level.

## Linked issues

- #21635 Umbrella: Company OS agent-governance guards — pre-request agent budget, tiered pricing, versioned agent definition
- #21636 feat(company-os): check the agent's budget before each LLM call in a run, not after the task
- #21637 feat(pricing): price context-length tiers and cache tokens — the flat schema under-counts long-context runs
- #21638 feat(agent-loop): detect short tool-call cycles (A,B,A,B), warn once, then stop with a distinct status
- #21639 feat(company-os): versioned, publish-validated agent definition with rollback (design first)
- #17219 security(audit): three audit writers document tamper-resistance they do not implement
