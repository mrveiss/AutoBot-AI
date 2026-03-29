# Visual Workflow System with Parallel Execution


## Quick Answer

**How do you create and execute a visual workflow with parallel fleet execution in AutoBot?**

Define workflow steps with a shared `parallel_group` (no inter-dependencies) so the
execution engine runs them concurrently. Steps with `dependencies` wait for
predecessors. Here is a complete example that runs audit scripts in parallel across
three fleet nodes, then aggregates results:

```python
#!/usr/bin/env python3
"""Create and execute a parallel fleet workflow via the AutoBot API."""

import asyncio

import aiohttp

from autobot_shared.ssot_config import config

BACKEND_URL = f"https://{config.vm.main}:{config.port.backend}"


async def run_parallel_fleet_audit(token: str):
    """Submit a parallel workflow that audits three fleet nodes simultaneously.

    Steps 1-3 share parallel_group 'audit_batch_1' and run concurrently.
    Step 4 depends on all three completing before it aggregates results.
    """
    workflow = {
        "user_message": "Run security audit across fleet in parallel",
        "auto_approve": False,
        "workflow_template": {
            "name": "parallel_fleet_audit",
            "description": "Audit scripts on three nodes simultaneously",
            "steps": [
                {
                    "id": "audit_frontend",
                    "agent_type": "system_commands",
                    "action": "execute_shell",
                    "target_node": config.vm.frontend,
                    "command": "/opt/autobot/scripts/audit/check_permissions.sh",
                    "parallel_group": "audit_batch_1",
                    "timeout": 300,
                    "inputs": {"target_host": config.vm.frontend},
                },
                {
                    "id": "audit_npu",
                    "agent_type": "system_commands",
                    "action": "execute_shell",
                    "target_node": config.vm.npu,
                    "command": "/opt/autobot/scripts/audit/check_services.sh",
                    "parallel_group": "audit_batch_1",
                    "timeout": 300,
                    "inputs": {"target_host": config.vm.npu},
                },
                {
                    "id": "audit_ai_stack",
                    "agent_type": "system_commands",
                    "action": "execute_shell",
                    "target_node": config.vm.aistack,
                    "command": "/opt/autobot/scripts/audit/check_network.sh",
                    "parallel_group": "audit_batch_1",
                    "timeout": 300,
                    "inputs": {"target_host": config.vm.aistack},
                },
                {
                    "id": "aggregate_results",
                    "agent_type": "orchestrator",
                    "action": "aggregate_results",
                    "dependencies": ["audit_frontend", "audit_npu", "audit_ai_stack"],
                    "user_approval_required": False,
                    "inputs": {"report_format": "markdown"},
                },
            ],
        },
    }

    async with aiohttp.ClientSession() as session:
        # Submit workflow
        resp = await session.post(
            f"{BACKEND_URL}/api/workflow/execute",
            json=workflow,
            headers={"Authorization": f"Bearer {token}"},
            ssl=False,
        )
        result = await resp.json()
        workflow_id = result.get("workflow_id")

        # Poll status
        while workflow_id:
            status_resp = await session.get(
                f"{BACKEND_URL}/api/workflow/workflow/{workflow_id}/status",
                headers={"Authorization": f"Bearer {token}"},
                ssl=False,
            )
            status = await status_resp.json()
            print(f"Progress: {status.get('progress', 0) * 100:.0f}%  "
                  f"Step: {status.get('current_step_info', {}).get('description', 'N/A')}")
            if status.get("status") in ("complete", "failed", "cancelled"):
                break
            await asyncio.sleep(5)

        return result


if __name__ == "__main__":
    import sys
    token = sys.argv[1] if len(sys.argv) > 1 else "YOUR_JWT_TOKEN"
    asyncio.run(run_parallel_fleet_audit(token))
```

**In the Visual Builder UI** (`/workflow-builder`):
1. Add three step nodes (one per fleet node), do NOT connect them to each other
2. Add one aggregation node, draw edges FROM each audit node TO it
3. Click Save, switch to Runner tab, click Execute

For execution strategies (sequential, pipeline, adaptive) see [Section 5](#5-parallel-execution-engine).

---


AutoBot's workflow system orchestrates multi-agent task execution with support for
parallel step groups, dependency-based scheduling, and distributed fleet operations.
This guide covers defining, executing, and monitoring workflows that run shell scripts
in parallel across AutoBot's infrastructure fleet.

**Source files referenced in this document:**

| Component | Path |
|-----------|------|
| Workflow API | `autobot-backend/api/workflow.py` |
| Workflow State Machine | `autobot-backend/api/workflow_state.py` |
| Agent Registry | `autobot-backend/orchestration/agent_registry.py` |
| Orchestration Types | `autobot-backend/orchestration/types.py` |
| Workflow Planner | `autobot-backend/orchestration/workflow_planner.py` |
| Workflow Executor | `autobot-backend/orchestration/workflow_executor.py` |
| Parallel Tool Executor | `autobot-backend/tools/parallel/executor.py` |
| Parallel Types | `autobot-backend/tools/parallel/types.py` |
| Execution Strategies | `autobot-backend/enhanced_orchestration/execution_strategies.py` |
| Enhanced Orchestration Types | `autobot-backend/enhanced_orchestration/types.py` |
| Workflow Classifier | `autobot-backend/workflow_classifier.py` |
| Workflow Templates (types) | `autobot-backend/workflow_templates/types.py` |
| Workflow Templates (security) | `autobot-backend/workflow_templates/security.py` |
| Workflow Templates (sysadmin) | `autobot-backend/workflow_templates/sysadmin.py` |
| Workflow Automation Models | `autobot-backend/services/workflow_automation/models.py` |
| Workflow Automation Executor | `autobot-backend/services/workflow_automation/executor.py` |
| Workflow Builder composable | `autobot-frontend/src/composables/useWorkflowBuilder.ts` |
| Workflow Canvas component | `autobot-frontend/src/components/workflow/WorkflowCanvas.vue` |
| Workflow Builder view | `autobot-frontend/src/views/WorkflowBuilderView.vue` |
| Workflow Templates types (TS) | `autobot-frontend/src/types/workflowTemplates.ts` |

---

## 1. Workflow System Overview

AutoBot's workflow system is built around a multi-agent orchestration architecture. A
user request enters through the chat interface or API, gets classified by complexity,
and is decomposed into a plan of ordered steps. Each step is assigned to a specialized
agent, and the execution engine runs the steps respecting dependency constraints and
parallel group assignments.

### Request Classification

The `WorkflowClassifier` (in `autobot-backend/workflow_classifier.py`) classifies every
incoming request into one of two active complexity levels defined in `autobot_types.py`:

```python
class TaskComplexity(Enum):
    SIMPLE = "simple"    # Regular conversation with Knowledge Base integration
    COMPLEX = "complex"  # Requires tools, research, or system actions

    # Legacy aliases (map to COMPLEX internally)
    RESEARCH = "complex"
    INSTALL = "complex"
    SECURITY_SCAN = "complex"
```

Classification uses keyword matching against Redis-stored rules. The default rule set
lives in `DEFAULT_CLASSIFICATION_KEYWORDS` and `DEFAULT_CLASSIFICATION_RULES` at module
level in `workflow_classifier.py`. Keywords are organized into categories: `research`,
`install`, `complex`, `security`, `network`, and `system`. Rules are prioritized
(highest first) and use boolean conditions such as
`any_security AND any_network` or `research >= 2 OR has_tools`.

`SIMPLE` requests are handled inline by the lightweight orchestrator.
`COMPLEX` requests enter the full workflow pipeline: planning, approval, execution,
and validation.

### Agent Registry

The `AgentRegistry` class in `autobot-backend/orchestration/agent_registry.py` manages
four default agent profiles, each with distinct capabilities:

| Agent ID | Agent Type | Capabilities | Max Concurrent |
|----------|------------|-------------|----------------|
| `research_agent` | `research` | RESEARCH, ANALYSIS | 5 |
| `documentation_agent` | `librarian` | DOCUMENTATION, KNOWLEDGE_MANAGEMENT | 3 |
| `system_agent` | `system_commands` | SYSTEM_OPERATIONS, CODE_GENERATION | 2 |
| `coordination_agent` | `orchestrator` | WORKFLOW_COORDINATION, ANALYSIS | 10 |

Additional agents can be registered at runtime via `AgentRegistry.register()`. The
registry tracks each agent's current workload, success rate (exponential moving
average, alpha=0.1), and average completion time.

