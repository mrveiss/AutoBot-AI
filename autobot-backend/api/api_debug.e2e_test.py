#!/usr/bin/env python3
"""
Debug the exact API workflow execution path
"""

import asyncio
import sys
from pathlib import Path

# Add AutoBot to Python path
sys.path.append(str(Path(__file__).parent))

from orchestrator import Orchestrator


async def test_api_workflow_execution():
    print("🌐 Testing API-style workflow execution...")  # noqa: print

    # Replicate the exact API workflow
    orchestrator = Orchestrator()
    user_message = "I need to scan my network for security vulnerabilities"

    print(  # noqa: print
        f"Initial tool registry check: {orchestrator.tool_registry is not None}"
    )  # noqa: print

    # Step 1: Check if should use workflow orchestration
    should_orchestrate = await orchestrator.should_use_workflow_orchestration(
        user_message
    )
    print(f"Should orchestrate: {should_orchestrate}")  # noqa: print

    if should_orchestrate:
        print("🔄 Using workflow orchestration...")  # noqa: print

        # Step 2: Create workflow response (this might be where issue occurs)
        print("🔄 About to create workflow response...")  # noqa: print
        workflow_response = await orchestrator.create_workflow_response(user_message)
        print(  # noqa: print
            f"Workflow response created: {workflow_response.get('message_classification', 'N/A')}"
        )
        print(  # noqa: print
            f"Response complexity: {workflow_response.get('request_complexity', 'N/A')}"
        )
        print(  # noqa: print
            f"Tool registry after workflow response: {orchestrator.tool_registry is not None}"
        )

        # Debug: Check workflow steps format
        workflow_steps = workflow_response.get("workflow_steps", [])
        print(f"Workflow steps type: {type(workflow_steps)}")  # noqa: print
        print(  # noqa: print
            f"Workflow steps length: {len(workflow_steps) if isinstance(workflow_steps, list) else 'N/A'}"
        )
        if workflow_steps:
            print(f"First workflow step type: {type(workflow_steps[0])}")  # noqa: print
            print(  # noqa: print
                f"First workflow step: {workflow_steps[0] if len(workflow_steps) > 0 else 'N/A'}"
            )

        # Step 3: Execute workflow steps (where the error occurs)
        try:
            execution_result = await orchestrator._execute_workflow_steps(
                workflow_steps, user_message
            )
            print(f"Workflow execution result: {execution_result}")  # noqa: print
        except Exception as e:
            print(f"Workflow execution failed: {e}")  # noqa: print
            import traceback

            traceback.print_exc()

    else:
        print("🔄 Using direct execution...")  # noqa: print
        result = await orchestrator.execute_goal(user_message)
        print(f"Direct execution result: {result}")  # noqa: print


if __name__ == "__main__":
    asyncio.run(test_api_workflow_execution())
