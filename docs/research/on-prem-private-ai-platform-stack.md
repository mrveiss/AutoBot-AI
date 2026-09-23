# Source Analysis: A Commercial On-Premise Private-AI Platform for Regulated Industries

**Source class:** vendor marketing site for a commercial platform built on top of a widely-starred
open-source private-RAG project. Referred to below as **the reference work**.
**Date analysed:** 2026-09-21
**Evidence basis:** 10 public marketing/blog pages (home, three platform-layer pages, deployment
options, sizing tool, open-source-foundation page, stack-review resource, 4 engineering blog posts).
**No source code was read** — the commercial product is closed; only the open-source predecessor is
public and was not fetched. Every figure below is **vendor self-reported** unless marked otherwise.

---

## What It Is

A packaged, self-hosted generative-AI platform aimed at banks, insurers, healthcare providers,
government and defence — buyers who cannot send data to a hosted model API. It sells the *whole
stack as one purchase*: inference serving, vector retrieval, document ingestion, an API gateway,
and an end-user workspace, installed inside the customer's own data centre, private-cloud VPC, or a
fully air-gapped network. Maturity: commercially shipping, with an appliance option (a pre-built
server shipped ready to deploy), a cloud-marketplace listing, hardware and data-centre partners, and
a managed-on-prem option operated by certified partners. Its open-source predecessor (a 2023
private-RAG framework, ~57k stars / ~8k forks self-reported) is still maintained and positioned as
the free developer-facing core; the commercial product adds multi-user, governance, and deployment
packaging.

The strategic bet is explicit and worth naming: **they are not selling model quality, they are
selling the absence of a per-token meter and the absence of an egress path.** Everything in the
architecture follows from those two commitments.

## Architecture & Key Patterns

Three layers, each sold as a separable component:

| Layer | Responsibility |
|---|---|
| **Serving/core layer** | Local model serving, GPU orchestration with dynamic allocation and failover, agentic RAG engine (hybrid search + multi-step retrieval + citation tracking), document-ingestion pipeline (OCR, metadata extraction, chunking, "100+ formats"), distributed async queues for ingestion/indexing/background jobs |
| **Gateway layer** | The single policy choke point: OpenAI- **and** Anthropic-compatible endpoints, token-scoped auth, per-token/user/team rate limits, admin-defined allow-lists of models *and* knowledge bases, guardrails with input/output inspection, full request/response audit capture, usage analytics |
| **Workspace layer** | End-user surface: chat, semantic search over internal corpora, an inline-AI document editor, shared projects with role-based access, group chats where several humans share one AI conversation, and named reusable automations for repeatable document work (summarisation, proposal drafting, structured extraction) |

Key patterns:

- **Gateway-as-enforcement-boundary.** Apps never hold infrastructure credentials or speak to a
  model directly; they authenticate only to a gateway instance whose configuration (allowed models,
  reachable knowledge bases, guardrails, limits) *is* the policy. A token inherits its gateway's
  governance rather than carrying its own. One project = one gateway = one isolation unit.
- **API-shape compatibility as the migration story.** Swap base URL + key, keep the existing agent
  tooling. This is the whole integration strategy — no proprietary SDK is advertised.
- **Model-agnostic serving.** Any open-weight or HF/GGUF-compatible family; the platform sells the
  orchestration, never a specific model.
- **Ship the workflow engine too.** A general-purpose automation tool is pre-deployed on the same
  box, so "integrate with our systems" does not require a second procurement.

## Notable Implementation Details

Four ideas from their engineering writing are transferable regardless of what one thinks of the
product:

1. **Action-level authorization, not app-level.** The argument: an agent holding a single credential
   can read large volumes of records, join information across systems, generate derivative files and
   trigger downstream actions in one short session, so the *same* identity produces wildly different risk
   depending on the action sequence. Their decision inputs are five: accountability (user + service
   account + agent identity + active role + delegated authority), exact resource (with labels and
   ownership), operation *verb* (read / search / modify / delete / share / approve / execute treated
   as distinct), session history (retrieval volume, repeated failures, prompt-injection signals,
   task drift), and — the good part — **mitigations instead of binary allow/deny**: narrow the
   dataset, strip write access, force re-auth, require approval, or isolate the operation.
   Plus progressive privilege (read-only first) and forced re-authorization at high-impact
   boundaries (external sharing, bulk access, financial actions).
2. **The agent session as a retained business record.** Six evidence categories per session:
   identity/authority, task + policy version + risk class + instruction hierarchy, data accessed
   (repos, files, records, timestamps, classifications), model+tool activity (model version, tool
   calls, parameters, failures, retries, external actions), human decisions (approvals, rejections,
   edits, escalations, reviewer identity), and outcome/disposition linked to the resulting artefact.
   Retention class is assigned **automatically at session close** from outcome × business process ×
   jurisdiction. They cite a six-year books-and-records floor from financial regulation as the
   worked example.
