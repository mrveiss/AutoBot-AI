# ADR-006: Skill-Bound Planning

## Status

**Status**: Accepted

## Date

**Date**: 2026-05-16

## Context

AutoBot's `StrategyPlanner` (`enhanced_orchestration/workflow_planning.py`) builds workflow
plans whose steps target *agents* by `AgentCapability` via a static capability mapping. The
`SkillRegistry` (populated by governance-approved skills) was invisible to the planner, so
capability gaps surfaced only at execution time — after planning had already committed to
steps the executor might not be able to dispatch.

Concurrently, `skills/builtin/skill_router.py` provides a 3-phase resolution pipeline:

| Phase | Mechanism |
|-------|-----------|
| 1 | Keyword scoring against registered skills |
| 2 | LLM re-ranking of top-K candidates |
| 3 | Gap-fill: `skill-researcher` → `autonomous-skill-development` → governance → registration |

Neither `StrategyPlanner` nor `WorkflowExecutor` called `skill_router`, leaving the
Phase 3 learning loop dormant for the planning path.

### Forces

- Planning must remain fast; Phase 3 (LLM-driven skill generation) is too slow for inline
  synchronous invocation.
- Plan steps must remain dispatchable via the legacy capability-based agent routing as a
  fallback — no hard cutover on day one.
- `WorkflowTask` fields must live on the canonical shared type (`autobot_shared/workflow`)
  to avoid duplication across the three orchestration layers.

## Decision

Bind skills at **plan time** using `skill_router` in dry-run mode. Attach
`(skill_name, action)` to each `WorkflowTask` so `WorkflowExecutor` can dispatch via
`SkillRegistry` instead of (or alongside) capability-based agent routing.

Three phases, each independently deployable:

### Phase 1 — Planner → skill_router (dry-run)

`StrategyPlanner.build_workflow_plan()` calls `_bind_skill_to_task()` per task. The lookup
uses `dry_run=True`: no skill is auto-enabled and Phase 3 gap-fill does **not** run
synchronously. When a skill matches, `task.skill_name` and `task.skill_action` are set.
When no match is found, `task.skill_name` stays `None` and legacy capability dispatch
continues unchanged.

### Phase 2 — WorkflowExecutor skill dispatch

`WorkflowExecutor._execute_single_task()` checks `task.skill_name` before falling back to
capability-based agent routing. When set, it calls
`SkillRegistry.get(task.skill_name).execute(task.skill_action, task.inputs)` directly.
If the bound skill is missing or disabled at execution time, the step raises a structured
error (not a silent fallback) so the failure is observable.

### Phase 3 — Async gap-fill + blocked-plan resume path

When Phase 1 finds no matching skill, `_trigger_async_gap_fill()` fires in background
(no blocking). The task receives a `pending_skill_id`. The plan is constructed in
`BLOCKED_ON_SKILL_GENERATION` state. A `BlockedPlanResumer` subscriber listens on the
`skill_promoted` Redis pub-sub channel; when a generated skill is registered it re-runs
Phase 1 for every task with a matching `pending_skill_id` and flips the plan to `PENDING`.

### Canonical task fields

`skill_name`, `skill_action`, `skill_resolution_method`, and `pending_skill_id` live on
`autobot_shared.workflow.WorkflowTask` — the single source of truth inherited by both
`enhanced_orchestration.types.AgentTask` and any future orchestration layer.

### Alternatives Considered

1. **Inline synchronous Phase 3 at plan time**
   - Pros: Plan always has a bound skill before returning.
   - Cons: Planning latency becomes unbounded (LLM + governance + registration). Rejected.

2. **Post-execution skill assignment** (bind during executor, not planner)
   - Pros: No change to planner API.
   - Cons: Loses ADR-006's key property: plans are verifiable before execution. Rejected.

3. **Static `CAPABILITY_MAPPING` extension** (add skill names to the existing map)
   - Pros: No new infrastructure.
   - Cons: Requires manual maintenance; cannot discover dynamically-registered skills.
     Rejected.

## Consequences

### Positive

- Plans are verifiable before execution: each step is bound to a known registered skill or
  explicitly flagged as pending.
- The Phase 3 learning loop (`skill-researcher` → `autonomous-skill-development`) now fires
  on planning gaps, not just execution gaps.
- Legacy capability-based routing continues to work unchanged for unbound steps.
- `WorkflowTask` fields are canonical — no duplication across orchestration layers.

### Negative

- Plans with unresolvable skills block until Phase 3 completes (or time out). The executor
  must handle `BLOCKED_ON_SKILL_GENERATION` state.
- `skill_router` availability is now a soft dependency of the planner. Unavailability
  degrades gracefully (Phase 1 skipped, legacy routing used) but increases latency jitter.

### Neutral

- `WorkflowExecutor` dispatch logic bifurcates: skill-bound path vs. capability path.
  Both are tested independently.

## Implementation Notes

### Key Files

- `autobot_shared/workflow/types.py` — `WorkflowTask`: `skill_name`, `skill_action`,
  `skill_resolution_method`, `pending_skill_id` fields added here (single source).
- `autobot-backend/enhanced_orchestration/workflow_planning.py` — `StrategyPlanner`:
  `build_workflow_plan()`, `_bind_skill_to_task()`, `_get_skill_router()`,
  `_trigger_async_gap_fill()`.
- `autobot-backend/enhanced_orchestration/workflow_runner.py` — `WorkflowExecutor`:
  `_dispatch_via_skill()` invoked when `task.skill_name` is set.
- `autobot-backend/skills/builtin/skill_router.py` — 3-phase meta-skill providing
  `find_skill` and `route` actions.
- `autobot-backend/skills/pending_skills.py` — `trigger_gap_fill()`, `PendingSkillsRegistry`.
- `autobot-backend/enhanced_orchestration/workflow_planning_test.py` — unit tests for
  Phases 1 and 3.

### Skill resolution action name

`_bind_skill_to_task()` invokes `router.execute("find_skill", {"task": <desc>, "dry_run": True})`.
The `find_skill` action returns `{"success": bool, "enabled_skill": str | None, "method": str}`.
Phase 3 fires when `success=True` and `enabled_skill` is `None` (no current match, but router
found the task description valid for gap-fill).

### Blocked-plan state

`WorkflowPlan.status` is set to `"blocked"` (string, not enum) when one or more tasks carry a
`pending_skill_id`. The `BlockedPlanResumer` subscriber is responsible for flipping this field
to `"pending"` after re-binding and must be wired to the `skill_promoted` pub-sub channel.

### Code Example — plan-time binding (Phase 1)

```python
# StrategyPlanner._bind_skill_to_task (simplified)
router = self._get_skill_router()
result = await router.execute("find_skill", {"task": task_desc, "dry_run": True})
if result.get("success") and result.get("enabled_skill"):
    task.skill_name = result["enabled_skill"]
    task.skill_action = task_data.get("skill_action") or "execute"
```

### Code Example — execution-time dispatch (Phase 2)

```python
# WorkflowExecutor._execute_single_task (simplified)
if task.skill_name:
    return await self._dispatch_via_skill(task)
# else: legacy capability-based agent routing
```

## Related ADRs

- [ADR-004](004-chat-workflow-architecture.md) — chat workflow architecture that `StrategyPlanner`
  participates in.

---

**Author**: mrveiss
**Copyright**: © 2025 mrveiss