The API layer's step dispatch table in `api/workflow.py` adds further specialized
handlers:

| Agent Type | Handler | Purpose |
|------------|---------|---------|
| `librarian` | `_handle_librarian_step` | Knowledge Base search |
| `research` | `_handle_research_step` | Web research and tool discovery |
| `orchestrator` | `_handle_orchestrator_step` | Plan coordination, result aggregation |
| `knowledge_manager` | `_handle_knowledge_manager_step` | Knowledge Base storage |
| `security_scanner` | `_handle_security_scanner_step` | Port/vulnerability scanning |
| `network_discovery` | `_handle_network_discovery_step` | Host enumeration |
| `system_commands` | `_handle_system_commands_step` | Shell command execution |

### Visual Workflow Builder

The frontend provides a full visual workflow builder at the `/workflow-builder` route.
The view (`WorkflowBuilderView.vue`) includes five sections accessible from a sidebar:

1. **Overview** -- Active workflow count, recent executions, system status.
2. **Visual Builder** (`WorkflowCanvas.vue`) -- Drag-and-drop canvas with node
   creation, connection drawing, zoom/pan, and auto-layout.
3. **Templates** (`WorkflowTemplateGallery.vue`) -- Browse and instantiate pre-built
   workflow templates by category.
4. **Natural Language** -- Describe a workflow in plain text and have the backend
   classify and plan it.
5. **Runner** (`WorkflowRunner.vue`) -- Execute workflows, approve steps, view
   real-time progress.

The canvas supports `step` nodes (command + description + risk level + confirmation
toggle) and `condition` nodes (branching logic). Nodes are connected via SVG path
edges with directional arrow markers.

---

## 2. Workflow Data Model

AutoBot uses several complementary data models depending on which layer of the system
is operating. Below are the primary structures.

### Core Types (orchestration layer)

From `autobot-backend/orchestration/types.py`:

```python
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Set

class AgentCapability(Enum):
    RESEARCH = "research"
    ANALYSIS = "analysis"
    DOCUMENTATION = "documentation"
    CODE_GENERATION = "code_generation"
    SYSTEM_OPERATIONS = "system_operations"
    DATA_PROCESSING = "data_processing"
    KNOWLEDGE_MANAGEMENT = "knowledge_management"
    WORKFLOW_COORDINATION = "workflow_coordination"

@dataclass
class WorkflowStep:
    step_id: str
    action: str
    description: str
    agent_id: str
    required_capabilities: Set[AgentCapability]
    estimated_duration: float
    dependencies: List[str] = field(default_factory=list)
    status: str = "pending"
    result: Dict[str, Any] = field(default_factory=dict)

@dataclass
class WorkflowPlan:
    workflow_id: str
    title: str
    description: str
    steps: List[WorkflowStep]
    created_at: datetime
    estimated_total_duration: float
    status: str = "pending"
    approval_required: bool = True
    approved: bool = False
```

### Template Types (workflow_templates layer)

From `autobot-backend/workflow_templates/types.py`:

```python
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List

class TemplateCategory(Enum):
    SECURITY = "security"
    RESEARCH = "research"
    SYSTEM_ADMIN = "system_admin"
    DEVELOPMENT = "development"
    ANALYSIS = "analysis"
    COMMUNITY = "community"

@dataclass
class WorkflowStep:
    id: str
    agent_type: str
    action: str
    description: str
    requires_approval: bool = False
    dependencies: List[str] = None      # Step IDs that must complete first
    inputs: Dict[str, Any] = None       # Parameters passed to the agent
    expected_duration_ms: int = 5000
```

### Enhanced Orchestration Types (parallel execution layer)

From `autobot-backend/enhanced_orchestration/types.py`:

```python
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Set

class ExecutionStrategy(Enum):
    SEQUENTIAL = "sequential"       # One step after another
    PARALLEL = "parallel"           # Independent steps run concurrently
    PIPELINE = "pipeline"           # Output of one stage feeds into the next
    COLLABORATIVE = "collaborative" # Agents communicate during execution
    ADAPTIVE = "adaptive"           # Strategy changes based on progress

@dataclass
class AgentTask:
    task_id: str
    agent_type: str
    action: str
    inputs: Dict[str, Any]
    dependencies: List[str] = field(default_factory=list)
    priority: int = 5
    timeout: float = 30.0
    capabilities_required: Set[AgentCapability] = field(default_factory=set)
    status: str = "pending"
    metadata: Dict[str, Any] = field(default_factory=dict)

@dataclass
class WorkflowPlan:
    plan_id: str
    goal: str
    strategy: ExecutionStrategy
    tasks: List[AgentTask]
    dependencies_graph: Dict[str, List[str]]  # task_id -> [dependency_ids]
    estimated_duration: float
    resource_requirements: Dict[str, Any]
    success_criteria: List[str]
    fallback_plans: List["WorkflowPlan"] = field(default_factory=list)
```

### Parallel Tool Call Types

From `autobot-backend/tools/parallel/types.py`:

```python
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Optional
import uuid

class DependencyType(Enum):
    NONE = auto()           # No dependency, can run in parallel
    DATA = auto()           # Output of A is input to B
    RESOURCE = auto()       # Both access same resource
    ORDER = auto()          # Must run in specific order
    TRANSACTIONAL = auto()  # Must complete together or rollback

@dataclass
class ToolCall:
    call_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    tool_name: str = ""
    arguments: dict = field(default_factory=dict)
    priority: int = 0
    depends_on: list[str] = field(default_factory=list)
    dependency_types: dict[str, DependencyType] = field(default_factory=dict)
    status: str = "pending"
    result: Any = None
    error: Optional[str] = None
    execution_time_ms: float = 0.0
    parallel_group_id: Optional[str] = None
```

### Workflow State (Redis-persisted)

From `autobot-backend/api/workflow_state.py`, the `WorkflowStateMachine` persists state
to Redis under `autobot:workflow:{workflow_id}` with a 7-day TTL on completion:

