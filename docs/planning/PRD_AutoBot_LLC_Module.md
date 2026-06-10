---
tags:
  - planning
  - llc
  - module
  - prd
aliases:
  - LLC PRD
  - AutoBot LLC Module PRD
  - Autonomous Agent-Company Module
status: current
---

# Product Requirements Document
# AutoBot LLC — Autonomous Agent-Company Module

**Document status:** Draft v1.0  
**Date:** 2026-05-19  
**Owner:** mrveiss  
**Target branch:** Dev_new_gui  

> **Read first:** [The AutoBot Platform Model](../architecture/PLATFORM_MODEL.md) and the
> [LLC module overview](../llc/_index.md). This PRD assumes the platform model — a small
> core, the Service Lifecycle Manager (SLM) management layer, and modules on top.

---

## 1. Executive Summary

**AutoBot LLC is a module you install on AutoBot** — an autonomous *agent-company*. It
lets operators define companies, build org charts of AI agents and human workers, set
strategic goals, plan and execute work through a full product backlog hierarchy, enforce
budgets, govern decisions through approval gates, and monitor costs — all from a single
control plane.

LLC is built **on the platform's bones**, not beside them. Rather than reimplementing
infrastructure, its agents **inherit** the primitives the AutoBot core already provides:

| LLC needs… | …inherited from the platform core |
|------------|-----------------------------------|
| Agents that remember across runs and share organizational context | **Institutional memory** — the Knowledge Base (RAG pipeline) + memory graph |
| Affordable 24/7 autonomous execution | **Local inference at zero marginal cost** — models run on hardware you own |
| Wiring agents into scheduled, event-driven work | **Hooks** — the platform's extension points and plugin system |
| Budget caps, approval gates, and access control | **Governance** — RBAC, review gates, and budgets enforced by the core |

Because the hard parts (memory, inference, governance, multi-modal processing, the LLM
gateway, WebSocket chat) already live in the platform, LLC stays small relative to what
it delivers. It contributes the *company-shaped* layer — companies, org charts, goals,
backlogs, sprints, heartbeat scheduling, board governance, and cost tracking — and leans
on the core for everything else.

This is not a bolt-on script and not a standalone product. It is a module that unifies
AutoBot's existing capabilities under a company-centric, goal-anchored, budget-governed
operating model.

---

## 2. Problem Statement

### 2.1 Current State

AutoBot today provides powerful individual capabilities: multi-provider LLM routing, a rich knowledge base, a streaming chat interface, multi-modal agents, workflow execution, browser automation, and code analysis. However, these capabilities operate in isolation:

- There is no concept of a **company** as a first-order entity that owns agents, goals, budgets, and work.
- Agents cannot be **autonomously scheduled** to wake up, check work, and act — without a human initiating every session.
- Work items have no **strategic ancestry** — a task cannot trace back through a project, program, portfolio, and company goal to the root mission.
- **Humans and AI agents** cannot be co-workers on the same task with clear handoff protocols.
- There is no **budget governance** that stops an agent automatically when it exceeds its monthly allocation.
- **Knowledge is not scoped** to a company or project — any agent can read any knowledge, and no knowledge is automatically injected into an agent's working context.
- Companies cannot be **templated and replicated** — each setup is bespoke.

### 2.2 User Pain Points

| Pain Point | Impact |
|------------|--------|
| AI agents lose context between sessions | Agent restarts from scratch every time; no organizational memory |
| No way to run agents autonomously 24/7 | Requires human to manually initiate every agent run |
| Can't track what AI agents are doing across parallel sessions | Work is invisible, uncoordinated, duplicated |
| No budget control — runaway LLM costs possible | Financial risk, no automatic stops |
| Humans and AI work in separate tools | No unified view of who is doing what, AI or human |
| No strategic alignment | Agents do tasks with no connection to company goals |
| Knowledge not shared across agents | Each agent starts with no organizational context |
| Can't replicate a working AI team setup | Every new project requires manual re-configuration |

---

## 3. Goals

### 3.1 Primary Goals

1. **Company as first-order entity** — every agent, project, goal, work item, budget, and knowledge collection belongs to a company. One AutoBot deployment runs many companies with full data isolation.
2. **Autonomous agent execution** — agents wake on schedule, check assigned work, execute, and report back without human initiation.
3. **Full work item hierarchy** — from company-level epic down to individual subtask, with strategic traceability at every level.
4. **Hybrid human + AI workforce** — humans and agents are interchangeable assignees on any work item, with structured handoff protocols.
5. **Knowledge-powered execution** — every agent receives RAG-assembled context from the company, project, and agent-level knowledge base at execution time.
6. **Budget governance** — per-agent and per-company monthly budgets enforced with hard stops and board notifications.
7. **Board control surface** — the human board can intervene, approve, redirect, or pause any entity at any time.

### 3.2 Non-Goals (V1)

