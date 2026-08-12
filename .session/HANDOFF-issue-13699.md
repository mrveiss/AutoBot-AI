# Handoff: issue-13699
status: complete
pr: #13731
base_at_push: 319c00127
gates: tests=PASS (2/2 target nodes; 10/10 module under -m performance; 364 passed across orchestration/, services/workflow_automation/, services/advanced_workflow/, workflow_templates/, performance_benchmarks_test.py, dependency_injection_test.py)
needs_rebase_before_merge: no
remaining:
blocked_on:
worktree: .worktrees/issue-13699  (safe to remove after merge)

## What landed

Two commits:
- `fix(orchestrator)`: `plan_workflow_steps` repointed from the retired `id` /
  `expected_duration_ms` kwargs to the canonical `WorkflowTask` fields (`task_id` /
  `estimated_duration_seconds`). Every prior call raised TypeError into the broad
  handler and returned `[]`. Guard now logs `exc_info=True`.
- `test(orchestrator)`: `TestOrchestratorPerformance.setup_method` injects the config
  double via the constructor instead of patching the absent
  `orchestrator.config_manager`; binds a classification double so the measured path is
  environment-independent; asserts a real `TaskComplexity` and a non-empty plan.

## Carried forward — NOT done

**#13730** — every remaining caller of `plan_workflow_steps` is still broken:
- un-awaited async calls at `orchestration/workflow_planner.py:113,219`,
  `services/workflow_automation/manager.py:75-76`,
  `services/advanced_workflow/step_generator.py:63`
- reads of `step.id` / `step.user_approval_required`, absent from `WorkflowTask`
- `orchestration/plan_steps_e2e_test.py` has no assertions and swallows exceptions

Chat-request workflow planning is dead end-to-end until #13730 lands. Do not close
#13730 on the strength of this PR — it fixes the planner, not its callers.
