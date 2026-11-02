# Managed integration platforms and agent tools

## Linked issues

- #20708 security(slm): the node agent turns off TLS verification on its calls to the SLM, citing closed #725
- #20709 bug(mcp): external MCP calls reach the audit log with no user, because dispatch passes only the role
- #20710 bug(workflow): workflow runs and their history live only in memory and are lost on restart
- #20711 bug(workflow): workflow versions are saved but cannot be listed, compared or restored

## Source Analysis: a commercial hosted integration and automation platform

Read on 2026-11-02 from vendor documentation only. No source code is public, and nothing here has been independently tested.

### What It Is
A mature commercial cloud integration and automation platform from a vendor. Workflows connect business applications, and a newer agent layer reuses those integrations as tools for AI agents.

### Architecture & Key Patterns
- **Hosted control and execution plane**, with regional data centers.
- **Workflows:** a trigger followed by actions. Variants cover plain workflows, APIs, data pipelines, application events and knowledge bases.
- **Data mapping:** each action's output is a data tree, and its fields are mapped into later steps.
- **Control flow:** conditionals, repeat-while, repeat-for-each, batched repeat, callable sub-workflows, and an explicit stop marked failed or successful.
- **Errors:** a try/catch-style block; retries set by attempt count and interval, optionally conditional.
- **Jobs:** each tool invocation runs as a job, visible in a central operations view.
- **Connectors:** a large catalog plus an SDK for custom connectors, private by default, shareable with update notifications.
- **On-prem agent:** an outbound TLS WebSocket tunnel on TCP 443 with mutual TLS against a vendor private CA, and no inbound ports. Agents can be grouped for high availability and load balancing.
- **Agents:** a registry of agent cards listing model, chat interface, job description, tools, application events and KPIs. Tools call applications, custom APIs, data tables or external MCP servers.
- **Delegation:** agents assign tasks to each other and can call A2A-compliant agents.
- **MCP servers:** expose tools with input and output schemas and dynamic tool discovery.

### Notable Implementation Details
- **Tools reuse automation:** the same integration and job machinery serves deterministic workflows and agent tools.
- **Tool versioning:** version history with compare, rollback and test cases; agent versions deploy across dev, test and prod.
- **End-user identity on MCP:** a server can act with the end user's credentials instead of a shared service identity. Every action is logged with identity, and rate limits are set per server and shared across its tools.
- **Guardrails (labelled beta):** prompt attack and harmful content checks are always on. PII modes are block, redact, tokenize and log only, with capped lists of custom patterns, filtered words and denied topics.
- **Tenant encryption:** job history is encrypted twice, with a cloud-provider key plus a tenant key.
- **Audit:** the activity log streams to external log destinations.

### Strengths
- One execution and audit model across workflows, APIs and agent tools.
- Agent governance is treated as a product surface: registry, versions, environments, per-user identity.
- Hybrid connectivity needs no inbound firewall changes.
- Connector breadth, which is the hardest part to copy.

### Weaknesses / Limitations
- Closed, hosted control plane. The docs read do not describe a fully self-hosted deployment.
- TLS inspection breaks the on-prem tunnel unless gateway hosts are excluded.
- Guardrails are still in beta and rely on fixed caps and filters.
- Key features depend on the plan.

### Visible vs Hidden Metrics
- **Visible (all self-reported):** connector count, monthly task volume, customer quotes and analyst placement. The vendor's own connector counts disagree.
- **Hidden:**
  - Workflows and connectors are proprietary, so leaving means rebuilding them.
  - Job data passes through the vendor's plane.
  - Usage-based costs grow with volume.
  - Connector breadth is a permanent maintenance burden for whoever owns it.
  - Agent tools inherit every connector's failure modes.
  - The on-prem tunnel adds a CA exclusion and agent fleet to operate.
- **Weighing:** the model suits enterprises that want a managed integration estate and accept the dependency. It suits self-hosted, privacy-first deployments poorly. For AutoBot the patterns are worth more than the scale figures: identity-bound tools, versioned tools, one job model. A connector catalog on this scale is not a sensible target.