```python
class WorkflowState(BaseModel):
    workflow_id: str
    goal: str
    current_step: str = "planning"    # planning | awaiting_approval | executing |
                                      # validating | complete | failed
    active_service: str = "main-backend"
    steps_completed: List[str] = []
    steps_remaining: List[Dict] = []
    done: bool = False
    errors: List[str] = []
    created_at: str
    updated_at: str
    metadata: Dict = {}
```

---

## 3. Defining Parallel Workflows

Parallel execution is the central concept for fleet-wide operations. Steps that share
the same `parallel_group` (or have no inter-dependencies) execute concurrently. Steps
with `dependencies` wait until all listed predecessor step IDs complete successfully
before starting.

### Via the Workflow API

The following example defines a workflow that executes three shell scripts in parallel
across three fleet nodes, then aggregates the results:

```python
import aiohttp
import json

from autobot_shared.ssot_config import config

BACKEND_URL = f"https://{config.vm.main}:{config.port.backend}"

async def create_parallel_fleet_audit():
    """Define a workflow that runs three audit scripts in parallel across the fleet.

    Steps 1-3 share parallel_group 'audit_batch_1' and have no inter-dependencies,
    so the execution engine runs them concurrently. Step 4 depends on all three
    completing before it aggregates results.
    """
    workflow_definition = {
        "user_message": "Execute security audit scripts in parallel across fleet",
        "auto_approve": False,
        "workflow_template": {
            "name": "parallel_fleet_audit",
            "description": "Run audit scripts across multiple nodes simultaneously",
            "steps": [
                {
                    "id": "audit_frontend",
                    "agent_type": "system_commands",
                    "action": "execute_shell",
                    "target_node": config.vm.frontend,
                    "command": "/opt/autobot/scripts/audit/check_permissions.sh",
                    "parallel_group": "audit_batch_1",
                    "timeout": 300,
                    "inputs": {
                        "target_host": config.vm.frontend,
                        "script": "/opt/autobot/scripts/audit/check_permissions.sh",
                    },
                },
                {
                    "id": "audit_npu",
                    "agent_type": "system_commands",
                    "action": "execute_shell",
                    "target_node": config.vm.npu,
                    "command": "/opt/autobot/scripts/audit/check_services.sh",
                    "parallel_group": "audit_batch_1",
                    "timeout": 300,
                    "inputs": {
                        "target_host": config.vm.npu,
                        "script": "/opt/autobot/scripts/audit/check_services.sh",
                    },
                },
                {
                    "id": "audit_ai_stack",
                    "agent_type": "system_commands",
                    "action": "execute_shell",
                    "target_node": config.vm.aistack,
                    "command": "/opt/autobot/scripts/audit/check_network.sh",
                    "parallel_group": "audit_batch_1",
                    "timeout": 300,
                    "inputs": {
                        "target_host": config.vm.aistack,
                        "script": "/opt/autobot/scripts/audit/check_network.sh",
                    },
                },
                {
                    "id": "aggregate_results",
                    "agent_type": "orchestrator",
                    "action": "aggregate_results",
                    "dependencies": [
                        "audit_frontend",
                        "audit_npu",
                        "audit_ai_stack",
                    ],
                    "user_approval_required": False,
                    "inputs": {
                        "report_format": "markdown",
                    },
                },
            ],
        },
    }

    async with aiohttp.ClientSession() as session:
        response = await session.post(
            f"{BACKEND_URL}/api/workflow/execute",
            json=workflow_definition,
            ssl=False,
        )
        result = await response.json()
        return result
```

**Key points:**

- The three `system_commands` steps all specify `"parallel_group": "audit_batch_1"`.
  Steps in the same parallel group execute concurrently.
- The `aggregate_results` step lists all three audit steps in its `dependencies` array.
  It will not start until every dependency completes successfully.
- `target_node` tells the executor which fleet host to SSH into.
- `timeout` is per-step in seconds. The group-level timeout is configurable via
  `ParallelExecutorConfig.group_timeout_ms` (default 60000ms).

### Via the Visual Builder

In the frontend's WorkflowCanvas:

1. Click **Add Step** three times to create three step nodes.
2. For each node, enter the shell command and description. Set risk level as needed.
3. Do **not** draw dependency connections between the three nodes -- the absence of
   edges means they can run in parallel.
4. Click **Add Step** once more for the aggregation step.
5. Draw edges from each of the three audit nodes to the aggregation node. This
   establishes the dependency relationship.
6. Click **Save** to persist the workflow definition.
7. Switch to the **Runner** tab and click **Execute**.

The canvas uses connection ports (`.port-in` and `.port-out`) on each node. Dragging
from an output port to an input port creates a directed edge that maps to the
`dependencies` array in the backend data model.

### Via the Template System

Pre-built templates can also define parallel groups. Register a template via the
`WorkflowTemplateManager`:

```python
from workflow_templates.types import (
    TemplateCategory,
    WorkflowStep,
    WorkflowTemplate,
)
from autobot_types import TaskComplexity

parallel_audit_template = WorkflowTemplate(
    id="parallel_fleet_audit",
    name="Parallel Fleet Security Audit",
    description="Run security audit scripts across fleet nodes simultaneously",
    category=TemplateCategory.SECURITY,
    complexity=TaskComplexity.COMPLEX,
    estimated_duration_minutes=10,
    agents_involved=["system_commands", "orchestrator"],
    tags=["security", "audit", "parallel", "fleet"],
    variables={
        "target_nodes": "Comma-separated list of target node IPs",
        "audit_script": "Path to audit script on target nodes",
    },
    steps=[
        WorkflowStep(
            id="audit_node_1",
            agent_type="system_commands",
            action="Execute audit script on node 1",
            description="System_Commands: Audit Node 1",
            inputs={"parallel_group": "audit_batch"},
            expected_duration_ms=30000,
        ),
        WorkflowStep(
            id="audit_node_2",
            agent_type="system_commands",
            action="Execute audit script on node 2",
            description="System_Commands: Audit Node 2",
            inputs={"parallel_group": "audit_batch"},
            expected_duration_ms=30000,
        ),
        WorkflowStep(
            id="audit_node_3",
            agent_type="system_commands",
            action="Execute audit script on node 3",
            description="System_Commands: Audit Node 3",
            inputs={"parallel_group": "audit_batch"},
            expected_duration_ms=30000,
        ),
        WorkflowStep(
            id="generate_report",
            agent_type="orchestrator",
            action="Aggregate audit results into report",
            description="Orchestrator: Generate Audit Report",
            dependencies=["audit_node_1", "audit_node_2", "audit_node_3"],
            requires_approval=True,
            expected_duration_ms=10000,
        ),
    ],
)
```

---

## 4. Workflow API Endpoints

All workflow endpoints require admin authentication (`check_admin_permission`
dependency). The router is mounted at `/api/workflow` in the backend.

### Execute Workflow

```http
POST /api/workflow/execute
Content-Type: application/json
Authorization: Bearer <token>
```

**Request body:**

```json
{
    "user_message": "Execute security audit scripts in parallel across fleet",
    "workflow_id": null,
    "auto_approve": false
}
```

The `WorkflowExecutionRequest` Pydantic model accepts:

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `user_message` | `str` | required | Natural language description of the task |
| `workflow_id` | `str \| null` | `null` | Optional pre-assigned workflow ID |
| `auto_approve` | `bool` | `false` | Skip per-step approval gates |

**Response (lightweight routing):**

