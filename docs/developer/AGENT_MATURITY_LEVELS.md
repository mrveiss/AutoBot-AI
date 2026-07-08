# Agent Maturity Levels

An operator-facing map of how AutoBot grows from a single agent to an automated
team. The four levels are borrowed from the "Agent Control Room" progression and
mapped to the concrete AutoBot constructs that already implement each one.

> **Guiding rule:** *automate only after the manual workflow works.* Move up a
> level when the level below is stable — not before.

Every construct below is wired in AutoBot today; the levels describe how much of
the stack you choose to switch on, not a build roadmap.

---

## Level 1 — One Agent

A single agent executes a task end to end: analyze events → select a tool →
execute → iterate → report → standby.

| Construct | Where |
|---|---|
| Agent execution loop (Manus-style 6-step) | [`autobot-backend/agent_loop/loop.py`](../../autobot-backend/agent_loop/loop.py) |
| Loop configuration | [`autobot-backend/agent_loop/types.py`](../../autobot-backend/agent_loop/types.py) (`AgentLoopConfig`) |

Best for a single personal/work assistant. No orchestrator or task delegation is
involved.

---

## Level 2 — Direct Specialists

Multiple role-specific agents, each with its own capabilities and tools. You (or
a router) pick the right specialist per task.

| Construct | Where |
|---|---|
| Specialist agents (research, classification, kb-librarian, system-command, RAG, security-scanner, …) | [`autobot-backend/agents/`](../../autobot-backend/agents/) |
| Per-agent capability + `allowed_work`/`forbidden_work` manifest | [`autobot-backend/orchestration/agent_registry.py`](../../autobot-backend/orchestration/agent_registry.py) (`AgentProfile`) |

Each agent's least-privilege boundary is declared once on its profile and
enforced at the tool seam — see [`AUTHENTICATION_RBAC.md`](AUTHENTICATION_RBAC.md).

---

## Level 3 — Orchestrator + Specialists

An optional front door decomposes a request into tasks, routes each to the
best-matched specialist, and synthesizes the result. Specialists remain directly
reachable — the orchestrator does not become a god-agent holding every
credential.

| Construct | Where |
|---|---|
| Orchestrator (plan → route → execute → synthesize) | [`autobot-backend/orchestrator.py`](../../autobot-backend/orchestrator.py) |
| Capability-scored agent routing | [`autobot-backend/orchestration/agent_router.py`](../../autobot-backend/orchestration/agent_router.py) (`AgentRouter`) |
| Multi-agent execution strategies (sequential/parallel/pipeline/collaborative) | [`autobot-backend/orchestration/workflow_runner.py`](../../autobot-backend/orchestration/workflow_runner.py) |

---

## Level 4 — Automated Team

Recurring, unattended work: scheduled jobs, audits, and governed agent-to-agent
delegation. Only switch this on once Levels 1–3 are stable.

| Construct | Where |
|---|---|
| Recurring/scheduled jobs (cleanup, audits, retention) | [`autobot-backend/celery_app.py`](../../autobot-backend/celery_app.py) (`beat_schedule`) |
| Governed subagent delegation (off by default) | [`autobot-backend/chat_workflow/delegation.py`](../../autobot-backend/chat_workflow/delegation.py) |

Delegated subtasks run as *governed autonomous agents*: the acting agent's
`forbidden_work` manifest is enforced at the tool seam, and in-process delegation
is depth-bounded. Delegation ships **off** behind `AUTOBOT_DELEGATION_ENABLED`, in
keeping with the "manual before automated" rule.

---

## Where to go next

- Capability boundaries & enforcement → [`AUTHENTICATION_RBAC.md`](AUTHENTICATION_RBAC.md)
- Model routing by task cost → [`TIERED_MODEL_ROUTING.md`](TIERED_MODEL_ROUTING.md)
- Sub-agent rules for parallel work → [`CLAUDE_BATCH.md`](CLAUDE_BATCH.md)