3. **Separate judgment from deterministic work.** Three step types: deterministic (schema
   validation, arithmetic, filtering, lookups, policy thresholds) → code or a rules engine;
   judgment (interpretation, synthesis, prioritisation) → the model, with eval criteria;
   human-authorized (payments, legal filings, clinical decisions) → explicit approval. Supporting
   rules: business logic never lives in provider-specific prompts, one trace id links
   input → transformations → model decisions → approvals → output, model permissions scoped to the
   minimum, and **all writes idempotent**. The stated payoff is testability: deterministic parts stay
   unit-testable while model variability is quarantined.
4. **Four-domain stack decomposition** used as a buyer's checklist: infrastructure (GPU, server,
   network, storage, redundancy) · model (selection, quantization, routing, context) · platform
   (ingestion, vector search, RAG/agents, connectors, multi-tenancy) · governance (access, audit,
   usage monitoring, rate limits, data boundaries). Their recurring argument — that what buyers
   underestimate is the infrastructure and operational choices rather than the model — is the honest
   part of the pitch.

## Strengths

- **One coherent policy plane.** Because every request crosses the gateway, attribution, audit,
  quota, model allow-listing and knowledge-base scoping are enforced in one place instead of N.
  Most self-built stacks scatter these.
- **Governance designed in, not bolted on.** Audit fields, retention classes and approval gates are
  specified at the architecture level, which is what actually clears a regulated procurement.
- **Deployment packaging is the real product.** Single-command install, driver/GPU auto-detection,
  an appliance option, and online / semi-air-gap / full-air-gap install patterns. Air-gap as a
  first-class mode (not a caveat) is rare and genuinely hard.
- **Cost model matched to the buyer.** Fixed infrastructure cost removes the per-token anxiety that
  kills multi-step agent designs — an agent that makes 400 calls costs the same as one that makes 4.
- **Open-source predecessor as the trust and distribution channel.** Developers adopt the free core;
  the enterprise buys the governance wrapper.

## Weaknesses / Limitations

- **Nearly every claim is unfalsifiable from outside.** A three-figure supported-format count,
  concurrency stated only in hundreds of users, and same-day time-to-production all carry no
  methodology, no workload definition, and no third-party verification. Two of their own pages
  contradict each other on deployment timeline, one giving a figure roughly an order of magnitude
  longer than the other.
- **Sizing is a lead-capture form, not a model.** The hardware calculator takes exactly two inputs
  (user band, use case) and publishes no formula, VRAM figure, or SKU. Capacity planning — the
  genuinely hard part — stays behind a sales conversation.
- **The governance blog posts are position papers, not designs.** No schema, no API, no storage
  format, no enforcement-hook detail. Useful as a requirements checklist; not as an implementation.
- **The gateway is a single point of failure and a single point of compromise.** Nothing public
  describes HA, failover, or what happens to policy enforcement when it is down.
- **Logging request *and response content* on every call** is a compliance feature that is
  simultaneously the largest sensitive-data store in the deployment. No retention, encryption, or
  access-control detail is given for the audit store itself.
- **Model-agnostic means the customer owns model risk.** Quantization, routing and context strategy
  are listed as *decisions the buyer makes*; the platform does not appear to opinionate them.
- **Vendor concentration.** Appliance, data centre, hardware and network partners are all named
  third parties — the "no lock-in" story is about model choice, not about the stack you inherit.

## Visible vs Hidden Metrics

**Visible (all vendor self-reported, none independently verified):** ~57k stars / ~8k forks / ~5k
developers on the open-source core · six compliance regimes claimed · deploy in under 3 hours ·
production in under a week · concurrency stated only in hundreds of users · 100+ ingestion formats · model range
8B → 405B · unlimited usage at fixed cost · named large-enterprise logos as users of the *free* core
(note the sleight: open-source adoption is cited as evidence for the commercial product).

**Hidden — the costs an adopter actually inherits:**
- **GPU capital and its idleness.** Fixed cost is fixed *whether or not you use it*. The per-token
  meter disappears; a depreciating GPU fleet sized for peak replaces it. Below some utilisation
  threshold the hosted meter is simply cheaper, and no published sizing model tells you where that
  line is.
- **Model-operations burden transfers to you.** Choosing, quantizing, evaluating, and re-evaluating
  open-weight models on every upgrade is continuous specialist work the platform does not remove.
- **The gateway becomes load-bearing.** Every app now depends on one internal service for auth,
  routing and audit. Its availability target becomes the availability target of all AI features.