- AutoBot LLC is not a replacement for external version control (Git/GitHub).
- It does not provide billing / revenue accounting — only AI cost tracking.
- It does not include a public company template marketplace in V1 (private export/import only).
- It does not replace AutoBot's existing chat interface — chat is extended, not replaced.
- Multi-board governance (multiple human approvers with voting) is post-V1.

---

## 4. User Personas

### 4.1 The Operator (Primary)
A technical founder, CTO, or engineering lead running one or more AI-native companies or internal AI teams. They configure companies, hire agents, set strategy, and monitor progress from the board dashboard. They approve key decisions, set budgets, and intervene when something goes off-track.

**Needs:** Single pane of glass for all autonomous work. Confidence that costs are bounded. Ability to intervene immediately. Clear visibility into what agents accomplished.

### 4.2 The Human Worker (Secondary)
A team member — developer, designer, analyst, PM — who works alongside AI agents on shared work items. They pick up tasks from the backlog, receive handoff packages from agents, review AI-produced artifacts, and hand work back to agents for continuation.

**Needs:** Clear handoff context from agents. Ability to see what the AI did and what remains. Simple interface to claim, work, and return tasks.

### 4.3 The AI Agent (System Actor)
An AutoBot agent (or adapter-compatible external agent) that operates autonomously via heartbeat scheduling. It reads assigned work items, executes using the full AutoBot AI stack, writes results back, reports cost, and updates task status.

**Needs:** Rich context at invocation time (goal ancestry, project KB, agent memory, acceptance criteria). Clear task ownership semantics. API to report cost and status.

### 4.4 The Board (Governance Actor)
The human governance layer. In V1, this is the operator. They approve hires, strategy proposals, budget overrides, and sprint gates. They can pause any agent or work item at any time.

**Needs:** Pending approval queue always visible. One-click approve/reject/request-changes. Full audit trail of every decision.

---

## 5. Product Hierarchy

### 5.1 Organizational Hierarchy

```
Platform
└── Company (LLC)
    ├── SubCompany (subsidiary, unlimited nesting depth)
    │   └── SubCompany...
    └── Org Chart
        ├── Human Workers (board-appointed, assignable)
        └── AI Agents (adapter-typed, heartbeat-scheduled)
            └── Reports-to tree (strict parent, cycle-detected)
```

**Company** is the root entity. All budgets, knowledge collections, secrets, goals, and work items are scoped to a company. SubCompanies inherit parent company KB with read-only access and weight decay; they do not write upward.

### 5.2 Goal Hierarchy

```
Company Goal (root mission — e.g. "Ship AutoBot LLC to production")
└── Team Goal (e.g. "Backend API complete and tested")
    └── Agent Goal (e.g. "Implement work item service")
        └── Task Goal (e.g. "Write atomic checkout logic")
```

Every work item at any level of the backlog hierarchy must be linkable to a goal. The system displays goal ancestry ("why does this task exist?") in every work item detail view and injects it into every agent heartbeat context package.

### 5.3 Work Item Hierarchy

```
Epic  (company/program scope — large outcome)
└── Feature  (project scope — deliverable capability)
    └── Product Backlog Item / Story  (sprint-plannable unit)
        └── Task  (single-session executable unit)
            └── Subtask / Bug  (atomic action)
```

**Types:** Epic, Feature, PBI (Story), Task, Bug, Subtask, Spike, Risk Item.

**Statuses:** `backlog → ready → in_progress → in_review → done | blocked | cancelled`

**Single-assignee invariant:** Every work item has exactly one assignee at any time — either a human user or an AI agent. Atomic checkout prevents double-assignment.

### 5.4 Project Hierarchy

```
Portfolio  (investment category — e.g. "Platform", "Growth")
└── Program  (multi-project initiative)
    └── Project  (delivery vehicle)
        └── Sprint / Iteration  (2-week time-box)
            └── Work Items committed to sprint
```

---

## 6. Feature Requirements

### 6.1 Company Management

**FR-COMP-01:** Create, update, archive, and restore companies.  
**FR-COMP-02:** Create sub-companies nested under any company to any depth. Sub-company inherits parent budget ceiling; cannot exceed it.  
**FR-COMP-03:** Each company has: name, mission statement, issue prefix (e.g. `ABO-`), auto-incrementing issue counter, monthly budget (cents), brand color, status (`active | paused | archived`).  
**FR-COMP-04:** Company data is fully isolated — no cross-company data access at any layer.  
**FR-COMP-05:** Export company as a template (structure only: agents, goals, projects, seed tasks, secret references) or snapshot (full state including sprint progress and KB summary). Secrets are scrubbed from exports; references are preserved as placeholders.  
**FR-COMP-06:** Import a company template into a new company with collision detection on agent names and issue prefixes.

### 6.2 Agent Management