```json
{
    "success": true,
    "type": "lightweight_response",
    "result": "Response generated successfully",
    "routing_method": "lightweight_pattern_match"
}
```

**Response (complex workflow, currently gated):**

```json
{
    "success": false,
    "type": "complex_workflow_blocked",
    "result": "Complex workflow orchestration is temporarily disabled...",
    "complexity": "complex",
    "suggested_agents": ["system_commands", "orchestrator"]
}
```

**Response (full orchestration, when enabled):**

```json
{
    "success": true,
    "type": "workflow_orchestration",
    "workflow_id": "550e8400-e29b-41d4-a716-446655440000",
    "workflow_response": {
        "message_classification": "complex",
        "workflow_preview": [
            "System_Commands: Execute check_permissions.sh on frontend node",
            "System_Commands: Execute check_services.sh on NPU node",
            "System_Commands: Execute check_network.sh on AI Stack node",
            "Orchestrator: Aggregate audit results"
        ],
        "agents_involved": ["system_commands", "orchestrator"],
        "estimated_duration": "5 minutes",
        "user_approvals_needed": 0
    },
    "execution_started": true,
    "status_endpoint": "/api/workflow/550e8400-e29b-41d4-a716-446655440000/status"
}
```

### List Active Workflows

```http
GET /api/workflow/workflows
Authorization: Bearer <token>
```

Returns both Redis-persisted workflows (via `WorkflowStateMachine.list_active()`) and
legacy in-memory workflows, with Redis taking precedence on ID conflicts.

**Response:**

```json
{
    "success": true,
    "active_workflows": 2,
    "workflows": [
        {
            "workflow_id": "550e8400-...",
            "user_message": "Execute security audit scripts",
            "classification": "complex",
            "total_steps": 4,
            "current_step": 2,
            "status": "executing",
            "created_at": "2026-03-15T14:30:00",
            "estimated_duration": "5 minutes",
            "agents_involved": ["system_commands", "orchestrator"]
        }
    ]
}
```

### Get Workflow Status

```http
GET /api/workflow/workflow/{workflow_id}/status
Authorization: Bearer <token>
```

**Response:**

```json
{
    "success": true,
    "workflow_id": "550e8400-...",
    "status": "executing",
    "current_step": 2,
    "total_steps": 4,
    "progress": 0.5,
    "current_step_info": {
        "step_id": "step_2",
        "description": "System_Commands: Execute check_services.sh on NPU node",
        "status": "in_progress",
        "agent_type": "system_commands",
        "action": "execute_shell",
        "started_at": "2026-03-15T14:30:05"
    },
    "estimated_remaining": "2 minutes"
}
```

### Approve Workflow Step

```http
POST /api/workflow/workflow/{workflow_id}/approve
Content-Type: application/json
Authorization: Bearer <token>
```

**Request body:**

```json
{
    "workflow_id": "550e8400-...",
    "step_id": "step_3",
    "approved": true,
    "user_input": null,
    "timestamp": 1710511800.0
}
```

**Response:**

```json
{
    "success": true,
    "message": "Workflow step approved",
    "next_action": "continue_execution"
}
```

### Get Pending Approvals

```http
GET /api/workflow/workflow/{workflow_id}/pending_approvals
Authorization: Bearer <token>
```

**Response:**

```json
{
    "success": true,
    "workflow_id": "550e8400-...",
    "pending_approvals": [
        {
            "step_id": "generate_report",
            "description": "Orchestrator: Generate Audit Report",
            "agent_type": "orchestrator",
            "action": "Generate comprehensive security audit report",
            "context": {}
        }
    ]
}
```

### Cancel Workflow

```http
DELETE /api/workflow/workflow/{workflow_id}
Authorization: Bearer <token>
```

**Response:**

```json
{
    "success": true,
    "message": "Workflow cancelled successfully"
}
```

Cancellation sets workflow status to `cancelled`, cancels any pending approval futures,
and publishes a `workflow_cancelled` event.

---

## 5. Parallel Execution Engine

### Execution Strategies

The `ExecutionStrategyHandler` in
`autobot-backend/enhanced_orchestration/execution_strategies.py` implements five
strategies:

| Strategy | Behavior |
|----------|----------|
| `SEQUENTIAL` | Topologically sort tasks, execute one at a time |
| `PARALLEL` | Start all tasks with satisfied dependencies concurrently |
| `PIPELINE` | Group into stages; each stage runs in parallel, output feeds next |
| `COLLABORATIVE` | All tasks run with inter-agent communication channels |
| `ADAPTIVE` | Start parallel, fall back to sequential on high failure rate (>30%) |

For fleet-wide parallel script execution, the `PARALLEL` strategy is the correct
choice.

### How Parallel Execution Works

The `execute_parallel` method manages a work queue with dependency checking:

```python
async def execute_parallel(self, plan: WorkflowPlan) -> Dict[str, Any]:
    """Execute independent tasks in parallel."""
    results = {}
    pending_tasks = list(plan.tasks)
    running_tasks = []

    while pending_tasks or running_tasks:
        # Find tasks whose dependencies are all satisfied
        ready_tasks = [
            task for task in pending_tasks
            if self._dependencies_met(task, results)
        ]
        for task in ready_tasks:
            pending_tasks.remove(task)

        # Start ready tasks up to max_parallel_tasks limit
        for task in ready_tasks:
            if len(running_tasks) < self.max_parallel_tasks:
                task_future = asyncio.create_task(
                    self._execute_single_task(task, results)
                )
                running_tasks.append((task, task_future))

        # Wait for any task to complete
        if running_tasks:
            done, _ = await asyncio.wait(
                [future for _, future in running_tasks],
                return_when=asyncio.FIRST_COMPLETED,
            )
            for task, future in running_tasks[:]:
                if future in done:
                    result = await future
                    results[task.task_id] = result
                    running_tasks.remove((task, future))

    return results
```

**Key behaviors:**

1. Tasks with no dependencies (or whose dependencies are already in `results`) are
   immediately eligible to run.
2. Concurrency is bounded by `max_parallel_tasks` (configurable, enforced by an
   `asyncio.Semaphore`).
3. `asyncio.wait` with `FIRST_COMPLETED` allows the engine to start new tasks as
   soon as a slot opens, without waiting for the entire batch.
4. The dependency check is simple: every ID in `task.dependencies` must be a key in
   `results` with `status == "completed"`.

### ParallelToolExecutor (Lower-Level)

For tool-level parallelism (used by the agent loop), the `ParallelToolExecutor` in
`autobot-backend/tools/parallel/executor.py` provides automatic dependency analysis
and group-based execution:

```python
from tools.parallel.executor import ParallelToolExecutor, ParallelExecutorConfig
from tools.parallel.types import ToolCall

config = ParallelExecutorConfig(
    max_parallel_calls=10,      # Maximum concurrent tool calls
    per_call_timeout_ms=30000,  # 30s per call
    group_timeout_ms=60000,     # 60s per group
    retry_failed=True,          # Auto-retry failed calls
    max_retries=2,              # Up to 2 retries
    collect_metrics=True,       # Track speedup metrics
)

executor = ParallelToolExecutor(
    tool_dispatcher=my_dispatch_function,
    event_stream=event_stream,
    config=config,
)

# Create tool calls for parallel execution
calls = [
    ToolCall(tool_name="execute_shell", arguments={
        "host": "172.16.168.21",
        "command": "/opt/autobot/scripts/audit/check_permissions.sh",
    }),
    ToolCall(tool_name="execute_shell", arguments={
        "host": "172.16.168.22",
        "command": "/opt/autobot/scripts/audit/check_services.sh",
    }),
    ToolCall(tool_name="execute_shell", arguments={
        "host": "172.16.168.24",
        "command": "/opt/autobot/scripts/audit/check_network.sh",
    }),
]

# Execute -- dependency analyzer will place all three in one parallel group
results = await executor.execute_batch(calls, task_id="fleet-audit-001")
```