### Not Established
- Concurrency limits, default retry policy, job limits, trigger internals.
- SDK structure and methods.
- Encryption key management, RBAC and deployment detail, billing units, and how human-in-the-loop approval works.

## AutoBot Comparison: the reference work → AutoBot

Audited against `main` at `58cbf98c43`. The MCP, versioning, live-executor, agent TLS, PII and tenant-key findings were re-read directly; the rest come from one audit pass over the code. "Not found" means the named greps returned nothing, and the frontends and worker nodes were only partly searched. Counts are grep-based.

### What We Can Adopt

| # | Candidate | Already exists? (checked) | Visible benefit | Hidden cost | Verdict | Effort |
|---|---|---|---|---|---|---|
| 1 | Record the real caller on external MCP tool calls | Partly. `MCPExternalBridge.call_tool` audits `user_id`, but `_call_external_bridge` passes only `role` (`autobot-backend/services/mcp_dispatch.py:379`), so it is `None` on that path | Every external action is attributable | Caller identity must be threaded through the dispatch path | Adopt | Moderate |
| 2 | Per-user credentials for external MCP servers | No. Credentials load with `cfg.owner_id`, one per server (`services/mcp_server_credentials.py:62-87`); built-in bridges use a service identity (`mcp_dispatch.py:349-367`) | Agents act with the user's own rights | Per-user consent, token refresh and revocation; a shared-credential mode must remain | Adopt with conditions: extend #13629's account identity work, opt-in per server | Significant |
| 3 | Per-server limits on external MCP calls | Not found in `call_tool`; limits exist per token and per module (`mcp_server/autobot_server.py:71-72`) | A noisy tool cannot exhaust a server's quota | Another limit to configure and explain | Adopt | Trivial |
| 4 | Finish workflow version history | Partly. `WorkflowVersionStore` has save, list, restore and diff (`services/workflow_versioning.py:103-289`), but the only caller is the save at create (`workflow_automation/manager.py:225`), with no routes found | Compare and roll back workflows | Restore must handle runs in progress | Adopt: wire in what exists | Moderate |
| 5 | Version history for skills | No. One `version` string on a unique-name row (`skills/models.py:53-70`); promotion is draft to builtin (`skills/promoter.py:32-55`) | Rollback when a skill update misbehaves | Schema and UI work; a dev/test/prod ladder is too heavy for a single self-hosted install | Adopt with conditions: history, compare and rollback only | Moderate |
| 6 | Durable, unified run record | No. Run state is in memory until restart (`manager.py:63-65`); `heartbeat_runs`, `process_runs` and LLC run tables are separate; no tool-call table found | One place to see and debug all work, surviving restarts | High write volume, migration, and overlap with the engine consolidation | Adopt with conditions: design inside #12577, using `store_authority`, not a parallel store | Significant |
| 7 | Workflow retries, branches and loops | Partly. Branches, retries and sub-workflows sit in `orchestration/workflow_executor.py`, unwired by its own docstring; the live executor has no retry code (0 files match in `services/workflow_automation/`). Loops and conditional retries were not found anywhere | Unattended workflows survive transient failures | Loops need iteration caps and loop-safe budgets | Adopt: carry over under #12577; only loops and conditional retries are new | Moderate to significant |
| 8 | Outbound-only agent connection | No. Agents send outbound HTTP heartbeats, but enrollment is inbound SSH/Ansible (`autobot-slm-backend/services/deployment.py`); no tunnel found | Nodes behind NAT join with no inbound ports | A permanent connection service, reconnection and certificate rotation; scope limited to AutoBot's own nodes | Adopt with conditions: only after agent TLS is fixed, and only if such deployments are a real need | Significant |
| 9 | Audit log export to external destinations | No sink found in `services/audit/`; Promtail ships general logs to internal Loki | Fits existing security tooling | Every sink needs the guarded fetch and a redaction review; audit data leaving the host | Adopt with conditions: off by default, one generic sink first | Moderate |
| 10 | Per-agent guardrail settings | No. PII policy is global, per type (`a2a/pii_pipeline.py:299-315`); `agent_id` does not appear in the three guardrail files read | Stricter rules for riskier agents | More configuration to reason about | Adopt with conditions: only once a second policy is actually needed | Moderate |
| 11 | Log-only PII mode | Partly. `PASS` plus audit approximates it (`a2a/pii_pipeline.py:52-58`, `:408`), not verified as a mode | Measure a policy before enforcing it | Small | Adopt: name the behaviour once confirmed | Trivial |