**FR-AGENT-01:** Create agents with: name, title, role, org position (`reports_to`), adapter type, adapter config (jsonb), context mode (`thin | fat`), monthly budget, permissions.  
**FR-AGENT-02:** Supported built-in adapter types: `process` (shell command), `http` (webhook), `autobot_agent` (native AutoBot agent from `agents/`), `claude_code` (Claude Code session). External adapters loadable via plugin.  
**FR-AGENT-03:** Agent status lifecycle: `active → paused | running | error | pending_approval | terminated`. Terminated agents cannot be resumed.  
**FR-AGENT-04:** Org chart enforces a strict tree (`reports_to` nullable for root). Cycle detection on every upsert.  
**FR-AGENT-05:** Board must approve new agent hires when `require_board_approval_for_new_agents` is set on the company.  
**FR-AGENT-06:** Agent API keys: created on hire, hashed at rest, plaintext shown once. Keys are company-scoped — cannot access other companies.  
**FR-AGENT-07:** Board can pause, resume, or terminate any agent instantly. Pause sends graceful stop signal; force-kills after configurable grace period.  
**FR-AGENT-08:** Agent capabilities description stored and indexed in company KB — used by other agents for peer discovery.

### 6.3 Goal Hierarchy

**FR-GOAL-01:** Create goals at four levels: `company | team | agent | task`. Each goal has: title, description, level, parent goal, owner (agent or user), status (`planned | active | achieved | cancelled`).  
**FR-GOAL-02:** Every company must have at least one root `company`-level goal.  
**FR-GOAL-03:** Goal ancestry API: given any work item, return the full chain of goals from the item's `goal_id` to the root company goal.  
**FR-GOAL-04:** Goal ancestry is displayed in every work item detail view and injected into every agent heartbeat context package.  
**FR-GOAL-05:** Goals are indexed in the company KB — agents can RAG-query "why does this task exist?" and receive a grounded answer.

### 6.4 Work Item Management

**FR-WORK-01:** Work item types: Epic, Feature, PBI, Task, Bug, Subtask, Spike, Risk.  
**FR-WORK-02:** Work item fields: id, company_id, project_id, sprint_id, goal_id, parent_id, type, title, description, acceptance_criteria, status, priority (`critical | high | medium | low`), story_points, assignee (agent_id OR user_id), created_by, identifier (e.g. `ABO-42`), started_at, completed_at, labels.  
**FR-WORK-03:** Atomic checkout: transition to `in_progress` requires a compare-and-swap on `checkout_run_id`. Concurrent checkout attempts return 409. Redis-backed lock with TTL.  
**FR-WORK-04:** Work items support: threaded comments (human or agent), file attachments, linked work products (artifacts: code, docs, PRs, screenshots, reports), blocking/blocked-by relations.  
**FR-WORK-05:** AI-assisted acceptance criteria drafting: when creating a PBI, the system RAG-queries the company KB (policies, past similar items) and proposes a draft AC list. User accepts, edits, or rejects.  
**FR-WORK-06:** Every mutating action on a work item is written to the immutable activity log with actor, timestamp, before/after state.  
**FR-WORK-07:** Work items completed by agents automatically ingest their artifacts (produced files, reports, plans) into the project KB collection.

### 6.5 Sprint / Iteration Planning

**FR-SPRINT-01:** Sprints belong to a project. Fields: name, goal description, start_date, end_date, status (`planning | active | review | closed`), committed velocity (story points), actual velocity.  
**FR-SPRINT-02:** Backlog grooming view: sortable, filterable list of all `backlog` and `ready` work items. Drag-drop priority ordering. Bulk-assign to sprint.  
**FR-SPRINT-03:** Sprint board: configurable columns per sprint. Work items move across columns. Board is real-time (WebSocket-pushed).  
**FR-SPRINT-04:** Kanban board: continuous flow view per project, no sprint boundary. Same real-time push.  
**FR-SPRINT-05:** Capacity planning: per-sprint capacity (human hours + agent budget). System warns when committed story points exceed declared capacity.  
**FR-SPRINT-06:** Burndown chart: per-sprint, per-project. Ideal line vs actual remaining points.  
**FR-SPRINT-07:** Sprint close: board must review and approve close. On close, sprint KB is summarized by LLM and merged into project KB. Incomplete items roll over to backlog (configurable: auto-rollover or manual triage).  
**FR-SPRINT-08:** Velocity history: past sprint actuals are stored and used to predict future sprint capacity via RAG + LLM synthesis.

### 6.6 Heartbeat / Autonomous Execution