The `DependencyAnalyzer` examines each call's `depends_on` list and groups independent
calls together. The executor reports `ExecutionMetrics` including:

- `total_calls`: Number of tool calls executed
- `parallel_groups`: Number of dependency-separated groups
- `sequential_time_ms`: Sum of individual execution times (what sequential would cost)
- `parallel_time_ms`: Actual wall-clock time
- `speedup_factor`: `sequential_time_ms / parallel_time_ms` (typically 3-5x)

### Executing on Remote Fleet Nodes

Each fleet node is accessible via SSH with the `autobot` user. The step executor
connects to `target_node` and runs the command:

```python
async def execute_step_on_target(
    step: Dict[str, Any],
    context: Dict[str, Any],
) -> Dict[str, Any]:
    """Execute a shell command on a remote fleet node.

    Args:
        step: Step definition with target_node, command, and timeout.
        context: Workflow context with credentials and environment.

    Returns:
        Dict with stdout, stderr, and exit_code.
    """
    import asyncssh

    target = step["inputs"]["target_host"]
    command = step["inputs"]["script"]
    timeout = step.get("timeout", 300)

    async with asyncssh.connect(
        target,
        username="autobot",
        known_hosts=None,
    ) as conn:
        result = await asyncio.wait_for(
            conn.run(command, check=True),
            timeout=timeout,
        )
        return {
            "stdout": result.stdout,
            "stderr": result.stderr,
            "exit_code": result.exit_status,
            "target_node": target,
        }
```

**Fleet node reference:**

| IP | Role | Typical Audit Scripts |
|----|------|-----------------------|
| 172.16.168.21 | Frontend VM | `check_permissions.sh`, `check_nginx.sh` |
| 172.16.168.22 | NPU VM | `check_services.sh`, `check_npu_health.sh` |
| 172.16.168.23 | Redis VM | `check_redis.sh`, `check_memory.sh` |
| 172.16.168.24 | AI Stack VM | `check_network.sh`, `check_gpu.sh` |
| 172.16.168.25 | Browser VM | `check_playwright.sh`, `check_vnc.sh` |
| 172.16.168.19 | SLM Server | `check_slm.sh`, `check_celery.sh` |

---

## 6. Fleet-Wide Execution via SLM

For operations that span the entire fleet, the SLM (Server Lifecycle Manager) on
`.19` provides a centralized execution API. The SLM handles node discovery, health
checking, and rolling/parallel execution strategies.

### Authenticating with the SLM

```python
import aiohttp

from autobot_shared.ssot_config import config

SLM_URL = f"https://{config.vm.slm}:{config.port.backend}"

async def get_slm_token() -> str:
    """Authenticate with the SLM and return a Bearer token."""
    async with aiohttp.ClientSession() as session:
        response = await session.post(
            f"{SLM_URL}/api/auth/login",
            json={"username": "admin", "password": "..."},
            ssl=False,
        )
        data = await response.json()
        return data["access_token"]
```

### Executing Scripts Across the Fleet

```python
async def execute_script_on_fleet(
    script_path: str,
    target_group: str = "all",
    parallel: bool = True,
    batch_size: int = 1,
) -> dict:
    """Execute a script across fleet nodes via SLM.

    Args:
        script_path: Absolute path to the script on target nodes.
        target_group: Node group to target ('all', 'frontend', 'ai-stack', etc.).
        parallel: If True, execute on all nodes concurrently.
            If False, use rolling execution with batch_size.
        batch_size: Number of nodes to update simultaneously in rolling mode.
            Use batch_size=1 to avoid git index.lock races during code sync.

    Returns:
        SLM execution response with per-node results.
    """
    token = await get_slm_token()
    headers = {"Authorization": f"Bearer {token}"}

    async with aiohttp.ClientSession() as session:
        response = await session.post(
            f"{SLM_URL}/api/execute/script",
            json={
                "script_path": script_path,
                "target_group": target_group,
                "execution_mode": "parallel" if parallel else "sequential",
                "batch_size": batch_size,
                "timeout": 300,
            },
            headers=headers,
            ssl=False,
        )
        return await response.json()
```

### Combining SLM Fleet Execution with Workflow Steps

A workflow can include SLM fleet execution as a step:

```python
WorkflowStep(
    id="fleet_audit",
    agent_type="system_commands",
    action="Execute fleet-wide audit via SLM",
    description="System_Commands: Fleet Audit via SLM API",
    inputs={
        "use_slm": True,
        "script_path": "/opt/autobot/scripts/audit/full_audit.sh",
        "target_group": "all",
        "execution_mode": "parallel",
    },
    expected_duration_ms=60000,
),
```

---

## 7. Visual Workflow Builder (Frontend)

### Architecture

The workflow builder frontend is composed of:

- **View**: `WorkflowBuilderView.vue` -- Top-level layout with sidebar navigation
- **Composable**: `useWorkflowBuilder.ts` -- Reactive state, API calls, WebSocket
  connection for live updates
- **Canvas**: `WorkflowCanvas.vue` -- Interactive node/edge editor
- **Runner**: `WorkflowRunner.vue` -- Execution controls and live progress
- **Templates**: `WorkflowTemplateGallery.vue` -- Template browser
- **Support components**: `EditStepDialog.vue`, `RiskAssessment.vue`,
  `CommandPreview.vue`, `ApprovalGatePanel.vue`, `StepInfoHeader.vue`,
  `WorkflowStepsList.vue`, `AdvancedOptionsPanel.vue`, `OrchestrationVisualizer.vue`,
  `WorkflowHistory.vue`, `WorkflowProgressWidget.vue`

### TypeScript Type Definitions

From `useWorkflowBuilder.ts`:

```typescript
type WorkflowStepStatus =
  | 'pending' | 'waiting_approval' | 'approved' | 'executing'
  | 'completed' | 'skipped' | 'failed' | 'paused';

type ExecutionStrategy =
  | 'sequential' | 'parallel' | 'pipeline'
  | 'collaborative' | 'adaptive';

type RiskLevel = 'low' | 'medium' | 'high' | 'critical';

interface WorkflowStep {
  step_id: string;
  command: string;
  description: string;
  explanation?: string;
  requires_confirmation: boolean;
  risk_level: RiskLevel;
  estimated_duration: number;
  dependencies?: string[];
  status: WorkflowStepStatus;
  execution_result?: Record<string, unknown>;
  started_at?: string;
  completed_at?: string;
}
```

### Creating a Parallel Workflow in the Canvas

The `WorkflowCanvas.vue` component manages an array of `nodes` and `connections`:

