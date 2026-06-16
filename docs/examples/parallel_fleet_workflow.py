# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Parallel Fleet Workflow Example

Issue #3406: Demonstrates building a workflow definition that uses
``distributed_shell`` steps to run shell scripts across multiple fleet
nodes in parallel via the DAG executor.

Running this example
--------------------
Set the required environment variables then execute the script directly:

    export SLM_URL=https://<slm-host>
    export SLM_AUTH_TOKEN=<your-jwt>
    python docs/examples/parallel_fleet_workflow.py

The script builds an in-process WorkflowDAG and calls DAGExecutor
directly — it does not require a running AutoBot backend server.
"""

import asyncio
import logging
import os
import sys

# ---------------------------------------------------------------------------
# Path bootstrap — allows running from the repo root without install
# ---------------------------------------------------------------------------
_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
_BACKEND_DIR = os.path.join(_REPO_ROOT, "autobot-backend")
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

from orchestration.dag_executor import (  # noqa: E402
    DAGExecutionContext,
    DAGExecutor,
    DAGNode,
    WorkflowDAG,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Workflow definition
# ---------------------------------------------------------------------------

# Three fleet nodes to target (replace with real node IDs from your SLM).
TARGET_NODES = [
    os.getenv("DEMO_NODE_1", "node-001"),
    os.getenv("DEMO_NODE_2", "node-002"),
    os.getenv("DEMO_NODE_3", "node-003"),
]

WORKFLOW_NODES = [
    {
        "id": "collect-facts",
        "type": "distributed_shell",
        "data": {
            "nodes": TARGET_NODES,
            "script": "hostname && uname -r && df -h /",
            "language": "bash",
            "timeout": 60,
        },
    },
    {
        "id": "check-services",
        "type": "distributed_shell",
        "data": {
            "nodes": TARGET_NODES,
            "script": "systemctl is-active autobot-agent || true",
            "language": "bash",
            "timeout": 30,
        },
    },
    {
        "id": "report",
        "type": "distributed_shell",
        "data": {
            "nodes": TARGET_NODES,
            "script": 'echo "Fleet health check complete on $HOSTNAME"',
            "language": "bash",
            "timeout": 15,
        },
    },
]

WORKFLOW_EDGES = [
    {"source": "collect-facts", "target": "check-services"},
    {"source": "check-services", "target": "report"},
]


# ---------------------------------------------------------------------------
# Step executor callback (required by DAGExecutor for non-distributed steps)
# ---------------------------------------------------------------------------


async def _noop_step(node: DAGNode, ctx: DAGExecutionContext):
    """Fallback for any STEP nodes — not used in this example."""
    return {"success": True, "node_id": node.node_id}


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


async def run_workflow() -> None:
    dag = WorkflowDAG(WORKFLOW_NODES, WORKFLOW_EDGES)

    cycle = dag.detect_cycle()
    if cycle:
        logger.error("DAG has a cycle: %s", " -> ".join(cycle))
        return

    executor = DAGExecutor(step_executor_callback=_noop_step)
    logger.info("Starting parallel fleet workflow (3 steps, %d nodes each)", len(TARGET_NODES))
    ctx = await executor.execute(dag, workflow_id="fleet-health-check-demo")

    logger.info("Workflow finished: status=%s", ctx.status)

    for step_id, result in ctx.step_results.items():
        print(f"\n--- Step: {step_id} ---")
        print(f"  success: {result.get('success')}")
        print(f"  total_duration_ms: {result.get('total_duration_ms')}")
        for node_result in result.get("node_results", []):
            print(
                f"  [{node_result['node_id']}] exit={node_result['exit_code']} "
                f"stdout={node_result['stdout'][:120]!r}"
            )
        if result.get("failed_nodes"):
            print(f"  FAILED nodes: {result['failed_nodes']}")

    if ctx.error:
        logger.error("Workflow error: %s", ctx.error)
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(run_workflow())
