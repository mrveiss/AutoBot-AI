---
tags:
  - research
aliases:
  - Multi-Agent Executive Advisor
---

# Source Analysis: AI Virtual Executive Team Assistant

## What It Is

A vendor-built AI product that presents a single coherent "virtual executive"
persona to the user, backed internally by eight domain specialist agents
(strategy, finance, HR, legal, operations, marketing, product, board
communications). Python/FastAPI backend, Next.js frontend, Anthropic Claude
as the LLM backbone with optional OpenRouter/local-model routing. Early-stage
but unusually well-documented: ~152 commits, 11 contributors, created
2026-06, Apache 2.0. Directory listing shows substantially more surface
(monitoring, briefing, onboarding, talent, staff-onboarding, MCP gateway,
committee review, clients) than the README's architecture doc describes —
the docs are stale relative to the actual module tree.

## Architecture & Key Patterns

- **Hidden multi-agent, single voice.** One orchestrator ("the Executive")
  is the only agent the user ever sees. It routes to specialists via a
  native Anthropic tool (`consult_specialist`) — the model decides who to
  call, not hardcoded logic — and runs the chosen specialists in parallel
  with `asyncio.gather`. The internal architecture is never exposed in
  responses.
- **Tiered model assignment.** Deep-reasoning specialists (strategy,
  finance, legal, board) get the top-tier model with extended thinking;
  routine specialists get a mid-tier model; routing/intent-classification
  and background memory extraction use the cheapest tier. No agent
  framework (no LangGraph/CrewAI) — direct SDK calls + FastAPI.
- **Provider abstraction with mechanical slug derivation.** A provider
  registry maps a common `LLMProvider` interface over direct-API, OpenRouter,
  and any OpenAI-compatible endpoint (local or hosted gateway). Anthropic
  model ids are translated to OpenRouter slugs by regex rather than a
  hand-maintained table, so new model releases route correctly without a
  code change. A feature-gate table silently disables Anthropic-only
  capabilities (prompt caching, extended thinking, server-side web search)
  when a call is routed off-Anthropic, instead of erroring.
- **Two-layer RAG.** Curated built-in domain knowledge (git-tracked
  Markdown, seeded into a vector store at startup) plus user-uploaded
  company documents (chunked, separate collection). Both are queried with
  a per-specialist domain-alias filter and injected into the *user turn*,
  never the cached system-prompt block.
- **Prompt-cache discipline as an explicit contract.** A fixed system-prompt
  render order (persona → company profile → knowledge index, each its own
  cache block) plus a written list of things that must never happen in a
  cached block (no `datetime.now()`, tool list must be sorted, JSON must be
  key-sorted, dynamic content only in the user turn). Claimed 70–85% cache
  hit rate after the first few turns.
- **Episodic memory via background extraction.** After every turn, a
  cheap-tier model runs a structured "extract anything worth remembering"
  tool call in the background (fire-and-forget task, strong reference held
  to survive GC), writing decisions/initiatives/advice to SQLite.
  `tool_choice=auto` lets the model skip the tool entirely on idle turns,
  keeping the store free of noise. Read path formats the last N decisions
  into a `<past_decisions>` block re-injected each session.
- **Atomic scheduler claim.** Due background actions are claimed with a
  single `UPDATE … RETURNING` (pending→running), with a startup sweep that
  requeues anything left `running` by a crash. Explicitly documented as
  single-instance-only — a second replica double-fires actions.
- **Adversarial self-review ("Committee").** After the Executive drafts a
  response, three reviewers (one fixed quality judge + two domain
  specialists drawn from whoever was actually consulted, with a fallback
  pair) critique it in parallel, then a single revision pass folds the
  critiques in. One pass only, no iteration — a bounded quality gate rather
  than an open-ended agentic loop.
- **Outbound anti-spam guard.** Every proactive external message (DM/email/
  chat) funnels through one chokepoint enforcing content dedup, a
  per-recipient rate cap, and quiet-hours/availability — fail-open by
  design (an internal lookup error allows the send rather than blocking
  it) and returns a reason string instead of raising, so the caller can
  decide to reword or reschedule.