```typescript
// Nodes represent workflow steps
interface CanvasNode {
  id: string;
  type: 'step' | 'condition';
  position: { x: number; y: number };
  data: {
    description: string;
    command: string;
    risk_level: RiskLevel;
    requires_confirmation: boolean;
  };
}

// Connections represent dependencies (from -> to means "to" depends on "from")
interface CanvasConnection {
  id: string;
  from: string;  // Source node ID
  to: string;    // Target node ID
  path: string;  // SVG path data
}
```

When saved, the canvas converts nodes to `WorkflowStep` objects. Nodes with no
incoming connections and no edges between them become parallel candidates. The backend
groups them by analyzing the dependency graph.

### Step Interaction

Each canvas node provides:

- **Description field**: Free-text description of what the step does
- **Command field**: The actual shell command to execute (monospace font)
- **Risk level dropdown**: `low`, `medium`, or `high`
- **Confirmation checkbox**: Whether the step requires user approval before execution
- **Input port** (top): For incoming dependency edges
- **Output port** (bottom): For outgoing dependency edges
- **Delete button**: Remove the node and its connections

### Canvas Controls

| Control | Action |
|---------|--------|
| **Add Step** | Create a new step node at default position |
| **Add Condition** | Create a branching condition node |
| **Clear** | Remove all nodes and connections |
| **Auto Layout** | Automatically arrange nodes in a readable layout |
| **Zoom In/Out** | Scale the canvas view |
| **Reset Zoom** | Return to default zoom level |
| **Save** | Persist the workflow definition to the backend |
| **Pan** | Click and drag on empty canvas area to pan |

### Real-Time Execution Display

The `WorkflowRunner.vue` and `WorkflowProgressWidget.vue` components display live
execution status. Steps transition through visual states:

| Status | Display |
|--------|---------|
| `pending` | Gray, waiting indicator |
| `waiting_approval` | Yellow, pulsing border, approval buttons shown |
| `executing` | Blue, spinner animation |
| `completed` | Green, checkmark icon |
| `failed` | Red, error icon with message |
| `skipped` | Gray with strikethrough |

For parallel steps, multiple nodes show the `executing` state simultaneously, giving
visual confirmation that concurrent execution is in progress.

---

## 8. Workflow Templates

Pre-built templates are organized by category. Each template defines a complete
workflow with steps, dependencies, agent assignments, and duration estimates.

### Template Categories

| Category | Module | Templates |
|----------|--------|-----------|
| Security | `workflow_templates/security.py` | Network Security Scan, Vulnerability Assessment, Security Audit |
| System Admin | `workflow_templates/sysadmin.py` | System Health Check, Performance Optimization, Backup and Recovery |
| Research | `workflow_templates/research.py` | Research workflows |
| Development | `workflow_templates/development.py` | Development workflows |
| Analysis | `workflow_templates/analysis.py` | Analysis workflows |
| Community | `workflow_templates/community.py` | Community-contributed templates |

### Example: Security Audit Template (with parallel steps)

The security audit template in `workflow_templates/security.py` demonstrates parallel
step dependencies. Notice that `compliance_research` and `asset_discovery` both depend
only on `audit_planning` and not on each other, making them candidates for parallel
execution:

```python
# From _create_audit_planning_steps():
WorkflowStep(
    id="audit_planning",
    agent_type="orchestrator",
    action="Plan security audit scope and methodology",
    description="Orchestrator: Audit Planning (requires your approval)",
    requires_approval=True,
),
WorkflowStep(
    id="compliance_research",
    agent_type="research",
    action="Research compliance requirements and security standards",
    description="Research: Compliance Standards",
    dependencies=["audit_planning"],       # Only depends on audit_planning
),
WorkflowStep(
    id="asset_discovery",
    agent_type="network_discovery",
    action="Discover and inventory all network assets",
    description="Network_Discovery: Asset Inventory",
    dependencies=["audit_planning"],       # Only depends on audit_planning
    inputs={"task_type": "asset_inventory"},
),
# compliance_check depends on BOTH, creating a fan-in:
WorkflowStep(
    id="compliance_check",
    agent_type="security_scanner",
    action="Verify compliance with security standards",
    description="Security_Scanner: Compliance Verification",
    dependencies=["compliance_research", "security_scanning"],
),
```

The dependency graph for this template:

```
audit_planning
    |
    +---> compliance_research ---+
    |                            |
    +---> asset_discovery -----> security_scanning ---> compliance_check
```

Steps `compliance_research` and `asset_discovery` can execute in parallel after
`audit_planning` completes.

### Parallel Fleet Template Example

A template for fleet-wide parallel updates:

```python
from workflow_templates.types import (
    TemplateCategory, WorkflowStep, WorkflowTemplate,
)
from autobot_types import TaskComplexity

fleet_update_template = WorkflowTemplate(
    id="fleet_system_update",
    name="Fleet-Wide System Update",
    description="Run apt update and upgrade across all fleet nodes in parallel",
    category=TemplateCategory.SYSTEM_ADMIN,
    complexity=TaskComplexity.COMPLEX,
    estimated_duration_minutes=30,
    agents_involved=["system_commands", "orchestrator"],
    tags=["fleet", "update", "parallel", "system"],
    variables={
        "target_group": "Node group to update (all, frontend, ai-stack)",
    },
    steps=[
        # Phase 1: Update package lists (parallel across all nodes)
        WorkflowStep(
            id="update_frontend",
            agent_type="system_commands",
            action="apt update on frontend node",
            description="System_Commands: apt update (.21)",
            inputs={"target_host": "172.16.168.21", "cmd": "sudo apt update"},
        ),
        WorkflowStep(
            id="update_npu",
            agent_type="system_commands",
            action="apt update on NPU node",
            description="System_Commands: apt update (.22)",
            inputs={"target_host": "172.16.168.22", "cmd": "sudo apt update"},
        ),
        WorkflowStep(
            id="update_ai_stack",
            agent_type="system_commands",
            action="apt update on AI Stack node",
            description="System_Commands: apt update (.24)",
            inputs={"target_host": "172.16.168.24", "cmd": "sudo apt update"},
        ),
        # Phase 2: Upgrade packages (parallel, depends on update phase)
        WorkflowStep(
            id="upgrade_frontend",
            agent_type="system_commands",
            action="apt upgrade on frontend node",
            description="System_Commands: apt upgrade (.21)",
            dependencies=["update_frontend"],
            requires_approval=True,
            inputs={"target_host": "172.16.168.21", "cmd": "sudo apt upgrade -y"},
        ),
        WorkflowStep(
            id="upgrade_npu",
            agent_type="system_commands",
            action="apt upgrade on NPU node",
            description="System_Commands: apt upgrade (.22)",
            dependencies=["update_npu"],
            requires_approval=True,
            inputs={"target_host": "172.16.168.22", "cmd": "sudo apt upgrade -y"},
        ),
        WorkflowStep(
            id="upgrade_ai_stack",
            agent_type="system_commands",
            action="apt upgrade on AI Stack node",
            description="System_Commands: apt upgrade (.24)",
            dependencies=["update_ai_stack"],
            requires_approval=True,
            inputs={"target_host": "172.16.168.24", "cmd": "sudo apt upgrade -y"},
        ),
        # Phase 3: Verify services (after all upgrades)
        WorkflowStep(
            id="verify_services",
            agent_type="orchestrator",
            action="Verify all services are running after upgrade",
            description="Orchestrator: Service Verification",
            dependencies=[
                "upgrade_frontend",
                "upgrade_npu",
                "upgrade_ai_stack",
            ],
        ),
    ],
)
```