**FR-HB-01:** Each agent has a heartbeat schedule (cron expression or interval). The scheduler fires adapters on schedule.  
**FR-HB-02:** Heartbeat invocation: adapter is called with a context package (thin: task_id + API base; fat: full RAG-assembled context — see §6.10).  
**FR-HB-03:** Heartbeat run record: id, agent_id, company_id, status (`queued | running | succeeded | failed | cancelled | timed_out`), started_at, finished_at, error, external_run_id, context_snapshot.  
**FR-HB-04:** Liveness monitor: detects runs stuck beyond configurable timeout. Creates recovery action work items. Board is notified.  
**FR-HB-05:** Manual heartbeat trigger: board can fire any agent's heartbeat immediately from the UI.  
**FR-HB-06:** Heartbeat can be scoped to a specific work item (agent wakes to work on exactly one task) or open-ended (agent decides what to work on from its queue).  
**FR-HB-07:** Agents report cost events and status back via REST API during and after execution. Cost is recorded per heartbeat run, per work item, per project.

### 6.7 Routines (Recurring Work)

**FR-ROUTINE-01:** A routine is a scheduled recurring work unit with its own: name, description, cron schedule, assignee (agent), env overlay (can reference company secrets), producing a new work item per firing or updating a recurring work item.  
**FR-ROUTINE-02:** Routine examples: daily standup summary, weekly cost report, nightly code health scan, hourly customer support triage.  
**FR-ROUTINE-03:** Routine env overlay is applied after project env and before system-injected keys. Routine-owned secrets do not require direct bindings on the executing agent.  
**FR-ROUTINE-04:** Routine run history is recorded with the same heartbeat run schema. Board can pause/resume any routine.

### 6.8 Board Governance & Approvals

**FR-GOV-01:** Approval types: `hire_agent | approve_strategy | budget_override | request_board_approval | sprint_close_gate`.  
**FR-GOV-02:** Approval lifecycle: `pending → revision_requested → approved | rejected | cancelled`.  
**FR-GOV-03:** Board approval inbox is always visible in the sidebar with a pending count badge.  
**FR-GOV-04:** Board can approve, reject, or request changes with a decision note. All decisions are written to KB decision log and activity log.  
**FR-GOV-05:** Board can pause or resume any agent, work item, sprint, or entire company instantly without going through the approval flow.  
**FR-GOV-06:** Budget override: when an agent or company exceeds budget, the hard stop fires and creates a `budget_override` approval request. Work resumes only after board approves an increase.  
**FR-GOV-07:** Sprint close gate: before a sprint can be marked closed, board must review the sprint summary (auto-generated from sprint KB) and approve.

### 6.9 Budget & Cost Tracking

**FR-BUDGET-01:** Monthly budgets (UTC calendar window) at two levels: company-level and per-agent. Agent budget cannot exceed company budget.  
**FR-BUDGET-02:** Sub-company budgets cascade: parent company budget is the ceiling for all children. Board can delegate a portion to a sub-company.  
**FR-BUDGET-03:** Cost events: each agent execution records input_tokens, output_tokens, cost_cents, provider, model, occurred_at. Each event is linked to: agent, company, work_item (optional), project (optional), goal (optional).  
**FR-BUDGET-04:** Hard stop: when `spent_monthly_cents >= budget_monthly_cents`, agent is auto-paused. An approval request is created for board review.  
**FR-BUDGET-05:** Soft alert: configurable threshold (default 80%) — board is notified but agent continues.  
**FR-BUDGET-06:** Cost dashboard: breakdown by company, sub-company, project, agent, work item, model, and date range. Exportable as CSV.  
**FR-BUDGET-07:** Cost rollups are aggregations of cost events — never manually edited. They are recomputed from events on demand.

### 6.10 Knowledge Base Integration

**FR-KB-01:** Every company gets a scoped KB collection set at creation: `company:{id}`, `company:{id}:agents`, and `company:{id}:decisions`.  
**FR-KB-02:** Every project gets a scoped KB collection at creation: `project:{id}`. Contains: spec, architecture decisions, retrospectives, work product artifacts.  
**FR-KB-03:** Every sprint gets an ephemeral KB collection: `sprint:{id}`. On sprint close, the sprint KB is LLM-summarized and merged into the project KB. The sprint collection is then archived.  
**FR-KB-04:** Every agent gets a persistent KB collection: `agent:{id}`. Contains: agent diary entries, task pattern learner output, past decisions. Survives across heartbeat sessions.  
**FR-KB-05:** Work item KB: ephemeral per-task collection indexed during execution (tool traces, comments, draft artifacts). On task completion, artifacts are merged into the project KB.  
**FR-KB-06:** Sub-company KB inheritance: a sub-company's agents can RAG-query the parent company KB with read-only access and configurable weight decay (parent context is de-prioritized vs own company context).  
**FR-KB-07:** Heartbeat fat-context assembly: before invoking a fat-context agent, the system issues parallel RAG queries across company KB, project KB, and agent KB to assemble a context package. Included in the package: goal ancestry, relevant company policies, similar completed past items, agent memory, acceptance criteria.  
**FR-KB-08:** AC suggestion: when creating a PBI/Story, the system RAG-queries company KB (standards, policies) and project KB (similar completed stories) and proposes a draft acceptance criteria list. Editable by user before saving.  
**FR-KB-09:** Human↔AI handoff brief: when a work item is handed from an agent to a human (or vice versa), the system generates a handoff brief from KB: what was done, what remains, relevant past decisions, open blockers. Presented in the work item transition UI.  
**FR-KB-10:** Board decision log: every board approval/rejection is written to the `company:{id}:decisions` KB collection with full rationale. Future decisions on the same topics are informed by RAG over past decisions.  
**FR-KB-11:** Cross-company template KB: exported company templates are indexed at the platform level, enabling future search-and-import of templates without exposing company-private data.  
**FR-KB-12:** Agent capability indexing: on hire or capability update, the agent's capabilities description is re-indexed into `company:{id}:agents`. Agents can discovery peers by querying this collection ("who in this company handles security audits?").

