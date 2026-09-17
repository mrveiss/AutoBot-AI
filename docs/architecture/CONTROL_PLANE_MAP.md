# AutoBot Control Plane Map

What controls AutoBot, layer by layer: what each layer controls, the doc that defines it, the
`file:symbol` that enforces it in code today, and whether the two agree. Produced for #16835.

## Survey method

Each layer below was checked independently against current code on `main` — never by trusting the
layer's own doc, an issue's claims, or this map's own prior draft. For each layer: read the doc(s)
claimed to cover it, find the actual enforcing code (grep for the mechanism the doc names, or search
independently if the doc is vague or absent), read the real implementation, and compare. A citation
here is either a file:line/symbol a reader can open and check themselves, or an exact search command
and its real output. Re-run either to verify or to catch the next drift — do not extend this map by
editing prose without doing the same check.

Every row below carries one of four verdicts:

- **Enforced** — the doc's claim matches what the code does today. Cited proof included.
- **Drifted** — the doc claims something the code no longer does, cites a path/mechanism that moved
  or never existed, or overclaims coverage. Cited contradiction included; child issue filed.
- **Not a control** — real code exists but doesn't gate/block anything (descriptive documentation,
  or infrastructure sizing/ops guidance rather than an enforced rule).
- **Doc gap** — the control is real and enforced in code, but no doc (or no *correct* doc) describes
  it. Child issue filed to close the gap.

Nothing here is marked "could not determine" — every layer was resolved to one of the above with
cited evidence. Where a layer needed a follow-on fix rather than just a doc correction, that's noted
per-row and the child issue covers both.

## Summary table

