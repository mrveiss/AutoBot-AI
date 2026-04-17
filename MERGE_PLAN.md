# Merge Plan: issue-5040 — One Conductor Orchestrator Refactor

## Part A — Merge EnhancedMultiAgentOrchestrator into ConsolidatedOrchestrator

### Method Audit

#### ConsolidatedOrchestrator methods (orchestrator.py)

| Method | Purpose | Decision |
|--------|---------|----------|
| `__init__` | Sets up LLM, memory, agents, registry | KEEP |
| `_init_core_components` | Factored init helper | KEEP |
| `_init_task_state` | Factored init helper | KEEP |
| `_init_enhanced_components` | Factored init helper | KEEP |
| `_init_classification_agent` | Factored init helper | KEEP |
| `_initialize_default_agents` | Seeds agent_registry | KEEP |
| `_create_*_agent_profile` x4 | Profile factories | KEEP |
| `_validate_llm_model` | Tests LLM connection | KEEP |
| `_ensure_working_llm_model` | Fallback model selection | KEEP |
| `initialize` | Async startup | KEEP |
| `shutdown` | Async teardown | KEEP |
| `process_user_request` | Main entrypoint | KEEP |
| `_classify_task` | Task classification helper | KEEP |
| `_select_model_for_task` | Model selection | KEEP |
| `_execute_mode_request` | Mode dispatch | KEEP |
| `_build_success_response` | Response builder | KEEP |
| `_build_failure_response` | Response builder | KEEP |
| `_process_simple_request` | Simple mode handler | KEEP |
| `_process_enhanced_request` | Enhanced mode handler | KEEP |
| `_process_parallel_request` | Parallel mode handler | KEEP |
| `_process_sequential_request` | Sequential mode handler | KEEP |
| `_execute_agents_sequentially` | Multi-agent sequential | KEEP |
| `_execute_agents_in_parallel` | Multi-agent parallel | KEEP |
| `_coordinate_multiple_agents` | Multi-agent coordinator | KEEP |
| `_synthesize_agent_results` | Result synthesis | KEEP |
| `register_agent` | Agent registration | KEEP |
| `find_best_agent_for_task` | Agent selection (delegates to util) | KEEP |
| `_reserve_agent` | Agent reservation (delegates to util) | KEEP |
| `_release_agent` | Agent release (delegates to util) | KEEP |
| `_update_agent_performance` | Updates AgentProfile (delegates to util) | KEEP (renamed `_update_profile_performance` to disambiguate) |
| `_get_enhanced_planner` | Lazy planner init | KEEP |
| `_get_enhanced_executor` | Lazy executor init | KEEP |
| `_get_enhanced_documenter` | Lazy documenter init | KEEP |
| `execute_enhanced_workflow` | Full workflow with docs | KEEP |
| `set_phi2_enabled` | Config update | KEEP |
| `get_status` | Status/metrics | KEEP |
| `update_configuration` | Dynamic config | KEEP |
| `classify_request_complexity` | Compat method | KEEP |
| `plan_workflow_steps` | Compat method | KEEP |
| `_create_simple_workflow_step` | Helper | KEEP |
| `_create_complex_workflow_steps` | Helper | KEEP |

#### EnhancedMultiAgentOrchestrator methods (enhanced_orchestration/__init__.py)

