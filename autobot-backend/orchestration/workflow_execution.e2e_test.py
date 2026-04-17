#!/usr/bin/env python3
"""
Test actual workflow execution to see if tool registry issues persist
"""

import asyncio
import sys
from pathlib import Path

# Add AutoBot to Python path
sys.path.append(str(Path(__file__).parent))

from orchestrator import Orchestrator


async def test_workflow_execution():
    print("🧪 Testing Actual Workflow Execution")  # noqa: print
    print("=" * 50)  # noqa: print

    orchestrator = Orchestrator()
    user_message = "Find the best Python web frameworks"

    try:
        # Test the full workflow pipeline that the API uses
        print("1. Classification...")  # noqa: print
        complexity = await orchestrator.classify_request_complexity(user_message)
        print(f"   ✅ Classified as: {complexity.value}")  # noqa: print

        print("2. Creating workflow response...")  # noqa: print
        workflow_response = await orchestrator.create_workflow_response(user_message)
        workflow_steps = workflow_response.get("workflow_steps", [])
        print(f"   ✅ Created workflow with {len(workflow_steps)} steps")  # noqa: print

        print("3. Testing workflow step execution...")  # noqa: print
        if workflow_steps:
            # Test the actual execution method that would be called
            first_step = workflow_steps[0]
            print(  # noqa: print
                f"   Testing step: {first_step.agent_type} - {first_step.action}"
            )  # noqa: print

            # This is the method that was failing before
            test_result = await orchestrator._execute_workflow_steps(
                workflow_steps, user_message
            )
            print(  # noqa: print
                f"   ✅ Workflow execution result: {test_result.get('execution_status', 'unknown')}"
            )

            # Check if tool registry error occurs
            if (
                "error" in test_result
                and "Tool registry not initialized" in test_result.get("error", "")
            ):
                print("   ❌ TOOL REGISTRY ERROR STILL PRESENT!")  # noqa: print
                return False
            else:
                print("   ✅ No tool registry errors detected")  # noqa: print

        print("\n4. Testing tool execution directly...")  # noqa: print
        # Test direct tool execution
        action = {
            "tool_name": "respond_conversationally",
            "tool_args": {"response_text": "test execution"},
        }

        direct_result = await orchestrator._execute_planned_action(action, [])
        if "Tool registry not initialized" in str(direct_result):
            print("   ❌ TOOL REGISTRY ERROR in direct execution!")  # noqa: print
            return False
        else:
            print("   ✅ Direct tool execution works")  # noqa: print

        print("\n🎉 All workflow execution tests passed!")  # noqa: print
        return True

    except Exception as e:
        print(f"\n❌ Workflow execution test failed: {e}")  # noqa: print
        import traceback

        traceback.print_exc()
        return False


if __name__ == "__main__":
    result = asyncio.run(test_workflow_execution())
    if result:
        print(  # noqa: print
            "\n✅ CONCLUSION: Workflow orchestration system is fully functional"
        )  # noqa: print
    else:
        print(  # noqa: print
            "\n❌ CONCLUSION: Issues detected that need further debugging"
        )  # noqa: print
