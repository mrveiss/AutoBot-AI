# Handoff: issue-13751
status: complete
pr: #13760
base_at_push: origin/Dev_new_gui (up to date at push)
gates: tests=PASS (5/5 guard; 598 orchestration sweep; 316 repo_tests)
needs_rebase_before_merge: no
remaining:
blocked_on:
worktree: .worktrees/issue-13751  (safe to remove after merge)

## Resolution chosen

Took the "record superseded" branch of #13751's ACs, not "wire it in". Every public
method on `orchestration.WorkflowPlanner` has zero callers, and every capability has a
wired canonical equivalent (`create_workflow_plan`,
`AgentRouter.get_agent_recommendations_scored`, `_fetch_planning_context`, services
`WorkflowExecutor.present_plan_for_approval`). Wiring it would recreate the parallel
planning path the issue was filed to prevent.

Follows the #12373/#12579 precedent ("deprecate dead orchestration engine in place"),
which had covered the executor half and missed this planner sibling.

## Scope correction found mid-task

`create_plan_summary_for_approval` is ALSO uncalled — the whole class is unreachable,
not just the two methods named in the issue. Only `__init__` runs.

## Stale claims corrected

- `orchestration/workflow_planning.py` called WorkflowPlanner "the canonical (but
  currently unwired)" planner — inverted; `StrategyPlanner` there is the wired one.
- `orchestrator.py` `_step_planner` comment implied a live collaborator.

## Prior history

#6820 tracked this module as one of four orphans and closed 2026-05-17 with three wired
and this one left. #12579 deprecated the sibling and skipped it. Both recorded intent in
prose only — nothing held it, which is why it recurred. Hence the new guard test.

## AC 3 reinterpreted (flagged, not silently ticked)

"A test exercises each through its production entry point" is unsatisfiable — there is no
production entry point. Replaced with a guard pinning the *absence* of one.
#13730 already covers both methods directly.