| # | Layer | Controls | Doc | Enforcing code | Verdict | Issue |
|---|---|---|---|---|---|---|
| 1 | Data access / tenancy | Which tenant's rows a request may touch under `/api/llc/*` | `docs/llc/tenant-context.md` | `autobot-backend/api/user_management/dependencies.py:188 get_tenant_context`, `llc/deps.py:142 assert_company_access` | Enforced | #16851 (citation staleness only) |
| 2 | Authentication | Verifying caller identity before any protected endpoint runs | `docs/developer/AUTHENTICATION_RBAC.md` | `autobot-backend/auth_middleware.py:864 get_current_user`, `:967 check_admin_permission` | Drifted | #16839 |
| 3 | Escalation | Human approval before an agent executes a risky terminal command | `docs/architecture/TERMINAL_APPROVAL_WORKFLOW.md` | `services/agent_terminal/service.py:662 _check_auto_approval_or_queue` | Drifted | #16840 |
| 4 | System instructions | Which extensions may read/rewrite the system prompt, and how | `docs/developer/PROMPT_MIDDLEWARE_GUIDE.md` | `chat_workflow/llm_handler.py:51,81`, `middleware/manager.py:265 invoke_with_transform` | Enforced | #16851 (citation staleness only) |
| 5 | Tool permissions | What a tool-invoking agent may call, what forces human approval | *(none — doc gap)* | `middleware/builtin/permission_enforcement.py:60 PermissionEnforcementExtension`, `autobot_shared/tool_catalogue.py:64 SENSITIVE_TOOLS` | Doc gap | #16841 |
| 6 | Input provenance / prompt-injection defence | Detecting/neutralizing injection payloads before they reach the model | umbrella #16777 | `autobot-backend/security/content_firewall.py`, `knowledge/ingest_sanitize.py:57 sanitize_fact_content` | Drifted | #16842 (RAG-chat-path gap already tracked as #16771) |
| 7 | Network egress policy | Outbound HTTP must be SSRF-safe | `docs/developer/THREAT_MODEL.md`, `docs/developer/ARCHITECTURE_EXCEPTIONS.md` | `autobot_shared/security/ssrf_guard.py:305 fetch_safe_url`, `research_browser_manager.py:284 _reject_if_dns_rebound` | Enforced | — |
| 8 | Data retention & deletion | Time-boxed deletion of sessions, files, audit logs, KB entries | *(none found)* | `autobot-backend/tasks/{chat,file,audit_log,knowledge}_retention.py` | Drifted | #16846 |
| 9 | Emergency stop / kill switch | Admin-triggered halt of autonomous operations | `docs/features/PHASE_8_ENHANCED_INTERFACE.md` | `autobot-backend/api/advanced_control.py:465 emergency_system_stop` | Drifted | #16843 |
| 10 | Update & deployment control | All updates go through the builtin updater only | `CLAUDE.md`, `docs/architecture/UPDATE_FLOWS.md` | `autobot-slm-backend/api/code_sync.py:3453 self_update`, `:3417 resolve_and_queue_self_update` | Enforced (one doc-scoping gap) | #16844 |
| 11 | Model & provider routing | Which LLM tier/model handles a request, and provider fallback | `docs/developer/TIERED_MODEL_ROUTING.md` | `autobot-backend/llm_shared/tiered_routing/tier_config.py:18-82` | Drifted | #16849 |
| 12 | Secrets management | Encrypted storage and per-owner access authorization of credentials | `docs/features/secrets_management_system.md` | `autobot-backend/services/secrets_service.py`, `knowledge/connectors/credential_store.py:603 _require_owner` | Drifted | #16579 / #16804 (already tracked, in flight) |
| 13 | Backup / restore | Backup creation, integrity verification, retention, restore | `docs/operations/lifecycle-matrix.md` (accurate); `docs/operations/disaster-recovery.md` (stale) | `autobot-slm-backend/services/backup.py`, `api/stateful.py:49,108,141,164` | Drifted | #16847 |
| 14 | Governance | EU AI Act / NIS2 / ISO 42001-style compliance mechanisms | `docs/architecture/EU_AI_GOVERNANCE.md` | `autobot_shared/plugin_sdk/capabilities.py:163 CapabilityChecker.check()` (real); `security/enterprise/compliance_manager.py` (dead) | Drifted | #16848 |
| 15 | Scaling | VM sizing, manual scale triggers, K8s roadmap | `docs/operations/scaling-strategy.md` | *(none — no autoscaling code exists)* | Not a control | — (classification note only) |
| 16 | Logging | Which logging call pattern is used; blocking raw print/console | `docs/developer/LOGGING_STANDARDS.md` | `.pre-commit-config.yaml:863 no-print-console` hook | Drifted | #16850 |
| 17 | Rate limiting / cost control | Per-user/tenant request-rate and spend limiting | *(none found)* | `autobot_shared/rate_limiter.py::RateLimiter` (partial); `llc/scheduler/budget_watchdog.py` (LLC-scoped, real) | Drifted | #16845 |

**Resolving the umbrella's two open questions:**
- **Tool permissions** (row 5): no comprehensive doc exists — the one cross-reference that names a
  destination (`AGENT_MATURITY_LEVELS.md` → `AUTHENTICATION_RBAC.md`) points at a doc that doesn't
  cover it. The enforcement itself is real, live, and heavily exercised (fail-closed, `#14523`).
- **Rate limiting / cost control** (row 17): not absent. Both request-rate and spend-limit
  infrastructure exist, but the general-purpose paths are disconnected at the call site — the main
  chat path's cost tracker calls a method that doesn't exist on its own tracker class (silently
  swallowed for ~5 months), and two of three general rate limiters are defined but never invoked.
  A narrower, genuinely-enforced spend limiter exists for the LLC ("AI-run companies") feature only.

## Per-layer detail

### 1. Data access / tenancy — Enforced