- **Audit-store gravity.** Full request/response retention at six-year scale is a storage, indexing,
  encryption, access-review and e-discovery programme — usually underestimated at purchase.
- **Air-gap tax on updates.** No internet means every model weight, dependency, CVE patch and
  platform upgrade needs a controlled offline transfer path, with humans in it.
- **Appliance/partner coupling.** Hardware, data-centre and managed-operations partners are new
  vendor relationships and new renewal negotiations.
- **Learning curve is organisational, not technical.** Action-level authorization only works if
  someone maintains resource labels, data classifications and approval policies — a governance
  headcount, not a deployment step.

**Weighing:** the visible wins are real *only above a usage and sensitivity threshold*. For an
organisation with a hard no-egress mandate and steady high-volume usage, fixed cost plus a single
policy plane plausibly beats a metered API. For everyone else the hidden costs — GPU idleness,
model-ops headcount, audit-store gravity, air-gap update friction — dominate, and the honest verdict
is that the platform is a *compliance purchase*, not an economics purchase. The architectural ideas
(gateway as sole enforcement point, action-level authz with mitigations rather than deny,
session-as-record with auto-assigned retention, judgment/deterministic separation with idempotent
writes and a single trace id) are **separable from the product and cost nothing to adopt** — that is
where the value to us lies, not in the packaging.

---

## Phase 2 — Comparison against this platform

**Scope set by the owner 2026-09-21:** this platform is also moving toward regulated buyers, so the
reference work is a direct competitor on the same buyer question, not a neighbouring tool. Compared
on **regulated-industry readiness**.

**Evidence basis:** four read-only code sweeps of `autobot-backend/`, `autobot_shared/`,
`autobot-slm-backend/`, `docs/developer/`, `docs/architecture/`. Citations below are from those
sweeps; three load-bearing claims (audit tamper-evidence, retention wiring, dead compliance manager)
were re-verified directly in this session and held. Claims not re-verified are marked *(swept)*.

### Headline

