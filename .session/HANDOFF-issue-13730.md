# Handoff: issue-13730
status: complete
pr: #13752
base_at_push: (rebased onto origin/Dev_new_gui after #13728)
gates: tests=PASS (6/6 target; 995 passed across orchestration/, tests/orchestration/, services/workflow_automation/, services/advanced_workflow/, workflow_templates/, chat_workflow/, performance_benchmarks_test.py, dependency_injection_test.py)
needs_rebase_before_merge: no
remaining:
blocked_on:
worktree: .worktrees/issue-13730  (safe to remove after merge)

## What landed

Two commits:
- `fix(orchestration)`: awaits added at all four planning call sites;
  `get_plan_summary` converted to `async def`; attribute reads moved to canonical
  `WorkflowTask` names (`task_id`, `requires_approval`); `manager.py` handler logs
  `exc_info`. Dict keys left alone on purpose — they are `workflow_planner`'s own
  contract with `create_plan_summary_for_approval` (line 267).
- `test(orchestration)`: `plan_steps_e2e_test.py` rewritten with real assertions;
  new `tests/orchestration/test_planning_caller_wiring.py` drives all four callers
  with a real `Orchestrator`.

## Live impact fixed

`api/workflow.py:290` and `services/workflow_automation/routes.py:258` both reach
`create_workflow_from_chat_request`. It returned `None` for every request, and
`api/workflow.py:292` maps that to **HTTP 500**. Chat-driven workflow creation was
returning 500 on every call.

## Carried forward — NOT done

**#13751** — `WorkflowPlanner.plan_workflow_steps_with_agents` and `get_plan_summary`
have zero callers. Corrected and tested here, but unwired: agent-assigned planning and
plan preview are unreachable from any production path. Do not close #13751 on the
strength of this PR.