### 6.11 Hybrid Human + AI Orchestration

**FR-HYBRID-01:** Any work item can be assigned to a human user OR an AI agent. The assignment model is a union — one assignee at a time, typed as `human | agent`.  
**FR-HYBRID-02:** Work item transition `in_review` can route to a specific human reviewer or a specific agent reviewer. Reviewer is set as a separate field from assignee.  
**FR-HYBRID-03:** Human claim: a human can claim any `backlog` or `ready` work item from the board without board approval (subject to sprint membership).  
**FR-HYBRID-04:** AI claim: an agent claims a work item via the heartbeat API using atomic checkout. If the item is already claimed by a human, the agent's checkout returns 409 and the agent moves on.  
**FR-HYBRID-05:** Handoff protocol — agent → human: agent transitions item to `in_review`, system generates KB-powered handoff brief, human reviewer is notified. Human can approve (mark done), request changes (item returns to `in_progress` on agent), or claim the item themselves.  
**FR-HYBRID-06:** Handoff protocol — human → agent: human transitions item to `ready`, optionally adds notes and attached files (auto-ingested into work item KB), item becomes available for agent heartbeat pickup.  
**FR-HYBRID-07:** Co-working mode (optional): both a human and an agent are on the same item simultaneously. Human retains final approval authority. Agent works on subtasks; human works on other subtasks. No concurrent checkout conflict at the parent level.  
**FR-HYBRID-08:** CEO Chat: a lightweight conversation surface scoped to a company. Chat messages are routed via LLM over company KB and always resolve to a concrete work object: a new task, a strategy approval request, a goal update, or a board decision. No free-floating chat without a work object.

### 6.12 Secrets Management

**FR-SECRET-01:** Company-scoped secrets with versioning. Fields: name, value (encrypted), version, provider (`local | aws_secretsmanager`), created_by, revoked_at.  
**FR-SECRET-02:** Secret bindings: agents and routines reference secrets by name; resolution happens at invocation time. Plaintext never stored in agent or routine config.  
**FR-SECRET-03:** Secret access events: every secret read is logged with actor, timestamp, and context (which heartbeat run triggered the read).  
**FR-SECRET-04:** Board can revoke any secret instantly. Active runs that hold a reference to a revoked secret are cancelled on next secret resolution attempt.

### 6.13 Activity Log (Immutable Audit Trail)

**FR-AUDIT-01:** Every mutating action across all LLC entities writes a record to the activity log: actor (agent or user), company_id, entity_type, entity_id, action, before_state (jsonb), after_state (jsonb), timestamp.  
**FR-AUDIT-02:** Activity log is append-only. No record can be updated or deleted.  
**FR-AUDIT-03:** Activity log is queryable per company, per entity, per actor, per date range.  
**FR-AUDIT-04:** Board can subscribe to activity log events via the existing AutoBot WebSocket event bus — live updates without polling.

### 6.14 Real-Time Events

**FR-RT-01:** All state changes (work item status, heartbeat run start/finish, approval created/resolved, budget alert) are published to the AutoBot live event bus (Redis pub/sub → WebSocket) and scoped to `company_id`.  
**FR-RT-02:** Sprint board and kanban board columns update in real-time without page refresh.  
**FR-RT-03:** Board approval inbox badge updates in real-time.  
**FR-RT-04:** Heartbeat run progress is streamed to the board UI — operators can watch an agent's execution live.

---

## 7. Non-Functional Requirements

### 7.1 Performance
- Work item list pages: ≤200ms P99 at 10,000 items per company.
- Heartbeat context assembly (fat-payload RAG): ≤2s P95 (parallel RAG queries).
- Atomic checkout: ≤50ms P99 (Redis compare-and-swap).
- Real-time event delivery: ≤100ms from backend state change to WebSocket push.
- Sprint burndown chart: ≤500ms at 500 items per sprint.

### 7.2 Reliability
- Heartbeat scheduler: survives process restart. State stored in Redis. On restart, all pending heartbeats are replayed.
- Budget enforcement: hard stop fires within one cost event of the limit. No grace window beyond the current event.
- Activity log: writes use PostgreSQL transactions. No mutation completes without a corresponding audit record.
- Atomic checkout: Redis TTL on checkout lock is 30 minutes. Watchdog clears expired locks and opens recovery actions.

