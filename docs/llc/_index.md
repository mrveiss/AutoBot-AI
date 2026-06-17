---
tags:
  - index
  - llc
  - module
aliases:
  - AutoBot LLC
  - LLC Module
  - LLC Index
  - Autonomous Agent Company
status: current
---

# AutoBot LLC

**AutoBot LLC is a module you install on AutoBot** — an autonomous *agent-company*.
Define a company of AI agents (and human co-workers), give them goals and a backlog,
schedule them to work autonomously, and govern their spend — all on infrastructure
you own.

LLC is the flagship example of AutoBot's [module model](../architecture/PLATFORM_MODEL.md):
it is built on the platform's bones rather than reimplementing them. See **[The AutoBot
Platform Model](../architecture/PLATFORM_MODEL.md)** for how core, the Service Lifecycle
Manager (SLM), and modules fit together.

> **LLC** here means the AutoBot **module**, not a legal "limited liability company."

---

## What LLC inherits from the platform

LLC is small relative to what it delivers because the hard parts already live in the
core. Its agents inherit:

| LLC capability | Inherited platform primitive |
|----------------|------------------------------|
| Agents that remember across runs and share organizational context | **Institutional memory** — the RAG knowledge base + knowledge graph |
| Affordable 24/7 autonomous execution | **Local inference at zero marginal cost** — models run on hardware you own |
| Wiring agents into scheduled, event-driven work | **Hooks** — the platform's extension points |
| Budget caps, approval gates, and access control | **Governance** — RBAC, review gates, and budgets enforced by the core |

Because of this, LLC contributes the *company-shaped* layer — companies, org charts,
goals, backlogs, sprints, heartbeat scheduling, board governance, and cost tracking —
and leans on the platform for memory, inference, and governance.

---

## What LLC adds

- **Company as a first-order entity** — agents, goals, budgets, knowledge, and work
  all belong to a company; one deployment runs many isolated companies.
- **Autonomous execution** — agents wake on a heartbeat schedule, pick up assigned
  work, execute, and report back without a human starting each session.
- **Work hierarchy** — Epic → Feature → Story → Task → Subtask, with goal ancestry.
- **Hybrid human + AI workforce** — humans and agents are interchangeable assignees
  with structured handoff briefs (generated from the knowledge base).
- **Board governance** — approval gates for hires, strategy, budget, and sprint close.
- **Budget governance** — per-agent and per-company budgets with hard stops.

---

## Documentation

| Document | Description |
|----------|-------------|
| [LLC Module PRD](../planning/PRD_AutoBot_LLC_Module.md) | Full product requirements: hierarchy, features, data model, API, phases |
| [Budget token mode](budget-token-mode.md) | Token-based budget accounting for LLC agents |
| [GitHub PR integration](github-pr-integration.md) | PR ↔ work-item linking, branch naming convention, webhook setup |
| [Project timeline (Gantt)](project-timeline.md) | Timeline view, scheduled dates, dependency arrows, critical path |

## Related

- [The AutoBot Platform Model](../architecture/PLATFORM_MODEL.md) — core → SLM → modules
- [Capability Catalog](../features/CATALOG.md) — all platform capabilities
- [Glossary](../GLOSSARY.md) — terminology, including LLC, SLM, and Module