**We are ahead on capability and behind on provability. Regulated buyers purchase provability.**
On retrieval quality this platform demonstrably exceeds what the reference work advertises. On the
governance spine — one enforcement point, one audit trail, one correlation id, one retention
schedule — the reference work has a coherent design and we have four-to-six partial ones. The gap
is not unknown to us: our own `docs/architecture/CONTROL_PLANE_MAP.md` (survey #16835, 2026-09)
already grades **8 of 17 control layers "Drifted"**. It is a known, unclosed gap.

### What We Already Do Better

| Capability | Evidence in this platform | Reference work |
|---|---|---|
| **Hybrid retrieval** | BM25 + dense in parallel, fused by Reciprocal Rank Fusion k=60 — `knowledge/search_components/hybrid_search.py:79-138`, `bm25.py:20-90`; `mode="hybrid"` is the default (`knowledge/search.py:622` (`_run_search` at :614)) *(swept)* | Claims "hybrid search"; no implementation visible |
| **Cross-encoder reranking** | Real `sentence_transformers.CrossEncoder` (`ms-marco-MiniLM-L-6-v2`) — `search_components/reranking.py:324-497`, default-on via `rag_config.py:46` *(swept)* | Not mentioned |
| **Agentic / iterative retrieval** | LLM query rewrite + up to 3 refinement rounds gated by a sufficiency verdict — `search_components/agentic_search.py:178,216-245`, default-on *(swept)* | Claims "agentic reasoning, multi-step retrieval"; no detail |
| **Citations, end to end** | `Citation` schema `api/schemas_chat.py:165-178` → built at `api/chat.py:658-679` → rendered in `CitationsDisplay.vue` *(swept)* | Claims "citation tracking" |
| **PII controls on the live path** | 14-type detector bank with BLOCK/REDACT/HASH policy — `a2a/pii_pipeline.py`, wired into every chat message via `security/chat_message_safety.py:58-114` *(swept)* | Claims "guardrails and input/output inspection"; unspecified |
| **Prompt-injection defence** | `security/prompt_injection_detector.py` + shared `security/content_firewall.py` *(swept)* | Not mentioned |
| **Egress engineering quality** | DNS-rebind-safe connector pinning, redirect re-validation, credential-header stripping across cross-origin redirects — `autobot_shared/security/ssrf_guard.py:107-305` *(swept)* | Not mentioned |
| **Model supply-chain integrity** | Exact revision + weight digest pinned, fails closed on mismatch — `autobot_shared/pinned_model_registry.py` *(swept)* | Not mentioned |
| **Scope of product** | Multi-modal, desktop/screen control, NPU acceleration, plugin surface | Out of scope entirely |

The retrieval stack is the one place where we would win a technical bake-off outright. It should be
the marketing spearhead, because it is real and theirs is a bullet point.

### Gaps & Opportunities — ranked by what blocks a regulated sale

**1. No single enforcement choke point.** *(swept + re-read)* There are at least three inbound
policy surfaces with three different credential systems: the external compat endpoints
(`api/openai_compat.py:293`, `api/anthropic_compat.py:237`, virtual `sk-` keys with model allow-list
and monthly budget), a separate MCP JSON-RPC surface with its own bearer/scope format and its own
limiter, and the internal chat UI (`api/chat.py`) which is JWT-authenticated and carries **none** of
the model allow-list, budget, or rate-limit checks. Internal agent tool calls use a fourth mechanism
(`middleware/builtin/permission_enforcement.py`). Rate limiting is per-IP, not per-token, so a
caller rotating client IP evades it on a fixed key. Tenancy (`TenantContext`,
`autobot_shared/user_management/base_service.py:22-43`) is real but never reaches the LLM path —
`org_id` is not passed from either compat endpoint, making the registry's per-org branch dead from
the gateway's perspective. **This is the single structural difference between the two products.**

**2. The audit trail cannot be produced on demand.** *(swept; tamper claim re-verified)* Six
parallel audit implementations (`services/audit/audit.py`, `services/audit/audit_log.py`,
`services/audit_logger.py`, `security_layer.py:669`, `models/workflow_audit.py`, plus middleware).
No cryptographic tamper-evidence anywhere — `security_layer.py:669-679` documents "tamper-resistant
audit log file (append-only)" over a plain `open(..., "a")`, and a repo-wide search for
hash-chaining primitives near audit code returns **0**. A docstring asserting a control that does
not exist is worse than silence: it is the exact thing an auditor tests and the exact thing that
turns a finding into a credibility problem.

**3. Configurable retention does not run.** *(re-verified)* The `retention_policies` table
(`user_management/models/retention_policy.py`, migration `20260604_051`) with per-user overrides and
an `anonymize_instead_of_delete` flag is exposed through an admin API — and the purge tasks never
read it. `tasks/chat_retention.py:31` takes a single global env value; the same holds for file,
audit and KB retention. The retention policy the product *presents* is not the retention policy that
*executes*, and the anonymize flag is stored but never honoured — deletion is always hard-delete.

**4. No end-to-end correlation id.** *(swept)* `session_id` threads input → tool calls → in-chat
approvals, then breaks twice: the durable `Approval` table (`models/approval.py:58-125`) has no
`session_id` column, and every LLM call mints its own unrelated `uuid4` (`llm_shared/models.py:172`).
`X-Request-ID` is read but never generated when absent (`middleware/tracing_middleware.py:217`).

**5. Approval gates are opt-in and mostly non-durable.** *(swept)* `enforce_work_item_approval()`
(`chat_workflow/tool_dispatch_guards.py:290-334`) returns early unless a work item declared the
category — so on an ordinary chat turn, credential-rotation tools are not gated. When it does fire
it appends an in-memory message rather than creating a row in the `approvals` table. Credential
*read/export* has no gate by construction — the catalogue only names rotation verbs.

**6. End-user SSO/MFA does not exist.** *(swept)* SSO, MFA and SCIM are wired only in the
fleet-admin console (`autobot-slm-backend/main.py:661-718`). For product end users there is
password + JWT only; `security/enterprise/sso_integration.py` is 916 lines referenced by nothing,
and the MFA model is an unwired stub. "Do you support SSO for our staff?" is a first-call question
in every regulated deal, and today the honest answer is no.

**7. The compliance layer is dead code.** *(re-verified)*
`security/enterprise/compliance_manager.py:45-52` defines a `ComplianceFramework` enum naming SOC2,
GDPR, ISO27001, HIPAA, PCI_DSS. Its only two references in the entire codebase are its own package
re-export. Scaffolding that names a framework it does not implement is a liability in a due-diligence
review, not an asset.

**8. Egress is a deny-list, not an allow-list.** *(swept)* Private/loopback/metadata ranges are
blocked, but any public host is reachable by default. `guard_egress=` appears at 28 call sites while
the shared client serves ~103, and ~51 files make direct `requests`/`httpx`/`aiohttp` calls outside
it entirely. A reviewer asking "can any code reach an arbitrary external host" gets "yes, by default."

**9. No orchestrated air-gap mode.** *(swept)* Telemetry is genuinely zero-egress and no
license/phone-home code exists — both real strengths. But `TRANSFORMERS_OFFLINE` defaults to False
and ~10 files call `from_pretrained`, so a cold air-gapped boot needs a pre-seeded cache and there
is no single switch, nor a test asserting zero outbound DNS.

**10. No data-residency / system-of-record register.** *(swept)* `CONTROL_PLANE_MAP.md` maps control
authority, not data lineage. Vector data lives in one large collection filtered by metadata rather
than per-tenant namespaces.

### Gap Ledger — our defects, owned by us

The reference work was a mirror, not a roadmap. Every item below stands on its own: it is a gap
against **our** regulated-readiness target and would need closing if no competitor existed. Nothing
here is filed, branched or committed with any reference to an external product.

Split by kind, because the two kinds deserve different urgency.

#### Class A — Defects: something claims to work and does not

These are the dangerous ones. Each presents a control surface that an operator, an auditor, or our
own engineers would reasonably believe is active.

| # | Defect | Evidence | Why it is Class A |
|---|---|---|---|
| A1 | Admin-configured retention never executes; `anonymize_instead_of_delete` stored and ignored; deletion is always hard-delete | `tasks/chat_retention.py:31` reads a flat env value; `RetentionPolicy` rows are never queried | An operator sets a data-handling policy and nothing happens — silent, and the failure mode is unrecoverable data loss or unlawful retention |
| A2 | Audit docstrings assert "tamper-resistant", "append-only", "immutable" over plain appends | `security_layer.py:669-679`; `services/audit_logger.py` docstring; `models/workflow_audit.py:22-27`; 0 hash-chaining primitives repo-wide | The claim is the defect. An auditor tests log integrity directly, and a false assertion converts a gap into a credibility failure |
| A3 | Sensitive-tool approval gate is opt-in per work item and produces no durable record on the common path; credential *read/export* has no gate at all | `chat_workflow/tool_dispatch_guards.py:290-334` returns early without a declared category | The gate exists, is documented, and does not fire on an ordinary chat turn |
| A4 | Per-key model allow-list and budget are bypassed entirely by the internal chat surface; rate limiting is per-IP, so a fixed key evades it by rotating client IP | `api/chat.py` imports no limiter; allow-list check guarded by `if api_key_record is not None:` (openai_compat.py:331) at `api/openai_compat.py:331` | Two enforced-looking controls with a documented bypass each |
| A5 | `ComplianceManager` names SOC2/GDPR/ISO27001/HIPAA/PCI_DSS and is referenced only by its own package re-export | `security/enterprise/compliance_manager.py:45-52`; 2 hits, both in `__init__.py` | Framework names in code read as capability in any due-diligence review |
| A6 | End-user SSO/MFA: a 916-line SSO framework and an MFA model stub, neither reachable | `security/enterprise/sso_integration.py`; `user_management/models/mfa.py` | Unfinished work, not dead code — **wire it in, never delete** (project rule) |

#### Class B — Structural gaps: never built

| # | Gap | Evidence |
|---|---|---|
| B1 | No single enforcement point — 3 inbound surfaces, 3 credential systems, 4th mechanism for internal tool calls; `org_id` never passed from the gateway, so the registry's per-org branch is unreachable | `api/openai_compat.py:361`, `api/anthropic_compat.py:308` both omit `org_id` |
| B2 | No correlation id spanning input → tools → model → approvals → output; breaks at `Approval` (no `session_id` column) and at each LLM call's own `uuid4` | `models/approval.py:58-125`; `llm_shared/models.py:172` |
| B3 | Six audit implementations; the consolidation toward `services/audit/audit.py` is documented in its own module docstring and incomplete | `services/audit/audit.py:5-17` |
| B4 | Egress is an address deny-list, not a destination allow-list; `guard_egress=` at 28 sites against ~103 shared-client callers; ~51 files call `requests`/`httpx`/`aiohttp` directly | `autobot_shared/http_client_manager.py:209-272` |
| B5 | No orchestrated air-gap mode — `TRANSFORMERS_OFFLINE` defaults False, ~10 `from_pretrained` sites, no test asserting zero outbound DNS from cold boot | `autobot_shared/ssot_config.py:2138` |
| B6 | Authorization is role-based only — no resource identity, no operation-verb granularity, no session-history signal, no graduated mitigation (narrow dataset / strip writes / force approval) short of allow-deny | `middleware/builtin/permission_enforcement.py`, `autobot_shared/tool_catalogue.py:64` |
| B7 | Idempotency covers opt-in HTTP POSTs only; internal tool dispatch is in-process and unprotected. `repetition_guard.py` is loop-detection, not replay-safety | `autobot_shared/idempotency.py`; `chat_workflow/tool_handler.py:3238` |
| B8 | No data-residency / system-of-record register; vector data is one large collection filtered by metadata rather than per-tenant namespaces | `CONTROL_PLANE_MAP.md` maps control authority, not data lineage |
| B9 | Agent sessions have no durable compliance record — `AgentSession` is an opaque resume blob, and the rich conversational record is file-based chat history | `models/process_run.py:104-117` |

#### The uncomfortable part

None of this is new information. `docs/architecture/CONTROL_PLANE_MAP.md` (survey #16835, 2026-09)
already grades **8 of 17 control layers "Drifted"** and independently reaches the same conclusion on
A1, A5, B3 and B4. The problem is not detection. We found these, wrote them down, and did not close
them. Any plan that produces another survey instead of merged fixes repeats the failure.

### Sequence

Ordered by *credibility risk per unit of effort*, not by size.

1. **A2 first — correct every false control claim.** Trivial effort, highest payoff. Either implement
   hash chaining or make the docstrings describe what the code does. A gap we state is a finding; a
   gap we mis-state is a credibility failure, and per `MEASUREMENT_DISCIPLINE.md` the stated gap is
   the contribution.
2. **A1 + A4 — make the configured control the executed control.** Wire the purge tasks to
   `RetentionPolicy`, honour `anonymize_instead_of_delete`, move rate limiting from IP to
   token/team, and close the allow-list bypass on the internal chat path. Both are moderate and both
   remove a live silent failure.
3. **A3 + A6 — finish the started work.** Default-on gating for sensitive categories with durable
   approval rows and credential-read coverage; wire the SSO/MFA code that already exists. Per
   project rule these are completions, not deletions.
4. **B2 + B9 — one trace id, one durable session record.** Moderate effort, and the single largest
   improvement to what we can actually show an auditor.
5. **A5 — wire the compliance layer in behind a real control, or state plainly in the code that it
   is scaffolding.** Never delete.
6. **B1 — gateway consolidation.** The structural bet. Does not start before an HA design exists,
   because collapsing to one enforcement point makes that point load-bearing for every AI feature.
7. **B4, B5, B6, B7, B8** — sequence after the above; each is independently schedulable.

### What this comparison does *not* change

Our retrieval stack is genuinely ahead and needs no work from this analysis. Hybrid BM25+dense with
RRF, a real cross-encoder reranker, default-on iterative retrieval with sufficiency gating,
end-to-end citations, and 14-type PII redaction on the live chat path are all real and all verified
above. The gap is the governance spine, not the capability. Effort spent broadening features here
would be effort not spent on the ledger above.

### Duplicate sweep — 2026-09-21

33 `gh issue list --search ... --state all` queries across the 15 ledger items, plus targeted
lookups. Verdicts below; **nothing filed yet**.

| Item | Verdict | Existing issue |
|---|---|---|
| A1 retention disconnected | **Duplicate — do not file** | #16846 *"admin_retention_policies.py is fully disconnected from the actual data-purge tasks"* — matched by 3 queries incl. `anonymize_instead_of_delete` |
| A2 false tamper-resistance claims | **New** | No match across 4 queries. Closest #14654 (schema bug), #3277/#4456 (closed, built the logging) |
| A3 approval gate opt-in / no durable row / credential read ungated | **Partly covered — file the delta only** | Covered: #13250 (gated twice, one path), #13421 (five surfaces, no shared record), #17043 (consolidation). Closed predecessors #11160, #11202, #14903. Delta = gate returns early with no work item, and credential *read/export* ungated by construction |
| A4 allow-list + budget bypass, per-IP limiting | **Budget half is a duplicate** | #16845 *"budget enforcement silently broken since April"*; #16857, #6588 (closed) adjacent. Delta = model allow-list skipped for JWT callers, limiter keyed by IP not token |
| A5 ComplianceManager dead | **Duplicate — do not file** | #16848 *"EU_AI_GOVERNANCE.md cites ComplianceManager as active audit infrastructure, but it's never instantiated"* |
| A6 end-user SSO/MFA unreachable | **New (capability), overlaps a dead-code issue** | #15154 covers the framework reading nonexistent policy files; the missing *login path* for end users is not filed. Cross-link #10193 |
| B1 no single choke point | **Almost certainly covered — read before filing** | #14904 *"the Gateway has been TEMP DISABLED since #881 and now carries a full governance stack nothing reaches"*; also #16971 |
| B2 no end-to-end trace id | **New** | No match. #14361 (closed) is Prometheus label cardinality, unrelated |
| B3 six audit implementations | **Closed-but-incomplete** | #6475 *"consolidate three parallel audit/event-log systems"* — closed; the count is now six |
| B4 egress coverage ratio | **Covered — add counts as a child/comment** | Umbrella #13623; #14901, #13625, #16378, #12979 |
| B5 no air-gap mode | **New** | `airgap` returned zero; #3275 (closed) is the only offline-mode issue |
| B6 role-only authz | **Largely covered — file the mitigation delta** | #15271 *"capability descriptors state what a tool is, never how far it may go"*, #13228, #13589, #15781, umbrella #13413 |
| B7 idempotency on internal dispatch | **New (narrow)** | #16760 is SLM-scoped; #15778, #15814 closed and HTTP-scoped |
| B8 residency / tenant namespaces | **New** | `data residency` returned **zero matches**; #15670 covers system-of-record generally |
| B9 durable agent session record | **New** | No match; #6746 (closed) is chat-state unification |

**Net: 3 outright duplicates, 1 needs reading first, 3 are deltas on existing issues, 7 genuinely new.**

### The systemic finding the sweep exposed

The searches kept returning the *same defect shape* from unrelated corners of the backlog:

> #16843 emergency_system_stop doesn't stop anything · #16857 three rate-limiter singletons never
> called · #16845 cost tracking broken since April · #14866 ownership enforcement has likely never
> been on · #12977 gates possibly enforced only in inert code · #16755 plugin capabilities granted
> at load and never checked · #14031 AgentLoop has no production caller · #14904 a governance stack
> nothing reaches · #16846 retention policy nothing reads · #16848 compliance manager never
> instantiated.

Every one is the same failure: **a control that exists, is documented, and does not execute.** The
regulated-readiness gap is not fifteen unrelated items — it is one repeated organisational failure
mode with fifteen instances. A buyer's auditor does not test features, they test controls, and this
pattern is precisely what such a test surfaces.

That suggests the highest-leverage item is not on the ledger at all: **a guard that fails CI when a
declared control has no production call path.** Without it, this list regenerates.

### Filed 2026-09-21

Umbrella **#17217** *"declared controls that do not execute — the regulated-readiness gap"*
(milestone v0.10.0), with 12 native sub-issues:

| Wave | Issues |
|---|---|
| 1 — stop the refill, correct what we mis-state (v0.10.0) | #17218 CI guard · #17219 tamper claims · #17220 approval gate inert · #17227 tool-dispatch replay |
| 2 — configured control = executed control, evidenceable runs (v0.11.0) | #17221 allow-list bypass · #17222 end-user SSO/MFA · #17224 correlation id · #17225 audit consolidation · #17229 durable session record (blocked by #17224) |
| 3 — structural (v0.11.0–v0.12.0) | #17223 three policy surfaces (HA design first) · #17226 air-gap mode · #17228 residency register |

Linked into existing scopes rather than duplicated: egress coverage measurements onto #13623,
authorization dimensions onto #15271. Already-tracked and linked: #16846, #16848, #16845.
Scope umbrellas referenced: #13413, #16524, #10193, #13916, #15773.

### Relationship wiring 2026-09-21

Adopted into #17217 (were parentless): #14866, #12977, #16755, #14904, #17190, #15154 — 18 children total.
Adopted into #13623 (egress umbrella, were parentless): #14901, #16378.
Blockers recorded: #17225←#16846 · #17229←#16846 and ←#17224 · #17220←#17043 · #17228←#15670.
Milestones assigned where absent: #16846, #16848, #16857, #17190 → v0.10.0.

**Two pre-existing umbrellas found during the wiring, both material:**

1. **#10603** *"wire built-but-disconnected machinery"* (open, v0.10.0) already names this exact
   failure mode — *"computed/built then discarded"* — scoped to efficiency/precision machinery.
   #17217 is the governance-domain sibling; cross-linked both ways rather than merged, and #17218's
   guard is shared work.
2. **#16835** *"map AutoBot's control plane"* is **closed (2026-09-17) with 13 open children**
   (#16839–#16851). A closed umbrella detaches its open children from any active track — which is
   the mechanical explanation for "we found these and did not close them". Needs a ruling: reopen,
   or re-parent the open children.

## Root-cause analysis — 2026-09-21

### Five repeating problems

Observed across this session's four code sweeps, the duplicate sweep, and the backlog probes.

| # | Pattern | Instances |
|---|---|---|
| P1 | **Merged but unreachable** — a control exists, is documented, has no production call path | #16846, #16848, #16845, #16857, #16843, #14866, #12977, #16755, #14031, #14904, #15154, plus the whole thesis of #10603 |
| P2 | **Merged alongside, not merged into** — N parallel implementations of one concept | 6 audit writers · 3 credential systems · 7 rate limiters · 4 copies of the egress decision · 5 approval surfaces · 3 authorization models · 2 semantic chunkers · 2 file-extension registries · 2 `EnforcementMode` enums |
| P3 | **Prose asserts what code lacks** — docstrings and docs describe controls that do not exist | "tamper-resistant"/"append-only"/"immutable" audit · content-firewall file coverage with no call sites · governance doc citing a never-instantiated manager · `CONTROL_PLANE_MAP.md` self-grading 8/17 layers "Drifted" |
| P4 | **Opt-in by default** — a control that must be requested, and mostly is not | `guard_egress` opt-in (28 of ~103) · idempotency requires a header · injection hard-block defaults off · claim verification defaults off · approval gate requires a declared work item |
| P5 | **Tracking decays into the same shape** — the structure meant to track the work acquires the defect | 6 closed umbrellas hold **19 open children** (#16835 alone holds 13) · umbrellas are **4.3× over-represented** in the oldest 100 open issues (18% vs 4.2% of the backlog) |

### The root cause

All five are the same mechanism:

> **"Done" is defined as *merged*, never as *reachable*. CI proves code compiles, lints, and passes
> tests its own author wrote. Nothing proves code is on a production path. So anything merged but
> unreachable is invisible to every gate the project has.**

Each pattern follows from that single omission:

- **P1** is the direct expression: unreachable code passes every gate, so nothing distinguishes a
  wired control from an unwired one at merge time.
- **P4** is P1's softer form. A default-off control is reachable but inert; it satisfies "merged"
  and produces the same runtime nullity.
- **P2** is the incentive consequence. Wiring into an existing seam is harder than adding a parallel
  one — and because nothing detects that the old path went dead, a second implementation costs
  nothing to land. Convergence is never forced, so divergence is free.
- **P3** is what fills the gap where verification should be. Documentation is written at merge time
  describing *intent*; no gate ties a prose claim to a call path, so the claim survives the code's
  death. This is why "tamper-resistant" outlived the absence of any hash chain.
- **P5** is the same rule applied to issues. An umbrella is closed when its work is *described* as
  finished rather than when its children are, because there too the completion test is narrative
  rather than mechanical.

### Why this is the cause and not just another symptom

The discriminating evidence is #10603. On 2026-06-28 an audit named this exact pattern —
*"computed/built then discarded"* — filed eleven children and closed five of them. The pattern then
produced **new** instances continuously through September: #16843, #16845, #16846, #16848, #16857,
#17190, #15154.

A cause that has been correctly named, partially remediated instance-by-instance, and continues to
generate fresh instances at the same rate is by definition untreated **at the cause**. Fixing
instances is what we have been doing; it has not changed the rate. That is the signature of a
missing gate rather than a missing effort.

The same reasoning retires the obvious alternative explanations. It is not carelessness — the
instances are found and written up rigorously, repeatedly, by the same people. It is not lack of
detection — `CONTROL_PLANE_MAP.md` detected 8 of 17 drifted layers and published it. It is not
priority — several instances sit in `priority: high` with milestones. Detection, diligence and
intent are all present; only the mechanical gate is absent.

### The falsifiable test

If the root cause is the missing reachability gate, then the guard in **#17218**, run with an empty
baseline, must independently rediscover the known instances. Its acceptance criterion is deliberately
written that way: *"reproduces at least 6 of the 10 known instances when its baseline is emptied."*

If it cannot rediscover them, this root-cause analysis is wrong and the cause lies elsewhere — most
likely in review practice rather than tooling. That is the check to run before scaling the guard's
scope.

### What follows

1. **#17218 is the fix**, and its scope should be read as broader than its title: not only declared
   *controls*, but any merged symbol presenting a production capability.
2. **P4 needs a default inversion**, not more instances closed — an opt-in control is P1 with extra
   steps. Each existing default-off gate needs an explicit ruling: default-on, or documented as
   deliberately advisory.
3. **P5 needs a closure rule** — an umbrella may not close while it holds open children, or its
   children re-parent on close. 19 children currently sit under closed parents.
4. **P3 needs the doc-to-callsite tie** — the cheapest version is #17219's correction pass; the
   durable version is a check that a doc claiming a control names the enforcing symbol, and that the
   symbol is reachable.

### Citation audit 2026-09-21

Re-verified the file:line citations published in the filed issues against the working tree. Confirmed exactly: `tool_dispatch_guards.py:310`, `models/approval.py` (0 hits for `session_id`), `llm_shared/models.py:172`, `ssot_config.py:2138`, `models/process_run.py:104`, `sso_integration.py` 916 lines, `mfa.py` 19 lines. **Wrong by ~18 lines and corrected in #17221 and #17223:** the allow-list guard is at `openai_compat.py:331` (not :313) and provider selection at :361 (not :343); anthropic equivalents :275/:308. Every finding held on re-verification — only the coordinates were off.

**Second citation audit:** running the new `verify-citations` gate over this doc flagged an ambiguous bare `search.py` reference at line 619. Resolving it showed the coordinate was also wrong — line 619 is `category: str | None = None`; the `mode: str = "hybrid"` default is at `knowledge/search.py:622`, `_run_search` at :614, and `enable_reranking: bool = False` at :230 (not :229). The finding held; the coordinates did not. The gate caught what the spot-check missed.