### 7.3 Security
- All LLC routes enforce `company_id` scoping in service layer — no cross-company data access regardless of auth token scope.
- Agent API keys are hashed (bcrypt) at rest. Plaintext shown once on creation.
- Secret values are encrypted at rest (AES-256). Decryption only at invocation time.
- All mutating LLC endpoints require actor authentication (board session or agent API key). Read-only endpoints require at minimum a company member token.
- Sub-company agents cannot write to parent company KB — read-only cross-boundary access only.

### 7.4 Scalability
- All LLC tables include `company_id` as a leading index column.
- Company isolation enables horizontal partitioning by `company_id` in future.
- Heartbeat scheduler uses Redis sorted sets for next-fire-time. Scales to 10,000 agents without in-process polling overhead.
- KB collection naming scheme supports unlimited companies and projects without namespace collision.

### 7.5 Maintainability
- All LLC code lives in `autobot-backend/llc/` — isolated from existing modules, imported via shared protocols.
- Adapters implement a three-method protocol (`invoke / status / cancel`) — adding a new adapter requires no changes to core scheduler.
- KB integration is mediated through a single `kb/context_builder.py` module — changing RAG strategy requires no changes to heartbeat or assignment services.

---

## 8. Data Model Summary

### 8.1 New Tables (18 core + 7 supporting)

| Table | Purpose |
|-------|---------|
| `llc_companies` | Extends org with company-scoped fields, parent_id for sub-companies |
| `llc_company_memberships` | Human users as company members with roles |
| `llc_goals` | 4-level goal hierarchy, parent_id chain |
| `llc_portfolios` | Portfolio container per company |
| `llc_programs` | Program under portfolio |
| `llc_projects` | Project under program (replaces project_state_tracking) |
| `llc_sprints` | Sprint under project |
| `llc_work_items` | Epic/Feature/PBI/Task/Bug/Subtask unified table |
| `llc_work_item_comments` | Threaded comments, human or agent authored |
| `llc_work_item_labels` | Tags per work item |
| `llc_work_products` | Artifacts produced by work item execution |
| `llc_boards` | Board definition (kanban or sprint) |
| `llc_board_columns` | Column config per board |
| `llc_assignments` | Union type: agent_id OR user_id per work item |
| `llc_heartbeat_runs` | Per-agent invocation records |
| `llc_cost_events` | Normalized cost per run/item/agent/project |
| `llc_approvals` | Board governance requests and decisions |
| `llc_routines` | Recurring scheduled work definitions |
| `llc_activity_log` | Immutable audit trail, company-scoped |
| `llc_company_secrets` | Versioned encrypted secrets |
| `llc_secret_bindings` | Agent/routine → secret name references |
| `llc_secret_access_events` | Every secret read logged |
| `llc_agent_configs` | Adapter type + config per agent (extends agent_org_nodes) |
| `llc_budget_incidents` | Budget threshold crossing records |
| `llc_kb_collections` | Registry of KB collection names, lifecycle, status |

### 8.2 Extended Existing Tables

| Existing Table | Extension |
|----------------|-----------|
| `organizations` | Add: `parent_org_id`, `issue_prefix`, `issue_counter`, `budget_monthly_cents`, `spent_monthly_cents`, `brand_color`, `require_approval_for_hires`, `pause_reason`, `paused_at` |
| `agent_org_nodes` | Add: `adapter_type`, `adapter_config`, `context_mode`, `budget_monthly_cents`, `spent_monthly_cents`, `default_environment_id`, `permissions`, `last_heartbeat_at`, `status`, `metadata` |

---

## 9. Frontend Requirements

### 9.1 New Views

| View | Description |
|------|-------------|
| Company Dashboard | Active agents, pending approvals, budget gauges, recent activity feed, live heartbeat status |
| Org Chart | Interactive tree visualization of all agents and human workers. Status indicators on each node. Click to view/edit. |
| Goal Tree | Hierarchical goal browser. Goal → linked projects → linked work items. |
| Backlog View | Prioritized, filterable work item list. Drag-drop ordering. Bulk sprint assign. AC suggestion trigger. |
| Sprint Board | Time-boxed kanban. Real-time column moves. Burndown chart sidebar. Sprint health indicators. |
| Kanban Board | Continuous flow view. WIP limits per column. Swimlanes by assignee type (human vs agent). |
| Work Item Detail | Full detail with: comments, attachments, work products, acceptance criteria, goal ancestry breadcrumb, assignee history, activity log, handoff brief. |
| Approvals Inbox | Pending governance requests. One-click approve/reject/request-changes. Decision note required. |
| Cost Dashboard | Breakdown charts by company, sub-company, agent, project, model. Date range picker. CSV export. |
| Company Portability | Export (template / snapshot). Import with collision preview. |
| Heartbeat Monitor | Live grid of all agents. Current run status. Manual trigger button. Last run summary. |
| CEO Chat | Company-scoped conversational surface. Every message resolves to a work object. History threaded per resolved object. |
| Sub-Company Tree | Visual tree of company → sub-company hierarchy with budget cascade view. |

