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
| [agent-terminal-implementation-plan.md](tasks/agent-terminal-implementation-plan.md) | Terminal agent PTY integration | Superseded — terminal implemented |
| [agent-files-optimization-plan.md](tasks/agent-files-optimization-plan.md) | Agent file consolidation | Superseded — see current issues |
| [async-optimization-follow-up-assessment.md](tasks/async-optimization-follow-up-assessment.md) | Async patterns audit | Largely complete |
| [backend-vulnerabilities-implementation-plan.md](tasks/backend-vulnerabilities-implementation-plan.md) | Security vulnerability fixes | Partially complete — see #3164 |
| [chat_404_implementation_plan.md](tasks/chat_404_implementation_plan.md) | Chat endpoint errors | Superseded |
| [commit-strategy-412-files.md](tasks/commit-strategy-412-files.md) | Commit strategy notes | Historical reference only |
| [gui-status-display-fix-task-breakdown-OLD.md](tasks/gui-status-display-fix-task-breakdown-OLD.md) | GUI status display | Superseded (marked OLD) |
| [phase-1-critical-fixes-detailed-breakdown.md](tasks/phase-1-critical-fixes-detailed-breakdown.md) | Phase 1 critical fixes | Superseded |
| [redis-service-endpoint-fix-plan.md](tasks/redis-service-endpoint-fix-plan.md) | Redis service endpoints | Largely complete |
| [redis-service-management-implementation-tasks.md](tasks/redis-service-management-implementation-tasks.md) | Redis service management | Partially complete — see open issues |
| [redis-sticky-tabs-fix-breakdown.md](tasks/redis-sticky-tabs-fix-breakdown.md) | Redis UI sticky tabs | Superseded |
| [ROOT_CAUSE_IMPLEMENTATION_PLAN.md](tasks/ROOT_CAUSE_IMPLEMENTATION_PLAN.md) | Root cause analysis | Historical reference |
| [AutoBot_Feature_Restoration_Project_Plan.md](tasks/AutoBot_Feature_Restoration_Project_Plan.md) | Feature restoration | GitHub issues filed for all items |
| [ai-optimized-roadmap.md](tasks/ai-optimized-roadmap.md) | AI optimization roadmap | Historical reference |
| [week-1-database-initialization-detailed-guide.md](tasks/week-1-database-initialization-detailed-guide.md) | DB init guide | Superseded by Ansible roles |
| [week-2-3-async-conversion-plan.md](tasks/week-2-3-async-conversion-plan.md) | Async conversion | Largely complete |

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