Dependency graph:

```
update_frontend -----> upgrade_frontend --------+
                                                |
update_npu ----------> upgrade_npu ------------>+--> verify_services
                                                |
update_ai_stack -----> upgrade_ai_stack --------+
```

All three `update_*` steps run in parallel (no dependencies). Each `upgrade_*` step
depends only on its corresponding `update_*` step, so all three upgrades also run in
parallel once their respective updates complete. The final `verify_services` step waits
for all three upgrades.

---

## 9. Monitoring Parallel Execution

### WebSocket Live Events

The backend publishes workflow events via the `event_manager`. These are forwarded to
connected WebSocket clients. The frontend composable `useWorkflowBuilder.ts` establishes
a WebSocket connection to receive live updates:

```typescript
import { getBackendWsUrl } from '@/config/ssot-config';
import { getAuthToken } from '@/utils/fetchWithAuth';

function connectWorkflowWebSocket(workflowId: string) {
    const wsUrl = getBackendWsUrl();
    const token = getAuthToken();
    const ws = new WebSocket(`${wsUrl}/api/ws?token=${token}`);

    ws.onmessage = (event: MessageEvent) => {
        const data = JSON.parse(event.data);

        switch (data.type) {
            case 'workflow_step_started':
                // A step has begun execution
                // data.step_id, data.step_index, data.total_steps
                updateStepStatus(data.step_id, 'executing');
                break;

            case 'workflow_step_completed':
                // A step finished successfully
                // data.step_id, data.result
                updateStepStatus(data.step_id, 'completed');
                break;

            case 'step_confirmation_required':
                // A step needs user approval
                // data.step_id, data.step_data
                showApprovalDialog(data.step_id, data.step_data);
                break;

            case 'step_failed':
                // A step failed
                // data.step_id, data.error
                updateStepStatus(data.step_id, 'failed');
                showErrorNotification(data.error);
                break;

            case 'workflow_completed':
                // All steps finished
                // data.workflow_id, data.total_steps, data.completed_steps
                markWorkflowComplete(data);
                break;

            case 'workflow_cancelled':
                // Workflow was cancelled
                markWorkflowCancelled(data.workflow_id);
                break;

            case 'workflow_plan_presented':
                // Plan approval requested (Issue #390)
                // data.plan, data.approval_options
                showPlanApprovalDialog(data.plan, data.approval_options);
                break;

            case 'step_rejected_by_judge':
                // LLM judge rejected a step
                // data.reason, data.suggestions
                showJudgeRejection(data.step_id, data.reason);
                break;
        }
    };

    return ws;
}
```

### Event Types Reference

