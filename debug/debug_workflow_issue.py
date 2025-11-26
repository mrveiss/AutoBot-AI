#!/usr/bin/env python3
"""
Debug the specific issue where plan_workflow_steps works in isolation
but fails when called through the API workflow
"""

import sys
import asyncio
from pathlib import Path

# Add AutoBot to Python path
sys.path.append(str(Path(__file__).parent))

from src.orchestrator import Orchestrator, TaskComplexity


async def debug_workflow_planning_issue():
    print("🔍 Debugging workflow planning issue...")

    orchestrator = Orchestrator()
    user_message = "I need to scan my network for security vulnerabilities"

    print("1. Direct test of plan_workflow_steps:")
    direct_steps = orchestrator.plan_workflow_steps(
        user_message, TaskComplexity.COMPLEX
    )
    print(f"   Direct call returned {len(direct_steps)} steps")

    print("2. Test through classify_request_complexity:")
    complexity = await orchestrator.classify_request_complexity(user_message)
    print(f"   Classification returned: {complexity}")

    print("3. Test plan_workflow_steps with classified complexity:")
    classified_steps = orchestrator.plan_workflow_steps(user_message, complexity)
    print(f"   With classified complexity: {len(classified_steps)} steps")

    print("4. Test should_use_workflow_orchestration:")
    should_orchestrate = await orchestrator.should_use_workflow_orchestration(
        user_message
    )
    print(f"   Should orchestrate: {should_orchestrate}")

    print("5. Test create_workflow_response (the problematic method):")
    try:
        workflow_response = await orchestrator.create_workflow_response(user_message)
        steps = workflow_response.get("workflow_steps", [])
        print(f"   create_workflow_response returned {len(steps)} steps")

        # Check if steps are the right type
        if steps:
            print(f"   First step type: {type(steps[0])}")
            if hasattr(steps[0], "id"):
                print(f"   First step ID: {steps[0].id}")
            else:
                print(f"   First step content: {steps[0]}")
    except Exception as e:
        print(f"   create_workflow_response failed: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(debug_workflow_planning_issue())
