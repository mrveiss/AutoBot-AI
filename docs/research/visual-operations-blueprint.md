# Visual Operations Blueprint — capability research and Company OS audit

> **Tracking:** umbrella [#13935](https://github.com/mrveiss/AutoBot-AI/issues/13935)
> (children #13936–#13943). Analysed 2026-08-10.
>
> Per repo policy, the third-party product examined is described by capability only; its name,
> company and URLs are deliberately absent. What matters here is the capability shape and what our
> own audit found.

## 1. The capability examined

A commercial SaaS "visual operations blueprint": a canvas where an organisation maps how work
actually moves, except the map is not a drawing — it is a **connected object graph**. Steps, roles,
tools, data attributes and costs are shared nodes, and the canvases are *projections* over one
relational model. Change a role once and every process referencing it updates.

Its pitch is a visibility gap — the operating model lives in people's heads and in third-party SaaS,
invisible to both colleagues and agents — and its differentiator is that a structured graph can be
served to AI agents over a standard tool protocol.

### The pieces worth naming

| Piece | What it does |
|---|---|
| Process canvas | sections → steps → connectors; per-step sidebar for requirements |
| Team/role canvas | role cards showing how one role contributes across *all* processes |
| Tool canvas | which software powers which step, with lifecycle and monthly/annual cost |
| Shared views | audience-scoped projections that stay synced instead of being duplicated |
| Rule-based colouring | declarative rules colour the graph by status / role / tool |
| Costing | step cost = time × frequency × role rate, plus tool cost |
| Change log | change records with status, owner and tool filter; list / board / calendar |
| Agent seam | agents read the whole blueprint; writes are proposal-with-documentation |
| Generation | builds real editable objects from a prompt, a whiteboard photo or a CSV |

### The four modelling ideas that actually transfer

1. **The executor is a typed field on every step** — person / automation / AI agent / empty. That
   makes "what share of the operation is already automated, and what is unowned" a *query* rather
   than a workshop.
2. **Views are projections, not copies.** The classic failure of process documentation is the
   summary copy drifting from the operator copy. Making the audience a filter kills that by
   construction.
3. **Presentation is derived from data.** Colour comes from declarative rules over status/role/tool,
   never hand-applied.
4. **Import beats authoring.** Prompt, screenshot, CSV and live sync from automation platforms all
   attack the real adoption blocker: nobody hand-draws forty processes.

### Where it is weak

- **Nothing verifies the blueprint against reality.** No drift detection, no execution telemetry
  feeding back, no "this step's tool was decommissioned". A blueprint that cannot detect its own
  staleness is a confidently-wrong oracle — and serving it to agents industrialises the error.
- **Costing inputs are self-reported.** Time and frequency are typed by a human; the resulting
  precision is presentation, not measurement.
- **The "AI agent" is a label on a step**, not an executor that runs.
- **Export is flattened** — steps and connectors only. Roles, tools, attributes, costs and statuses
  never leave. The graph is the lock-in.
- **Curation debt is the whole product.** Every node is a hand-maintained record with no automatic
  refutation; the cost is continuous, falls on the busiest people, and is invisible until wrong.

### Visible vs hidden metrics

**Visible:** feature breadth, per-editor pricing, agent-protocol access, bring-your-own-key.
All self-reported; no independent benchmark or audited ROI figure was published.

**Hidden:** continuous curation debt; confident-wrong amplification once agents consume a stale
graph; a second source of truth for anything already encoded in code or config; per-seat pricing
that taxes exactly the behaviour the model needs (many people keeping their own area current); and
the change-management cost of asking an organisation to think in a relational model rather than in
diagrams.

**Weighing:** for a company whose operations live in humans and third-party SaaS, the hidden costs
are worth paying. For one whose operations are **already executable code**, they invert: the
blueprint's authority is unearned, its content duplicates the code, and its agent seam magnifies the
error. The concept is only safe when the graph is **derived from the executing system and can detect
its own drift**. That inversion is the interesting question — and it is the one the product does not
answer.

## 2. Audit — what Company OS already is

Company OS is the **LLC module**: `autobot-backend/llc/` (24 model files, 30+ API routers, 8
execution adapters) and `autobot-frontend/src/views/llc/` (30 views). The audit's purpose was to
stop us building anything we already own.

| Capability | Ours | Verdict |
|---|---|---|
| Workspace / org | `llc/models/company.py`, sub-company tree | exists, richer (nested companies) |
| Roles | `MembershipRole`, `AgentOrgNode.org_role` | exists, RBAC-shaped |
| People | `llc/models/membership.py` — human users only | exists, **split** (see §3) |
| AI agents | `llc_agent_hires`, `AgentOrgNode`, `LLCAgentStatus` (9 states) | **far richer** |
| Tools | no company-scoped tool object | gap (deliberately not filled — §5) |
| Credentials | `llc/models/secret.py` + `autobot_shared/secrets_vault.py` | **we are ahead** |
| Steps / edges | `components/workflow/WorkflowCanvas.vue` | exists, wrong scope |
| Change log | `work_item.py`, `activity.py`, `approval.py`, `finding_proposal.py` | **we are ahead** |
| Costing | `llc/api/costs.py`, `llc/models/budget.py` | **we are ahead** (measured) |
| Agent protocol seam | `autobot-backend/mcp/`, `api/mcp_registry.py` | exists, gated by #13228 |

### The decisive audit result

`autobot-frontend/src/components/workflow/WorkflowCanvas.vue` is **already** a 488-line node/edge
editor: pan/zoom, node drag, port-to-port connection drawing, SVG bezier edges, auto-layout, node
types `step | condition | switch | vision-*`. It is wired into `views/WorkflowBuilderView.vue`
(2235 lines) under `/automation/*`. `autobot-frontend/package.json` contains **no** graph library.

We do not need a canvas. We need the canvas we own to have an **org identity** — and, since Company
OS absorbs the automation module, that is a consolidation rather than a fork.

## 3. Findings

**F1 — the org chart's human branch can never render** ([#13936](https://github.com/mrveiss/AutoBot-AI/issues/13936), fixed in PR #13945).
`llc/api/companies.py:837` declares `OrgChartNode.is_human: bool`; line 969 — the only construction
site — hardcoded `is_human=False`, and `llc_company_memberships` was never joined. Meanwhile
`views/llc/OrgTreeNode.vue` already styled `is_human` distinctly and the drawer already branched on
it. The UI was built for people; the data path never existed. Same class as the lying-detector
cluster in #13852.

**F2 — the human/agent discriminator is untyped** ([#13937](https://github.com/mrveiss/AutoBot-AI/issues/13937)).
`llc/models/work_item.py:112` — `assignee_type` is a bare `String(16)`, with no enum in
`llc/models/enums.py`, whose own docstring declares itself the SSOT that exists to prevent exactly
this. Any executor rollup would group by unvalidated free text and report a confident wrong count.

Note the human/agent unification **already exists at the assignment level** (`assignee_type` +
`assignee_agent_id` + `assignee_user_id`, delivered under #10532). It is the org-chart level and the
type constraint that were missing — a narrow gap, not a new subsystem.

## 4. What we already do better

1. **Our agents execute.** Nine-state lifecycle, budgets, heartbeat runs, pause/resume/terminate
   controls, replay logs, and 8 adapters under `llc/adapters/`. Theirs is a coloured label.
2. **Credentials.** `LLCSecret` is encrypted, versioned, revocable and attributed, behind the
   canonical vault. Theirs is "connect your account" with no visible grant/audit/revocation plane.
3. **The work plane.** `epic → feature → pbi → task/bug/subtask/spike/risk`, sprints, boards,
   backlog, Gantt, goal trees, and six approval gates. Their equivalent is a flat five-status list.
4. **Cost is measured.** `llc/api/costs.py` normalises real provider token usage and quota windows.
5. **Portability.** `llc/models/export.py`, `llc/api/portability.py` — versus a flattened export.

**Strategic consequence:** their fatal flaw is that nothing verifies the blueprint. We are the only
one of the two that can close that loop, because we already hold execution telemetry — heartbeat
runs, adapter outcomes, token spend, work-item transitions. "A step marked live whose bound agent
has not run in 30 days" is a query we can actually write.

## 5. Adoption decision — GUI only

Owner decisions, recorded 2026-08-10:

1. **Adopt GUI patterns only.** No external data model, vocabulary or naming. Every surface binds to
   Company OS functionality that already exists, or it is not built.
2. **Extension, never replacement.** All 17 nav entries in `components/llc/LlcSidebar.vue` stay. No
   current Company OS screen is removed or rebuilt.
3. **People are polymorphic — agent · user · contact.** An *agent* is a hired executor; a *user* is
   a human with an account; a *contact* is a human who appears in a process (the supplier you email,
   the customer you call) with **no account, who must never be able to log in**. A contact is a
   separate entity, never a `users` row — `users` is the authentication boundary, and putting
   non-authenticating identities inside it makes every auth column one that needs a special
   exclusion. Audit found no contact entity exists today; the only `PERSON` concept in the codebase
   is NLP entity extraction over documents, which is not an operational actor.
4. **Company OS absorbs the automation module.**
5. **The canvas is built inside the Org Chart**, which already exists per company and is not fully
   built. It is the native place to display teams and people. Not a new nav entry.
6. **Our style:** `design-system/tokens.ts`, existing `autobot-*` token classes, and all 11 locales
   (`ar de en es fa fr he lv pl pt ur`; four are RTL). No graph library.

### Adopted (children of #13935)

| # | Pattern | Wave |
|---|---|---|
| [#13936](https://github.com/mrveiss/AutoBot-AI/issues/13936) | org chart reports `is_human` honestly | 1 |
| [#13937](https://github.com/mrveiss/AutoBot-AI/issues/13937) | `AssigneeType` in the enum SSOT | 1 |
| [#13969](https://github.com/mrveiss/AutoBot-AI/issues/13969) | contact entity — a process human with no account | 1 |
| [#13938](https://github.com/mrveiss/AutoBot-AI/issues/13938) | one People surface: agent · user · contact | 1 |
| [#13939](https://github.com/mrveiss/AutoBot-AI/issues/13939) | canvas as a view mode inside Org Chart | 2 |
| [#13940](https://github.com/mrveiss/AutoBot-AI/issues/13940) | node sidebar: fixed slot order + icon rail | 3 |
| [#13941](https://github.com/mrveiss/AutoBot-AI/issues/13941) | rule-based colouring + legend | 3 |
| [#13942](https://github.com/mrveiss/AutoBot-AI/issues/13942) | executor rollup: person / automation / AI agent / unassigned | 4 |
| [#13943](https://github.com/mrveiss/AutoBot-AI/issues/13943) | "View As" role lens | 4 |

### Rejected — do not re-propose

- **A tool/stack register as a new data plane.** No company-scoped tool object is to be created; it
  would be curation debt with nothing to anchor it.
- **A credential-reference binding on canvas nodes.** The sidebar may *display* an existing
  `LLCSecret` reference; it must never hold a value. Their connect-your-account model is rejected
  outright — it has no grant/audit/revocation plane.
- **Graph-grounded note generation.** Not GUI, and blocked on #13686/#13687 — 2 of 5 context layers
  structurally cannot render, so we would ship a generator grounded in layers that return nothing.
- **Serving the operations graph over the agent protocol.** Rejected until #13228 lands. The seam
  currently bypasses canonical RBAC via a default-allow blocklist; exposing the org/role/credential
  graph through it converts one authorisation gap into total operational disclosure.
- **The role lens as an authorisation boundary.** It is a presentation filter and must be marked as
  one. It must not reuse `MembershipRole` — two mechanisms that both look like authorisation is the
  defect shape tracked in #13250.

### Not audited — verify before acting

Whether a data-dictionary / attributes layer exists anywhere in our codebase (their "entities and
attributes" plane). No claim is made either way; grep and read before filing anything on it.

Separately noted but unverified: both `autobot-frontend/src/design-system/tokens.ts` and
`autobot-frontend/src/design-tokens/tokens.ts` exist. If that is genuine canonical-source
duplication it belongs to the #13916 umbrella — read both before claiming it.

## 6. Vocabulary hazard

`CoWorkerType {agent, human}` and `AssigneeType {user, agent}` (`llc/models/enums.py`) answer the
same question with different member names. A same-name sweep cannot see this — only comparing member
sets does, which is the #13845/#13846 lesson. It has already produced a live bug: #13954, a Kanban
swimlane filtering on `'human'` against a backend that only ever writes `'user'`, so the column never
matched a row. The axis is about to become three-valued (agent / user / contact), so it is tracked as
#13970 and must be settled rather than mechanically renamed.