### 9.2 Extended Existing Views

- **AgentRegistryView.vue** — extend with adapter config editor, heartbeat schedule, budget indicator.
- **WorkflowBuilderView.vue** — add LLC routine builder as a mode.
- **AuditLogsView.vue** — scope to `company_id`, add LLC entity type filters.
- **ChatView.vue** — add company context mode (CEO Chat) as a view variant.
- **PluginsView.vue** — add adapter plugin registry tab.

### 9.3 Real-Time Requirements

All board views and the approval inbox must update in real-time via the existing AutoBot WebSocket event bus. No polling. Company-scoped event channels ensure agents in company A cannot see events from company B.

---

## 10. API Surface

### 10.1 New Route Groups (all under `/api/llc/`)

```
/companies                    CRUD + sub-company tree
/companies/{id}/goals         Goal hierarchy CRUD
/companies/{id}/goals/{id}/ancestry   Goal ancestry chain
/companies/{id}/portfolios    Portfolio/program/project hierarchy
/companies/{id}/approvals     Board approval queue + decisions
/companies/{id}/costs         Cost dashboard data
/companies/{id}/activity      Activity log queries
/companies/{id}/export        Template / snapshot export
/companies/{id}/secrets       Company secret management

/projects/{id}/sprints        Sprint CRUD + close
/projects/{id}/backlog        Prioritized work item list
/projects/{id}/board          Board column config + items

/work-items                   CRUD (company-scoped)
/work-items/{id}/checkout     Atomic checkout
/work-items/{id}/comments     Threaded comments
/work-items/{id}/products     Work product artifacts
/work-items/{id}/handoff      Handoff brief generation

/agents/{id}/heartbeat        Manual trigger, run status, cancel
/agents/{id}/runs             Heartbeat run history
/agents/{id}/budget           Budget status + spend history

/routines                     Routine CRUD + run history

/import                       Template import with collision preview
```

### 10.2 Agent-Facing API (authenticated via agent API key)

```
GET  /api/llc/agent/work-items/next     Next assigned item (atomic checkout)
POST /api/llc/agent/work-items/{id}/status   Status update
POST /api/llc/agent/cost-events              Cost event ingestion
POST /api/llc/agent/comments                 Comment on work item
POST /api/llc/agent/products                 Upload work product artifact
POST /api/llc/agent/heartbeat/report         Heartbeat run completion report
GET  /api/llc/agent/context/{item_id}        Pre-assembled KB context package
```

---

## 11. Integration with Existing AutoBot Modules

| AutoBot Module | LLC Integration |
|----------------|----------------|
| `autobot_shared/redis_client` | Atomic checkout lock, heartbeat scheduler sorted set, cost event queue |
| `agents/base_agent.py` | `autobot_agent` adapter wraps base_agent for heartbeat dispatch |
| `chat_workflow/` | CEO Chat mode uses chat_workflow with company KB as RAG source |
| `llm_shared/` | All agent LLM calls route through existing LLM gateway with cost header; cost_cents extracted from `x-llm-cost` response header |
| `knowledge_base.py` + ChromaDB | KB collections created/queried via existing KB interface; no new DB client |
| `autobot_memory_graph/` | Agent memory persisted to `agent:{id}` KB collection after each heartbeat |
| `memory/agent_diary.py` | Diary entries written to agent KB after heartbeat completion |
| `services/agent_org_service.py` | LLC agent management extends existing org service |
| `api/agent_org.py` | LLC adds adapter config + heartbeat endpoints to existing org API |
| `user_management/models/organization.py` | `llc_companies` extends Organization with LLC fields |
| `integrations/project_management_integration.py` | Retained as outbound sync: completed LLC work items can be synced to external tools via existing Jira/Trello/Asana connectors |
| `plugin_manager.py` | External adapter plugins loaded via existing plugin manager |
| `api/workflow_secrets.py` | LLC secret management uses same encryption service |
| `user_management/models/audit.py` | LLC activity log extends existing audit infrastructure |

---

## 12. Implementation Phases

### Phase 1 — Core Control Plane (Foundation)
*Target: 8 GitHub issues*

1. Company model extension — sub-companies, budget, issue_prefix, status lifecycle  
2. 4-level goal hierarchy — CRUD + ancestry traversal + KB indexing  
3. Work item hierarchy — Epic/Feature/PBI/Task/Bug/Subtask, unified table, atomic checkout  
4. Board approval gates — hire, strategy, budget, sprint-close types  
5. Per-agent budget enforcement — hard stop, soft alert, cost event ingestion  
6. Immutable activity log — company-scoped, all-mutations coverage  
7. Company-scoped secrets — versioned, encrypted, binding model, access log  
8. LLC API routes — `/api/llc/` route group registration, agent-facing API keys