- **External monitoring → alerts pipeline.** A watchlist of external
  sources is polled on a heartbeat, one adapter per source kind, each
  wrapped in its own try/except so one source's failure can't poison
  others; surviving signals feed the same triage/alert pipeline used for
  inbound messages, deduplicated via a unique key.
- **Eval-gated CI.** ~29 LLM-as-judge scenarios across 5 scored dimensions;
  CI fails on a hard floor score or a >10% regression on any dimension vs
  the base branch. Adding a new specialist agent has a documented checklist
  (register + prompt + knowledge docs + ≥2 eval scenarios) enforced by CI.

## Notable Implementation Details

- Deriving the OpenRouter slug from a Claude model id by regex (rather than
  a lookup table) means the mapping self-updates for new model releases —
  a small but clean way to avoid a stale hand-maintained constant.
- The provider feature-gate table is a "degrade gracefully, don't error"
  pattern: routing an agent to a non-Anthropic model silently drops
  caching/thinking/web-search rather than failing the call.
- The outbound guard's dedup compares a normalized 160-char prefix of the
  message against prior sends, clipped *before* normalizing — documented
  specifically so the stored and candidate strings stay comparable.

## Strengths

- Prompt-caching rules are written down as a contract with concrete
  "never do X" items, not left as tribal knowledge — a real defense
  against silent cache-hit-rate regressions.
- The provider/model abstraction is unusually clean for a young repo:
  one regex-driven mapping plus one feature-gate table, so a new provider
  doesn't require touching agent code.
- Fail-open, reason-returning guard design (outbound anti-spam) is a good
  template for any control that must never itself cause an outage.
- Bounded, single-pass self-review gives a cheap output-quality gate
  without the cost/latency risk of an open-ended critique loop.
- Evals are a CI merge gate, not a manual side script.

## Weaknesses / Limitations

- Single-instance scheduler is a hard scaling ceiling baked into the
  storage choice (SQLite `UPDATE…RETURNING`) — horizontal scaling needs a
  re-architecture, not a config flag.
- Episodic memory, audit log, alerts, and the scheduler all share one
  SQLite file — simple at small scale, a single write-contention and
  backup/restore unit as usage grows.
- Committee review is unconditionally single-pass: a bad revision has no
  second chance, and it triples the relevant LLM calls for any turn it
  runs on.
- Local-model support has real capability cliffs the repo acknowledges but
  a user could easily miss: no caching, no extended thinking, no
  server-side web search, and routing quality depends on the local model
  being strong at tool use.
- Actual module surface (monitoring, briefing, talent, staff-onboarding,
  MCP gateway, clients, committee) has outgrown the architecture doc, which
  still describes an earlier, smaller shape.

## Visible vs Hidden Metrics

- **Visible:** self-reported star/fork counts that are high relative to an
  ~11-contributor, ~152-commit, ~3-month-old repo (not independently
  verifiable — treat with skepticism rather than as an adoption signal); a
  claimed 70–85% prompt-cache hit rate (plausible given the documented
  discipline, but no public benchmark); an eval-gate score threshold that
  is self-graded by the vendor's own judge-model harness, not
  independently verified.
- **Hidden:** the single-instance scheduler and shared-SQLite design are
  invisible in the feature list but cap horizontal scaling; the Committee
  review multiplies per-turn LLM cost for any response it covers; the
  local-model path's capability cliff (cache/thinking/search all silently
  off) is easy to miss until cost or quality shifts; a small team
  maintaining 20+ subpackages is a real long-term maintenance load that a
  feature tour doesn't surface.
- **Weighing:** for the product's own stated scope (single-tenant/small-team
  executive-assistant use case) the hidden scaling ceiling doesn't bite —
  it only matters past a size this design was never meant to reach. The
  visible wins that matter here — the caching contract, the provider
  abstraction, and the fail-open guard pattern — are cheap to evaluate as
  *patterns* independent of whether the popularity signal reflects real
  adoption.

---

## AutoBot Comparison: reference work → AutoBot

Focus: Company OS / "CEO as employee" — AutoBot's `llc/` module already models
a company with agent-or-human role holders, so the comparison centers on
where that maps onto the reference work's single-hidden-persona design.

### What We Can Adopt