| Method | Purpose | Decision |
|--------|---------|----------|
| `__init__` | Sets up agent_capabilities, agent_performance, Redis, planner | PORT into Orchestrator |
| `_ensure_redis` | Lazy Redis init | PORT |
| `_get_strategy_handler` | Lazy strategy handler | PORT |
| `_build_planning_prompt` | LLM prompt for workflow planning | PORT |
| `_parse_planning_response` | Parse LLM response | PORT |
| `create_workflow_plan` | LLM-driven workflow plan creation | PORT (UNIQUE) |
| `_evaluate_criteria` | Success criteria evaluation | PORT |
| `_handle_workflow_success` | Workflow success handling + metrics | PORT |
| `_handle_workflow_failure` | Workflow failure with fallback plans | PORT |
| `execute_workflow` | Execute a WorkflowPlan | PORT (UNIQUE) |
| `_handle_task_timeout` | Task retry on timeout | PORT |
| `_handle_task_exception` | Task exception handling | PORT |
| `_execute_single_task` | Execute one AgentTask | PORT (UNIQUE) |
| `get_agent_recommendations` | Rank agents by capability+performance | PORT (UNIQUE) |
| `_coordinate_collaboration` | Redis pubsub collaboration | PORT |
| `_broadcast_to_agents` | Redis publish | PORT |
| `_update_performance_metrics` | Update metrics for all plan tasks | PORT |
| `_update_agent_performance` | Update AgentPerformance dataclass | PORT (renamed `_update_task_agent_performance` — different data structure than ConsolidatedOrchestrator's method) |
| `_publish_workflow_event` | Publish via event_manager | PORT |
| `_get_agent_instance` | Get agent from AgentClientRegistry | PORT |
| `get_performance_report` | Dict of perf data | PORT (UNIQUE) |
| `_calculate_capability_coverage` | Coverage stats | PORT (UNIQUE) |

### Duplicate Resolution

`_update_agent_performance` exists in both but with DIFFERENT data structures:
- ConsolidatedOrchestrator's version: updates `AgentProfile` in `self.agent_registry`, delegates to `utils.agent_selection._update_performance`
- EnhancedMultiAgentOrchestrator's version: updates `AgentPerformance` in `self.agent_performance`

Resolution: Both must coexist as they operate on different state. Rename the ported one to `_update_task_agent_performance` in the merged Orchestrator. Update all callers within the ported methods.

### State Merging in __init__

The merged Orchestrator.__init__ will call both init chains:
1. Existing: `_init_core_components`, `_init_task_state`, `_init_enhanced_components`, `_init_classification_agent`, `_initialize_default_agents`
2. New: `_init_enhanced_multi_agent_state` (new method factoring out the EnhancedMultiAgentOrchestrator __init__ state)

### Module Singleton

`enhanced_orchestrator` module-level singleton in `enhanced_orchestration/__init__.py` must be removed.
`api/orchestration.py` must be updated to use `get_orchestrator_sync()` from `orchestrator.py`.
`create_and_execute_workflow` convenience function must be ported to `orchestrator.py`.

## Part B — Rename ConsolidatedOrchestrator → Orchestrator

Files to update:
- `orchestrator.py`: class definition, docstrings, `__all__`, singleton functions
- `dependencies.py`: 4 occurrences
- All test files using `ConsolidatedOrchestrator as Orchestrator` alias
- `initialization/lifespan.py`: docstring references
- `utils/resource_factory.py`: docstring
- `api/api_endpoint_migrations_test.py`: test assertions
- `services/advanced_workflow/step_generator.py`: type annotation
- Any other grep hits

## Part C — Rename 6 Specialized Classes

### 1. SLMDeploymentOrchestrator → SLMDeploymentBridge
- File: `services/slm/deployment_orchestrator.py` → `services/slm/deployment_bridge.py`
- Call sites: `api/slm/deployments.py`, `api/slm/deployments_api_test.py`

### 2. DeploymentOrchestrator → DeploymentCoordinator
- File: split from `deployment_orchestrator.py` into `services/slm/deployment_coordinator.py`
- Call sites: `api/slm/deployments.py`, `api/slm/deployments_api_test.py`, `initialization/lifespan.py`, `services/slm/deployment_orchestrator.py`

### 3. SubagentOrchestrator → SubagentDispatcher
- File: `services/orchestration/subagent_orchestrator.py` → `services/orchestration/subagent_dispatcher.py`
- Function: `get_subagent_orchestrator` → `get_subagent_dispatcher`
- Call sites: `tests/orchestration/test_subagent_orchestrator_reflection.py`

### 4. AutonomousLoopOrchestrator → AutonomousLoopRunner
- File: same file (class rename only)
- Function: `get_loop_orchestrator` stays (or rename to `get_loop_runner`)
- Call sites: `api/knowledge_rag.py`, `services/knowledge/test_autonomous_loop.py`

### 5. AdvancedWorkflowOrchestrator → WorkflowCoordinator
- File: `services/advanced_workflow/orchestrator.py` → `services/advanced_workflow/coordinator.py`
- Call sites: `services/advanced_workflow/__init__.py`, `services/advanced_workflow/routes.py`

### 6. AgentOrchestrator → DistributedAgentCoordinator
- File: same file, class rename only
- Call sites: `agents/agent_orchestration/__init__.py`, `a2a/task_executor.py`, `agents/__init__.py`, `a2a/a2a_test.py`
- Function: `get_agent_orchestrator` → `get_distributed_agent_coordinator`

## Part D — Close-out

### #5038: ResourceFactory.get_enhanced_orchestrator → get_orchestrator
- `utils/resource_factory.py`: method rename + docstring + cache key `"enhanced_orchestrator"` → `"orchestrator"`
- `get_orchestrator` shorthand function already exists at bottom of file — need to update it

### #5039: Remove `as Orchestrator` aliases in test files
After Part B rename, `from orchestrator import Orchestrator` directly (no alias needed)
Files:
- `orchestration/current_status.e2e_test.py`
- `orchestration/workflow_orchestration.e2e_test.py`
- `orchestration/final_workflow.e2e_test.py`
- `orchestration/workflow_execution.e2e_test.py`
- `orchestration/plan_steps.e2e_test.py`
- `complete_system.e2e_test.py`
- `performance_benchmarks.performance_test.py`
- `tools/tool_registry_debug.e2e_test.py`
- `api/api_debug.e2e_test.py`
- `dependency_injection_test.py`
- `api/api_endpoint_migrations_test.py`