**Rejected by hidden metrics**

| Candidate | Why not |
|---|---|
| Connector catalog on the reference work's scale | Permanent upkeep for thousands of third-party APIs. Connector models are the higher priority (see Gaps) |
| Reversible PII tokenization | Adds a mapping store holding the very data it protects, and `REDACT` and `HASH` already cover outbound sends |
| Denied topics, word filters and capped lists | Fixed lists are brittle, and false positives are costly in a general agent. The source's own version is beta |
| Double-encrypted tenant run history | Adds key management before run history is even durable. Revisit after #6; LLC secrets already derive per-company keys (`llc/services/secret.py:76-77`) |
| KPIs on agent cards | No current use; `kpi` has no hits in the code, and nothing would feed them |

### What We Already Do Better

Based on what the source's docs show; the source's approval flow was not established.

- **Self-hosted by design:** job data stays on the owner's infrastructure.
- **Human approval:** `ApprovalGateService`, four-eyes rules (`autobot_shared/approval_four_eyes.py`) and remote routing are in the code.
- **A2A:** signed agent cards, trust scores and peer identity (`a2a/`, `api/a2a.py`).
- **Untrusted content:** `content_firewall.py` screens tool, web, RAG and MCP output, beyond prompt checks.
- **Third-party connector isolation:** external adapters run as subprocesses over NDJSON (`knowledge/connectors/external_adapter.py`).
- **Connector credentials:** encrypted through `SecretsService`, with an owner check on load (`knowledge/connectors/credential_store.py:226-283`).

### Gaps & Opportunities

In priority order, defects first:

1. **Agent traffic has TLS verification off.** `ssl=False` appears 4 times in `autobot-slm-backend/slm/agent/agent.py` (`:190`, `:223`, `:323`, `:479`). The comment at `:223` says "mTLS pending PKI setup (Issue #725)", but #725 is closed. The agent also authenticates with a shared internal key (`:131`).
2. **External MCP audit records have no caller** (candidate 1).
3. **Workflow runs vanish on restart, and the live engine has no retries** (candidates 6 and 7).
4. **Built, not wired:** `WorkflowVersionStore` restore and diff, and the orchestration engine's capabilities.
5. **Three connector models:** KB connectors (17 registered types), `BaseIntegration` (23 subclasses) and the plugin SDK and MCP servers. Worth consolidating; integration APIs such as GitHub take the token per request, and stored persistence was not found in the one read.
6. **Harmful-content checks:** no such feature was found, and injection hard-blocking is off by default (`security/chat_message_safety.py`). Whether that default is right is a product decision.

### Specific Code/Files Affected

| File | Change |
|---|---|
| `autobot-backend/services/mcp_dispatch.py`, `chat_workflow/tool_handler.py` | Pass the caller's identity to the bridges and audit |
| `autobot-backend/services/mcp_external_servers.py`, `mcp_server_credentials.py`, `mcp_external_bridge.py` | Optional per-user credentials; per-server limit |
| `autobot-backend/services/workflow_versioning.py`, `autobot-backend/api/` | Routes for list, diff and restore |
| `autobot-backend/skills/models.py`, `skills/promoter.py` | Skill version history and rollback |
| `autobot-backend/services/workflow_automation/executor.py`, `manager.py`, `orchestration/` | Durable runs; carry over retries and branching under #12577 |
| `autobot-slm-backend/slm/agent/agent.py` | Turn on TLS verification; client certificates |
| `autobot-backend/services/audit/` | Optional external sink |
| `autobot-backend/a2a/pii_pipeline.py` | Log-only mode; later per-agent policy |