| Event Type | Published When | Key Fields |
|-----------|----------------|------------|
| `workflow_step_started` | Step begins executing | `workflow_id`, `step_id`, `step_index`, `total_steps` |
| `workflow_step_completed` | Step finishes successfully | `workflow_id`, `step_id`, `result` |
| `workflow_approval_required` | Step needs user approval | `workflow_id`, `step_id`, `description`, `context` |
| `step_confirmation_required` | Step confirmation prompt | `workflow_id`, `step_id`, `step_data` |
| `workflow_completed` | All steps done | `workflow_id`, `total_steps`, `execution_time` |
| `workflow_failed` | Workflow error | `workflow_id`, `error`, `current_step` |
| `workflow_cancelled` | User cancels workflow | `workflow_id`, `user_message` |
| `workflow_approval` | Step approved/denied | `workflow_id`, `step_id`, `approved` |
| `workflow_plan_presented` | Plan shown for approval (#390) | `workflow_id`, `plan`, `approval_options` |
| `step_rejected_by_judge` | LLM judge blocks a step | `workflow_id`, `step_id`, `reason`, `suggestions` |
| `step_failed` | Individual step failure | `workflow_id`, `step_id`, `error` |

### Prometheus Metrics

Workflow execution is tracked via `PrometheusMetricsManager`:

```python
from monitoring.prometheus_metrics import get_metrics_manager

metrics = get_metrics_manager()

# Record workflow execution completion
metrics.record_workflow_execution(
    workflow_type="parallel_fleet_audit",
    status="success",
    duration=45.2,
)

# Record individual step completion
metrics.record_workflow_step(
    workflow_type="parallel_fleet_audit",
    step_type="system_commands",
    status="completed",
)

# Track active workflow count
metrics.update_active_workflows(
    workflow_type="parallel_fleet_audit",
    count=1,
)

# Record user approval decision
metrics.record_workflow_approval(
    workflow_type="parallel_fleet_audit",
    decision="approved",
)
```

### Execution Metrics for Parallel Runs

The `ParallelToolExecutor` logs speedup metrics after each batch:

```
INFO: Parallel execution complete: 12543.2ms (sequential would be 35291.8ms, speedup: 2.81x)
```

The `ExecutionMetrics` dataclass provides programmatic access:

```python
metrics = ExecutionMetrics(
    total_calls=3,
    parallel_groups=1,          # All 3 calls in one group
    sequential_calls=0,         # None required sequential execution
    total_time_ms=12543.2,
    sequential_time_ms=35291.8,
    parallel_time_ms=12543.2,
    speedup_factor=2.81,        # 2.81x faster than sequential
)
```

---

## 10. Error Handling and Recovery

### Timeout Handling

Timeouts are enforced at three levels:

| Level | Default | Configuration |
|-------|---------|---------------|
| Per-call | 30s | `ParallelExecutorConfig.per_call_timeout_ms` |
| Per-group | 60s | `ParallelExecutorConfig.group_timeout_ms` |
| Per-step | 300s | `WorkflowStep.timeout` or `estimated_duration` |

When a timeout occurs in a parallel group, the executor marks timed-out calls as
`failed` with error `"Timeout"` and returns partial results:

```python
try:
    group_results = await asyncio.wait_for(
        asyncio.gather(*tasks, return_exceptions=True),
        timeout=self.config.group_timeout_ms / 1000,
    )
except asyncio.TimeoutError:
    for call in group:
        if call.status == "running":
            call.status = "failed"
            call.error = "Timeout"
            results[call.call_id] = {"error": "Timeout"}
```

### Partial Failure Strategies

The system supports several responses to partial failures:

**Continue on failure (default for optional steps):**

If a step is marked as optional (`task.metadata.get("optional", False)`), the
sequential executor continues to the next step even after failure.

**Abort on required step failure:**

If a required step fails in the sequential strategy, execution stops:

```python
if result.get("status") == "failed" and not task.metadata.get("optional", False):
    logger.error("Required task %s failed, stopping workflow", task.task_id)
    break
```

**Automatic retry:**

The `ParallelToolExecutor` retries failed calls up to `max_retries` (default 2) when
`retry_failed=True`:

```python
if self.config.retry_failed:
    retry_result = await self._retry_call(call, task_id)
    if retry_result is not None:
        results[call.call_id] = retry_result
```

**Adaptive strategy fallback:**

The `ADAPTIVE` execution strategy monitors progress and failure ratios. If the failure
rate exceeds 30%, it automatically switches from parallel to sequential execution:

```python
def _adapt_strategy(self, progress_ratio, failure_ratio, current):
    if failure_ratio > 0.3:
        return ExecutionStrategy.SEQUENTIAL
    if progress_ratio > 0.7 and failure_ratio < 0.1:
        return ExecutionStrategy.PARALLEL
    return current
```

### Result Aggregation from Parallel Executions

After parallel steps complete, the aggregation step receives all results via the
execution context:

```python
async def _execute_coordinated_step(self, step, execution_context, context):
    """Execute a step with access to all prior step results."""
    # execution_context["step_results"] contains:
    # {
    #     "audit_frontend": {"success": True, "result": {...}},
    #     "audit_npu": {"success": True, "result": {...}},
    #     "audit_ai_stack": {"success": False, "error": "Connection timeout"},
    # }
    pass
```

The orchestrator aggregation step can then build a combined report:

```python
# In the aggregate_results step handler:
all_results = execution_context["step_results"]
successful = {k: v for k, v in all_results.items() if v.get("success")}
failed = {k: v for k, v in all_results.items() if not v.get("success")}

report = {
    "total_nodes": len(all_results),
    "successful": len(successful),
    "failed": len(failed),
    "details": all_results,
    "failures": {k: v.get("error") for k, v in failed.items()},
}
```

### Workflow State Recovery

Workflow state is persisted to Redis via `WorkflowStateMachine`. On backend restart,
active workflows can be recovered:

```python
sm = get_workflow_state_machine()

# List all active (non-completed) workflows
active = await sm.list_active()
for state in active:
    if state.current_step == "executing":
        # Resume or mark as failed depending on policy
        await sm.fail(state.workflow_id, "Backend restart during execution")
```

Completed workflows are retained in Redis for 7 days (`COMPLETED_TTL = 7 * 24 * 3600`)
before automatic expiration.

### Plan Approval System

The plan approval system (Issue #390) adds a safety gate before execution:

1. Backend calls `present_plan_for_approval()` which sends a
   `workflow_plan_presented` WebSocket event to the frontend.
2. The frontend displays the plan with four options: approve all, step-by-step review,
   modify, or reject.
3. The backend waits via `wait_for_plan_approval()` with a configurable timeout
   (default 300s, max 3600s).
4. On timeout, the approval status becomes `TIMEOUT` and execution does not proceed.

Approval modes defined in `PlanApprovalMode`:

| Mode | Behavior |
|------|----------|
| `FULL_PLAN_APPROVAL` | Approve entire plan at once (currently implemented) |
| `PER_STEP_APPROVAL` | Approve each step individually (planned) |
| `HYBRID_APPROVAL` | Approve plan + critical steps separately (planned) |
| `AUTO_SAFE_STEPS` | Auto-approve low-risk, ask for high-risk (planned) |

---

## Complete Example: Three Parallel Shell Scripts Across the Fleet

This end-to-end example ties together all concepts. It defines a workflow that executes
three shell scripts in parallel across three fleet nodes, waits for all three to
complete, and then aggregates the results into a report.

### Step 1: Define the Workflow

```python
import asyncio
import aiohttp

from autobot_shared.ssot_config import config

BACKEND_URL = f"https://{config.vm.main}:{config.port.backend}"

workflow = {
    "user_message": "Run security audit across frontend, NPU, and AI Stack nodes",
    "auto_approve": False,
    "workflow_template": {
        "name": "parallel_security_audit",
        "description": "Execute audit scripts on three fleet nodes in parallel",
        "steps": [
            {
                "id": "check_permissions",
                "agent_type": "system_commands",
                "action": "execute_shell",
                "parallel_group": "audit_wave_1",
                "timeout": 300,
                "inputs": {
                    "target_host": "172.16.168.21",
                    "script": "/opt/autobot/scripts/audit/check_permissions.sh",
                },
            },
            {
                "id": "check_services",
                "agent_type": "system_commands",
                "action": "execute_shell",
                "parallel_group": "audit_wave_1",
                "timeout": 300,
                "inputs": {
                    "target_host": "172.16.168.22",
                    "script": "/opt/autobot/scripts/audit/check_services.sh",
                },
            },
            {
                "id": "check_network",
                "agent_type": "system_commands",
                "action": "execute_shell",
                "parallel_group": "audit_wave_1",
                "timeout": 300,
                "inputs": {
                    "target_host": "172.16.168.24",
                    "script": "/opt/autobot/scripts/audit/check_network.sh",
                },
            },
            {
                "id": "aggregate_report",
                "agent_type": "orchestrator",
                "action": "aggregate_results",
                "dependencies": [
                    "check_permissions",
                    "check_services",
                    "check_network",
                ],
                "user_approval_required": True,
                "inputs": {"report_format": "markdown"},
            },
        ],
    },
}
```

### Step 2: Submit the Workflow

```python
async def submit_workflow():
    async with aiohttp.ClientSession() as session:
        resp = await session.post(
            f"{BACKEND_URL}/api/workflow/execute",
            json=workflow,
            ssl=False,
        )
        result = await resp.json()
        workflow_id = result.get("workflow_id")
        print(f"Workflow submitted: {workflow_id}")
        return workflow_id
```

### Step 3: Monitor Execution

```python
async def poll_status(workflow_id: str):
    async with aiohttp.ClientSession() as session:
        while True:
            resp = await session.get(
                f"{BACKEND_URL}/api/workflow/workflow/{workflow_id}/status",
                ssl=False,
            )
            status = await resp.json()

            progress = status.get("progress", 0)
            current = status.get("current_step_info", {})
            print(
                f"Progress: {progress:.0%} | "
                f"Step: {current.get('description', 'N/A')} | "
                f"Status: {current.get('status', 'N/A')}"
            )

            if status.get("status") in ("completed", "failed", "cancelled"):
                break

            await asyncio.sleep(2)
```

### Step 4: Approve the Aggregation Step

```python
async def approve_report(workflow_id: str):
    async with aiohttp.ClientSession() as session:
        resp = await session.post(
            f"{BACKEND_URL}/api/workflow/workflow/{workflow_id}/approve",
            json={
                "workflow_id": workflow_id,
                "step_id": "aggregate_report",
                "approved": True,
                "user_input": None,
                "timestamp": 1710511800.0,
            },
            ssl=False,
        )
        return await resp.json()
```

### Execution Timeline

```
T+0.0s   Workflow submitted
T+0.1s   Execution engine groups steps by dependencies
         - Group 1 (parallel): check_permissions, check_services, check_network
         - Group 2 (sequential after group 1): aggregate_report

T+0.2s   Three SSH connections opened concurrently:
         - .21: /opt/autobot/scripts/audit/check_permissions.sh  [RUNNING]
         - .22: /opt/autobot/scripts/audit/check_services.sh     [RUNNING]
         - .24: /opt/autobot/scripts/audit/check_network.sh      [RUNNING]

T+12.3s  check_services completes (fastest node)
T+18.7s  check_permissions completes
T+23.1s  check_network completes (slowest node)

T+23.2s  All dependencies for aggregate_report satisfied
         aggregate_report enters waiting_approval state
         WebSocket event: step_confirmation_required

T+25.0s  User approves via UI or API call
         aggregate_report enters executing state

T+26.5s  aggregate_report completes
         WebSocket event: workflow_completed

         Total wall-clock time: 26.5s
         Sequential equivalent: ~55s (check_permissions 18.7s + check_services 12.3s
                                      + check_network 23.1s + aggregate 1.5s)
         Speedup factor: 2.08x
```