**1. Layered prompt-cache contract with written invariants**
- Applies to: `autobot-backend/llm_shared/providers/anthropic.py`
  (`_apply_system_content`, line 357) — the only `cache_control` site in the
  backend, and the general prompt-assembly path any role-holder agent's chat
  turn goes through (`autobot-backend/chat_workflow/llm_handler.py`).
- Already-exists audit: `grep -rl cache_control autobot-backend/` → one hit.
  It wraps the *entire* system string in a single ephemeral block; there is
  no split between stable content (persona, company profile) and per-turn
  content, and no written rule against dynamic content leaking into it.
- Visible benefit: a cache-hit-rate improvement is plausible wherever
  company-profile/KB context currently rides inside the same block as
  rotating content, busting the cache every turn. Hidden cost: prompt-
  assembly code gets more complex, and prose-only discipline ("never put X
  in the cached block") is exactly the failure mode this repo's own
  measurement doctrine warns about — it needs a guard test, not just a
  comment.
- Verdict: **adopt-with-conditions** — worth doing for the LLC/company-agent
  prompt path specifically, paired with a regression guard rather than
  documentation alone.
- Effort: moderate.

**2. Outbound proactive-message anti-spam guard (fail-open dedup + rate cap + quiet hours)**
- Applies to: `autobot-backend/integrations/slack_integration.py`,
  `autobot-backend/services/telegram_bot_service.py`, and any proactive send
  triggered off `autobot-backend/llc/scheduler/heartbeat_scheduler.py`.
- Already-exists audit: `grep -ril quiet_hours .` → zero hits repo-wide;
  `grep -n "rate_limit|throttle"` in both integration files → zero hits.
  Confirmed absent.
- Visible benefit: closes a live governance hole for any role-holder agent
  (CEO or department lead) that can message a human proactively off a
  heartbeat/routine trigger — today nothing stops a duplicate or 3am send.
  Hidden cost: another piece of state to maintain; if built fail-closed
  instead of fail-open, it becomes a new way to silently drop a wanted
  message — the fail-open, reason-returned design is the part worth copying,
  not just the feature.
- Verdict: **adopt** — real unguarded surface, low novelty risk since
  `llc/services/activity_log.py` already records sends and can back the
  dedup lookup instead of a new table.
- Effort: moderate.

**3. Bounded single-pass adversarial self-review for outward responses**
- Applies to: wherever a role-holder agent's response is finalized before
  reaching the user (`chat_workflow/llm_handler.py`); reviewer selection
  could reuse `llc/services/role_assignment.py` to pick from whichever
  roles were actually consulted this turn, mirroring the source's
  "consulted-first, fallback pair" reviewer selection.
- Already-exists audit: `grep -rilE "critique|self.review|quality_judge|revision.pass|second.opinion" chat_workflow/ llc/` →
  `llc/models/review_gate.py`, `llc/api/review_gate_policies.py`,
  `llc/services/review_gate.py`, and `llc/services/findings_verify.py`, all
  **per-work-item** human/cross-vendor approval gates (bug triage, findings),
  not a response-level critique-and-revise pass on ordinary chat turns. No
  equivalent exists for the latter.
- Visible benefit: a cheap, bounded quality gate directly on-theme for
  "CEO as employee" — other role-holders (a CFO- or GC-equivalent agent)
  sanity-checking the CEO's answer before it ships, the way a real executive
  team would. Hidden cost: triples relevant LLM calls on any gated turn, and
  single-pass means a bad revision has no second chance.
- Verdict: **adopt-with-conditions** — gate it behind a `review_gate.py`-style
  per-company/per-type opt-in policy rather than running unconditionally, so
  it inherits AutoBot's existing governance model instead of adding a second
  ungated policy surface.
- Effort: significant (touches the live response path; needs its own eval
  coverage).

**4. Curated built-in domain-expert knowledge seeded per role**
- Applies to: `autobot-backend/llc/kb/collections.py` and role-based context
  assembly for a CEO/department-lead agent's turn.
- Already-exists audit: `ls autobot-backend/llc/built_in_templates/` → 4
  generic team-*structure* JSON templates (customer-ops, research-team,
  content-team, software-team), no content library; `grep -rn
  "builtin_knowledge|curated" llc/kb/*.py` → zero hits; `find llc -iname
  "*.md"` (excl. tests) → zero files. Confirmed: no built-in domain-
  knowledge layer exists. Everything in `llc/kb/` (decision logs, diaries,
  handoff briefs, sprint summaries) is *output* of the company's own
  operation, not curated *input* expertise.
- Visible benefit: today a freshly-created company's CEO/CFO-equivalent
  role-holder agents have zero baseline domain expertise until the company
  accumulates its own KB — a cold-start gap the source's two-layer design
  (built-in + company-specific, both live from day one) doesn't have. Hidden
  cost: curating/maintaining an expert-level knowledge library is a content-
  ownership burden distinct from code, and it goes stale (legal/tax
  frameworks change) in a way code doesn't.
- Verdict: **adopt-with-conditions** — valuable for the "role-holder agent
  should arrive competent, not blank" framing, but content-maintenance cost
  means starting with 1–2 of AutoBot's most commonly agent-held roles rather
  than all domains at once.
- Effort: moderate for retrieval plumbing (a new seeded collection + domain
  filter — both patterns the KB module already has for company docs),
  significant and ongoing for content creation.

### What We Already Do Better

- **Role/reporting-line modeling.** `llc/models/role_assignment.py` +
  `reporting_line.py` + `company_ceo.py`: any role — including CEO — can be
  held by an agent *or* a human, with full tenure history (`ended_at`, rows
  never deleted), a bounded cycle-guarded default reporting chain, and a
  schema-enforced one-CEO-per-company invariant. The source's `people`/
  `departments` tables are an informational roster; its 8 specialists are
  hardcoded-AI-only Python classes with no human-holder concept and no
  occupancy history. AutoBot already treats "who is the CEO" as a
  first-class, swappable, audited fact — and models the *role* generically
  rather than hardcoding a fixed 8-seat C-suite, so an AutoBot company isn't
  limited to the source's specific roster.
- **Distributed scheduler claim.** `llc/scheduler/heartbeat_scheduler.py`
  claims work via an atomic Redis `zrem` with a running-state marker, so a
  re-claim after a crash is safe with multiple workers. The source's SQLite
  `UPDATE…RETURNING` claim is explicitly documented as unsafe across more
  than one process — AutoBot's equivalent already scales horizontally.
- **Company structure breadth.** `llc/models/board.py`, `budget.py`,
  `goal.py`, `sprint.py` (files confirmed present) give the company object
  board governance, budget tracking, goals, and sprint planning built into
  the org model itself. The source's company context is a single gitignored
  YAML profile plus uploaded docs — no equivalent structured objects.
- **Provider registry maturity.** `llm_shared/provider_registry.py` +
  `provider_degradation.py`: ordered fallback chains, per-conversation
  provider override, and cross-worker (Redis-backed) health/degradation
  marking with a distinct non-expiring "needs re-auth" cause. The source's
  registry does slug-mapping and static feature gating but has no fallback
  chain or live health tracking.

### Gaps & Opportunities

Priority order, by impact for the "CEO as employee" framing:
1. **Outbound anti-spam guard** — cheapest, closes a live, currently-open
   governance hole the moment any role-holder agent messages a human
   proactively.
2. **Prompt-cache layering** — pure cost/latency win, no product surface
   change, moderate effort.
3. **Bounded self-review committee** — the most on-theme adoption (other
   role-holders reviewing the CEO's answer) but the highest running cost;
   needs to be opt-in, not default.
4. **Curated domain-expert knowledge per role** — highest long-term value
   for making a newly-assigned role-holder agent competent on day one, but
   the only item here with an ongoing content-maintenance cost rather than a
   one-time engineering cost.

### Specific Code/Files Affected

| File | Change |
|---|---|
| `autobot-backend/llm_shared/providers/anthropic.py` | Split the single `cache_control` block into layered blocks (stable vs. per-turn content) |
| `autobot-backend/chat_workflow/llm_handler.py` | Prompt-assembly site for both the cache-layering fix and the self-review hook |
| `autobot-backend/integrations/slack_integration.py`, `autobot-backend/services/telegram_bot_service.py` | Add the outbound anti-spam chokepoint before any proactive send |
| `autobot-backend/llc/services/activity_log.py` | Reuse as the delivery-history source for outbound dedup, instead of a new table |
| `autobot-backend/llc/services/review_gate.py` | Extend the existing policy model to cover an opt-in response-level review pass |
| `autobot-backend/llc/services/role_assignment.py` | Source of "who was consulted this turn" for dynamic reviewer selection |
| `autobot-backend/llc/kb/collections.py` | Register a new built-in, role-scoped knowledge collection alongside the existing company-docs collection |
| `autobot-backend/llc/built_in_templates/` | Where a curated-knowledge manifest per role would live, alongside the existing team-structure templates |

### Workflow Gaps (follow-up)

The reference work ships 18 pre-built "executive deliverable" workflows
(`board_prep`, `investor_update`, `fundraising_prep`, `ma_evaluation`,
`annual_plan`, `quarterly_plan`, `mbr`, `org_design`, `comp_refresh`,
`exec_search_brief`, `risk_register`, `crisis_comms`, etc.) grouped into 6
UI sections, each a `WorkflowBase` subclass that streams plan → intermediate
→ final-Markdown-artifact events and persists run state across restarts.

**Already-exists audit:**
- `autobot-backend/workflow_templates/types.py` — `TemplateCategory` is a
  closed enum: `SECURITY, RESEARCH, SYSTEM_ADMIN, DEVELOPMENT, ANALYSIS,
  COMMUNITY`. No board/governance/people category.
- `grep -ril "board_prep|investor_update|fundraising_prep|mbr\b|gtm_launch|pricing_review|churn_deep_dive|crisis_comms|risk_register" autobot-backend/ autobot-frontend/src/`
  → zero hits. No equivalent template exists under any name.
- `grep -rl "workflow_templates|workflow_automation|WorkflowTemplateManager" autobot-backend/llc/` → zero hits, but this grep was too narrow — see
  correction below.
- `autobot-backend/services/workflow_automation/` already has
  `persistence.py` + `state_machine.py` — run-state survival across
  restarts is **already handled**, on par with or ahead of the source's
  `persistence.py`. Not a gap.

**Correction (post-filing re-audit):** the LLC module has its own,
already-partially-built bridge that the grep above missed because it lives
outside `llc/`: `models/workflow.py::Workflow` (a canonical, company-
scopable workflow identity table), with `llc/services/workflow.py` +
`llc/api/workflows.py` giving it company-scoped CRUD (landed, #14210,
closed) and `llc/models/role_workflow.py` attaching a workflow to a role
so it survives holder turnover, plus process-node reads (landed, #13963,
closed). That foundation work explicitly scoped **out** two things, which
is where the real gap sits: (a) UI to create a workflow or attach it to a
role — already tracked separately in #14409 (open, v0.13.0) — and
(b) **execution**: nothing runs an attached workflow against live company
state (board/budget/goal) or writes its result back to `llc/kb/decision_log.py`.
Neither #14409 nor #14617 (a Backlog decision issue about drafting
workflows *from documents*, a different question) covers (b). "Company OS"
and "workflow" are explicit v0.13.0 milestone capability areas, so this
finding lands on ground already being worked — no new issue is filed for it
here; see the Verdict below for how it's scoped against the pre-existing
work.

**What we already do better:** the source's 18 workflows are each bespoke
`WorkflowBase` Python subclasses (one class per deliverable). AutoBot's
`WorkflowTask` steps are data-defined (`prompt`/`command`/`tools_allowed`/
`tools_denied`/`estimated_duration_seconds`) with variable substitution and
complexity levels — a more general, reusable execution engine. The gap is
not engine capability, it's (a) zero content in an executive-deliverable
category and (b) no bridge from that engine into the company object model.

**Verdict: adopt-with-conditions.** This is the single most product-visible
gap found across both passes — a CEO/board-role-holder agent producing a
real board deck or investor update, grounded in the company's own
goal/budget/board data, is the clearest "CEO as employee" payoff of
anything reviewed. But it should be sequenced *behind* the LLC↔workflow
bridge, not shipped as a standalone template pack: without that wiring the
output can't read real company state or write back to the decision log, and
without going through `review_gate.py` a board-facing artifact ships with
no human-review option — the same governance surface every other company
deliverable already gets. Effort: **significant** — this is an integration
layer, not a content pack, with the content itself (18 templates × domain
structure) as a second, separately-schedulable cost on top.
