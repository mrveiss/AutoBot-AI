---
tags:
  - planning
  - tasks
aliases:
  - Active Tasks
  - Task Tracker
---

# Active Task Tracking

> **Authoritative source: [GitHub Issues](https://github.com/mrveiss/AutoBot-AI/issues)**
>
> All active work items live in GitHub Issues. This file is a navigation aid only —
> it does not duplicate issue content.

---

## Open Issues by Area

Use these saved searches in GitHub:

| Area | Filter |
| --- | --- |
| All open | [open issues](https://github.com/mrveiss/AutoBot-AI/issues?q=is%3Aopen) |
| High priority | [`priority:high` label](https://github.com/mrveiss/AutoBot-AI/issues?q=is%3Aopen+label%3Apriority%3Ahigh) |
| Bugs | [`type:bug` label](https://github.com/mrveiss/AutoBot-AI/issues?q=is%3Aopen+label%3Abug) |
| Knowledge Base | [`area:knowledge-base`](https://github.com/mrveiss/AutoBot-AI/issues?q=is%3Aopen+label%3Aknowledge-base) |
| AutoResearch | [`area:auto-research`](https://github.com/mrveiss/AutoBot-AI/issues?q=is%3Aopen+label%3Aauto-research) |
| Infrastructure | [`area:infrastructure`](https://github.com/mrveiss/AutoBot-AI/issues?q=is%3Aopen+label%3Ainfrastructure) |
| Frontend | [`area:frontend`](https://github.com/mrveiss/AutoBot-AI/issues?q=is%3Aopen+label%3Afrontend) |

---

## Implementation Breakdown Files

The files below in `docs/planning/tasks/` are **per-issue implementation breakdowns**
written during active development. They predate the GitHub Issues workflow and most
are now complete or superseded.

**Do not add new tasks here.** File a GitHub Issue instead.

| File | Topic | Status |
| --- | --- | --- |
| [backend-vulnerabilities-implementation-plan.md](tasks/backend-vulnerabilities-implementation-plan.md) | Security vulnerability fixes | Active — keep until #3164 closed |
| [redis-service-management-implementation-tasks.md](tasks/redis-service-management-implementation-tasks.md) | Redis service management | Active — keep until Redis issues closed |

---

## How to File a New Issue

```
gh issue create \
  --title "<type>(<scope>): <description>" \
  --body "..." \
  --label "type:<bug|enhancement>,area:<area>,priority:<high|medium|low>"
```

All implementation work must be linked to a GitHub Issue before starting.
See [CLAUDE_RULES.md](../developer/CLAUDE_RULES.md) for the full workflow.