### Phase 2 — Agile Workflow Layer
*Target: 6 GitHub issues*

9. Portfolio → Program → Project → Sprint hierarchy — CRUD + sprint lifecycle  
10. Sprint planning — capacity, velocity history, burndown data  
11. Kanban board + Sprint board — column config, real-time WebSocket push  
12. Backlog view — priority ordering, bulk sprint assign, type/status filters  
13. Human workers as first-class assignees — user claims, handoff protocol  
14. Sprint auto-close — board gate, KB summarization, rollover logic  

### Phase 3 — Heartbeat + Adapters
*Target: 5 GitHub issues*

15. Heartbeat scheduler — Redis sorted set, cron dispatch, restart-safe  
16. Adapter protocol — `invoke/status/cancel` base class + process + http adapters  
17. AutoBot agent adapter — wraps `agents/base_agent.py` for heartbeat dispatch  
18. Liveness monitor + watchdog — stuck run detection, recovery action creation  
19. Routine entity — recurring work CRUD, env overlay, run history  

### Phase 4 — Hybrid Human + AI Orchestration
*Target: 5 GitHub issues*

20. Union assignment model — human | agent, co-working mode  
21. Agent → human handoff — KB-powered brief generation, reviewer notification  
22. Human → agent handoff — notes ingestion into work item KB, agent pickup  
23. CEO Chat — company-scoped chat, LLM + KB routing to work objects  
24. Human review gate — mid-work-item approval step, configurable per item type  

### Phase 5 — Knowledge Base Integration
*Target: 10 GitHub issues*

25. KB collection lifecycle manager — create/archive per company/project/sprint/agent  
26. Heartbeat context builder — parallel RAG assembly, fat payload construction  
27. Agent diary → KB writer — post-heartbeat hook on `agent_diary.py`  
28. Sprint KB summarizer — LLM-summarize + merge into project KB on close  
29. Handoff brief generator — AI→Human and Human→AI brief from KB  
30. AC suggester — RAG over company policies + past PBIs on work item create  
31. Sub-company KB inheritance — read-through with weight decay  
32. Artifact ingestor — work products indexed into project KB on completion  
33. Board decision log writer — approvals written to `company:{id}:decisions` KB  
34. Agent capability indexing — on hire/update, re-index to `company:{id}:agents`  

### Phase 6 — Portability + Frontend Polish
*Target: 6 GitHub issues*

35. Company template export — structure + seed tasks, secret scrubbing  
36. Company snapshot export — full state including sprint progress  
37. Company import — collision detection, preview, namespace remapping  
38. Frontend: Company Dashboard + Org Chart + Goal Tree views  
39. Frontend: Backlog + Sprint Board + Kanban Board + Work Item Detail views  
40. Frontend: Approvals Inbox + Cost Dashboard + Heartbeat Monitor + CEO Chat views  

---

## 13. Success Metrics

| Metric | Target (90 days post-launch) |
|--------|------------------------------|
| Agents running autonomously on heartbeat schedule | ≥ 5 per active company |
| Work items completed by AI agents without human intervention | ≥ 60% of total closed |
| Budget hard stops firing correctly (no overruns) | 100% |
| Heartbeat context assembly P95 latency | ≤ 2s |
| Board approval queue actioned within 24h | ≥ 90% |
| Company KB queries returning relevant results (user-rated) | ≥ 80% relevant |
| Human↔AI handoffs with generated brief viewed by human | ≥ 75% of handoffs |
| Sprint velocity prediction accuracy (within 20%) | ≥ 70% of sprints |

---

## 14. Open Questions

1. **Sub-company budget inheritance model:** Should a sub-company's budget be a hard subset of parent (cannot exceed parent remaining), or a soft guideline with board override?
2. **Goal ancestry requirement strictness:** Should creating a work item with no resolvable goal ancestry be a warning or a hard block?
3. **Co-working mode default:** Should co-working mode (human + agent simultaneously) be opt-in per company or opt-in per work item?
4. **Sprint close gate:** Should the board approval be required for every sprint close, or only when uncompleted committed items are present?
5. **KB weight decay for sub-company inheritance:** What is the default decay factor for parent KB results vs own KB results? Configurable per company or fixed?
6. **Agent diary granularity:** Should the diary entry be one entry per heartbeat run or one entry per tool call within a run?
7. **CEO Chat history retention:** Are CEO Chat threads retained indefinitely or archived after the resolved work object reaches a terminal state?
8. **Template marketplace:** Should V1 template export/import be private only, or should a "share publicly" flag be available immediately?

---

*End of PRD — AutoBot LLC Module v1.0*
