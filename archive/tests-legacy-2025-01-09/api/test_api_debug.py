#!/usr/bin/env python3
"""
Debug the exact API workflow execution path
"""

import sys
import asyncio
from pathlib import Path

# Add AutoBot to Python path
sys.path.append(str(Path(__file__).parent))

from src.orchestrator import Orchestrator


async def test_api_workflow_execution():
    print("🌐 Testing API-style workflow execution...")

    # Replicate the exact API workflow
    orchestrator = Orchestrator()
    user_message = "I need to scan my network for security vulnerabilities"

    print(f"Initial tool registry check: {orchestrator.tool_registry is not None}")

    # Step 1: Check if should use workflow orchestration
    should_orchestrate = await orchestrator.should_use_workflow_orchestration(
        user_message
    )
    print(f"Should orchestrate: {should_orchestrate}")

    if should_orchestrate:
        print("🔄 Using workflow orchestration...")

        # Step 2: Create workflow response (this might be where issue occurs)
        print("🔄 About to create workflow response...")
        workflow_response = await orchestrator.create_workflow_response(user_message)
        print(
            f"Workflow response created: {workflow_response.get('message_classification', 'N/A')}"
        )
        print(
            f"Response complexity: {workflow_response.get('request_complexity', 'N/A')}"
        )
        print(
            f"Tool registry after workflow response: {orchestrator.tool_registry is not None}"
        )

        # Debug: Check workflow steps format
        workflow_steps = workflow_response.get("workflow_steps", [])
        print(f"Workflow steps type: {type(workflow_steps)}")
        print(
            f"Workflow steps length: {len(workflow_steps) if isinstance(workflow_steps, list) else 'N/A'}"
        )
        if workflow_steps:
            print(f"First workflow step type: {type(workflow_steps[0])}")
            print(
                f"First workflow step: {workflow_steps[0] if len(workflow_steps) > 0 else 'N/A'}"
            )

        # Step 3: Execute workflow steps (where the error occurs)
        try:
            execution_result = await orchestrator._execute_workflow_steps(
                workflow_steps, user_message
            )
            print(f"Workflow execution result: {execution_result}")
        except Exception as e:
            print(f"Workflow execution failed: {e}")
            import traceback

            traceback.print_exc()

    else:
        print("🔄 Using direct execution...")
        result = await orchestrator.execute_goal(user_message)
        print(f"Direct execution result: {result}")


if __name__ == "__main__":
    asyncio.run(test_api_workflow_execution())