`get_tenant_context` (`api/user_management/dependencies.py:188`) resolves `org_id` by header → path
→ query → JWT precedence; non-platform-admin callers get a DB membership check
(`_check_org_membership`) and a `403` if not a member. `llc/deps.py:142 assert_company_access`,
`:157 load_authorized`, `:127 load_owned_project` all return `404` (not `403`) on mismatch, matching
the "can't distinguish not-yours from doesn't-exist" design. `llc/middleware/agent_auth.py:29
LLCAgentAuthMiddleware` validates bearer agent-API-keys the same way. #12215's IDOR-closure claim
verified live in `llc/api/activity.py` and `routines.py`. Only drift: stale line-number citations in
the doc (#16851).

### 2. Authentication — Drifted

Core mechanism (`auth_middleware.py:864 get_current_user`, `:967 check_admin_permission`, 3-attempt
lockout at `:51-52`) matches the doc exactly, as does RBAC (`auth_rbac.py:149,244,287`) and
self-registration (`api/auth.py:476`). But `AUTHENTICATION_RBAC.md`'s "Single-User Mode" section
documents an `AUTOBOT_SINGLE_USER_MODE` auth-bypass env var that doesn't exist anywhere in code
(zero grep hits) — `security_layer.py:151-153` states explicitly there is no such bypass (#10636,
#10713). Also: `docs/developer/ROLES.md`, listed in the umbrella's survey as an Authentication doc,
actually documents SLM infrastructure deployment roles, not RBAC — a survey mis-pointing, not a code
issue. See #16839.

### 3. Escalation — Drifted

`TERMINAL_APPROVAL_WORKFLOW.md` claims SAFE-risk commands execute immediately, only MODERATE+
requires approval. In code, `_check_auto_approval_or_queue` (`agent_terminal/service.py:662`) checks
only previously-learned per-user rules and, on no match, unconditionally queues **every** command for
manual approval — the risk-based `CommandApprovalManager.needs_approval` (`command_approval_manager.py
:247`) exists but is never called from the execution path. The codebase's own test
(`post_execution_failure_15073_test.py:96-99`) has to stub around this to exercise "auto-approved."
Role-based gating (`_check_agent_permission`) and the `/approve`/`/interrupt` endpoints do match the
doc. See #16840.

### 4. System instructions — Enforced

`_emit_system_prompt_ready`/`_emit_full_prompt_ready` (`llm_handler.py:51,81`) call
`invoke_with_transform` (`middleware/manager.py:265`) exactly as documented; `_init_builtin_extensions`
(`initialization/lifespan.py:486`) registers the real extensions onto the live singleton, not a
throwaway instance (confirming the #14280 fix). Only drift: the hook-count table is stale by one row
(#16851).

### 5. Tool permissions — Doc gap (resolves the umbrella's open question)

No doc comprehensively covers this. `AGENT_MATURITY_LEVELS.md` cross-references
`AUTHENTICATION_RBAC.md` for "tool seam" enforcement; that doc has zero coverage of the mechanism
(verified by full read + targeted grep). The real enforcement is live and fail-closed:
`PermissionEnforcementExtension` (`middleware/builtin/permission_enforcement.py:60,94`) raises on an
undeclared tool or an unauthorized role and this correctly propagates as a hook veto
(`middleware/base.py:212`); `autobot_shared/tool_catalogue.py:64 SENSITIVE_TOOLS` is the
approval-required catalogue; `agent_loop/loop.py:1495,1636,1645,1759` is the agent-loop approval gate.
See #16841.

### 6. Input provenance / prompt-injection defence — Drifted

KB-write sanitization is closed and live (#16770): `ingest_sanitize.py:57 sanitize_fact_content`
called from `knowledge/facts.py:777 store_fact()`. The chat-facing gap is already tracked (#16771,
PR #16791 open): `content_firewall.py`'s `inspect(source=RAG)` is wired only into
`advanced_rag_optimizer.py:1049`, not into the live chat retrieval path
(`chat_workflow/llm_handler.py:_retrieve_knowledge_context` → `services/knowledge/service.py`), which
has zero firewall references — RAG text reaching the live chat prompt today bypasses the firewall
entirely. New finding not covered by #16777's children: `content_firewall.py`'s docstring claims
file-read coverage (`ContentSource.FILE`) with zero production call sites. See #16842.

### 7. Network egress policy — Enforced

`fetch_safe_url`/`pinned_request_with_redirects` (`autobot_shared/security/ssrf_guard.py:305,230`)
resolve-then-pin to defeat DNS-rebind TOCTOU, exactly as `THREAT_MODEL.md:131-134` cites.
`research_browser_manager.py:284 _reject_if_dns_rebound` covers the Playwright path (which can't use
the pinned-connector trick) via `is_public_url_async`, and honestly documents its own residual
DNS-rebind race rather than hiding it. `ARCHITECTURE_EXCEPTIONS.md:232-265`'s SLM→node-proxy bypass is
correctly scoped and grep-checked. No drift found anywhere in this layer.

### 8. Data retention & deletion — Drifted

No dedicated doc exists. `admin_retention_policies.py` CRUDs a `retention_policies` DB table that is
**never consumed** by the four actual purge tasks
(`tasks/{chat,file,audit_log,knowledge}_retention.py`), which instead read flat env-var config
(`ssot_config.*_retention_days`) — confirmed via `grep -rl "RetentionPolicy"`, zero non-API callers.
`anonymize_instead_of_delete` is stored and round-tripped by the API but never read by any deletion
path — always hard-delete regardless of the flag. See #16846.

### 9. Emergency stop / kill switch — Drifted

`emergency_system_stop` (`advanced_control.py:465`) is documented as an immediate system-wide halt.
It calls `request_takeover(...)` without ever passing `affected_tasks`, which defaults to `[]`
(`takeover_manager.py:646-677`) — so `_pause_affected_tasks` loops zero times on both the
critical-trigger path and the auto-approve path. Nothing in the codebase reads the resulting
`paused_tasks` Redis set to gate execution; it's exposed read-only for a health-check count. The
frontend's own code comment already describes the real behavior accurately ("auto-approved takeover
request," not a kill switch). See #16843.

### 10. Update & deployment control — Enforced (one scoping gap)

`self_update` (`code_sync.py:3453`) delegates to `resolve_and_queue_self_update` (`:3417`), whose own
docstring confirms it's the single shared function behind both the maintenance-UI route and the
credential-free local admin socket (#15728) — "one code path with two doors, not a second updater to
keep in sync." Matches `UPDATE_FLOWS.md` and the CLAUDE.md rule. Gap: `docs/deployment/hyper-v-
internal-network.md:113` still documents an ad-hoc `deploy.sh` script for first-time bootstrap without
scoping it as bootstrap-only, reading as an ongoing deployment method. See #16844.

### 11. Model & provider routing — Drifted

`TIERED_MODEL_ROUTING.md` (self-labeled "v2.1.0 Fully Implemented") is extensively stale against
`llm_shared/tiered_routing/`: wrong file paths (cites a directory that no longer exists), a diagram
routing through a class whose own docstring says "Deprecated," a claimed 7-tier system vs. the actual
5-tier `TierConfig` (`tier_config.py:18-82`), different scoring weights (`complexity_scorer.py:40-45`),
a claimed-default-on env var that doesn't exist vs. the real gate `config.chat_tiered_routing`
(default **off**, `ssot_config.py:281`), and a stale example API response. See #16849.

### 12. Secrets management — Drifted (already in flight)

Encryption claims are accurate (Fernet, `secrets_service.py:96-121`) and the doc already
self-corrected an earlier AES-256-GCM overclaim. But the doc's "✅ Proper access control enforcement"
is currently false: `_build_get_secret_query`/`_row_to_secret_dict` (`secrets_service.py:313-339,172-
189`) never select or map `created_by`, so `credential_store.py:603 _require_owner` fails closed for
every connector-credential owner on the default path. Already tracked and fix-in-flight: issue #16579,
PR #16804 (not yet merged as of this survey).

### 13. Backup / restore — Drifted

`disaster-recovery.md` describes a manual `backup_autobot.sh` cron script that doesn't exist anywhere
in the repo, and never mentions the real subsystem: `stateful.py:49,108,141,164` (backup CRUD +
restore API) and `services/backup.py` (checksum-verified backup, retention pruning). The more accurate
`lifecycle-matrix.md` has one stale Known Gap: it claims no PostgreSQL backup timer exists, but a
scheduled `systemd` timer with its own retention has shipped since PR #11383/#11384 (2026-07-09),
before the doc's last edit (2026-09-03). See #16847.

### 14. Governance — Drifted

`EU_AI_GOVERNANCE.md` is unusually self-aware (correctly labels several gaps as "not enforced"), but
its evidence table cites `ComplianceManager` (`security/enterprise/compliance_manager.py`, 910 lines)
as active audit-logging infrastructure. Zero instantiations exist anywhere in the codebase outside its
own package export; the repo's own test for this area explicitly states it "deliberately does not
instantiate the manager." By contrast, the plugin capability system
(`autobot_shared/plugin_sdk/capabilities.py:163 CapabilityChecker.check()`) genuinely raises and is
called live from `plugin_manager.py:560,599,618` — real governance, correctly documented. See #16848.

### 15. Scaling — Not a control

`scaling-strategy.md` is a manual ops runbook (PowerShell VM commands, a script you'd run by hand);
`Scaling_Roadmap_and_Architecture_Evolution.md` explicitly self-labels its own content as
"aspirational, not current state." No autoscaling code exists anywhere in the repo (zero
`autoscal`/Kubernetes-manifest hits). This layer should be classified in any future revision of this
map as descriptive/operational documentation, not an enforced control — no child issue filed, since
there's no contradiction, just a category mismatch with the other 16 rows.

### 16. Logging — Drifted

The real enforcement is genuine and blocking: hook id `no-print-console`
(`.pre-commit-config.yaml:863-869`, backed by `pre-commit-no-print-console`), live in both the local
git hook and pre-commit.ci. But `LOGGING_STANDARDS.md` cites a different, unwired, orphaned script
(`scripts/detect-logging-violations.sh`) as the enforcement mechanism. Separately, the doc's documented
Python pattern (stdlib `logging.getLogger`) contradicts CLAUDE.md's canonical
`autobot_shared.logging_manager.get_logger` pattern — and neither is actually hook-enforced (only the
raw print/console ban is). See #16850.

### 17. Rate limiting / cost control — Drifted (resolves the umbrella's open question)

Not absent, but broken where it matters most. General request-rate infrastructure
(`autobot_shared/rate_limiter.py::RateLimiter`) is real and wired to several narrow surfaces (secrets
endpoint, public embed widget, shared links, and multiple *outbound*-pacing use cases) — but the two
instances scoped to general per-user/per-conversation limiting are defined and never called
(`user_management/middleware/rate_limit.py:28`, `utils/conversation_rate_limiter.py:360`). Spend
limiting: the general-purpose Budget Policy system (#6470, `budget_policy.py`) is fully implemented
but unreachable — `llm_service.py:1181` calls `LLMCostTracker.record()`, a method that doesn't exist
on that class, silently swallowed since commit `eda3f4529e` (2026-04-01, ~5 months). The
OpenAI/Anthropic-compatible gateways never call cost tracking at all. A separate, genuinely-enforced
spend limiter exists (`llc/scheduler/budget_watchdog.py`, hard-stops agents/companies at ≥100% of
budget) but is scoped to the LLC "AI-run companies" feature only, not general chat/API traffic. See
#16845.

## Child issues filed from this survey

| Issue | Layer | Severity |
|---|---|---|
| #16839 | Authentication | Doc drift |
| #16840 | Escalation | Behavioral drift — approval policy far stricter than documented |
| #16841 | Tool permissions | Doc gap |
| #16842 | Input provenance | Doc overclaim (new, not covered by #16777's children) |
| #16843 | Emergency stop | **Broken safety control** — does not stop anything |
| #16844 | Update & deployment | Doc scoping gap |
| #16845 | Rate limiting / cost control | **Broken control** — budget enforcement silently dead ~5 months |
| #16846 | Data retention & deletion | Broken control — policy API disconnected from enforcement |
| #16847 | Backup / restore | Doc drift (two docs) |
| #16848 | Governance | Dead code cited as active infrastructure |
| #16849 | Model & provider routing | Extensive doc drift |
| #16850 | Logging | Doc drift (wrong script + pattern conflict) |
| #16851 | Doc hygiene | Citation staleness (2 docs, no behavioral impact) |

Pre-existing, already tracked (not re-filed): #16579/#16804 (secrets `created_by`), #16771/#16791 (RAG
chat-path firewall gap, child of #16777).
