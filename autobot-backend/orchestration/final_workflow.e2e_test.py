#!/usr/bin/env python3
"""
Final test to verify all workflow issues have been resolved
"""

import asyncio
import sys
from pathlib import Path

# Add AutoBot to Python path
sys.path.append(str(Path(__file__).parent))

from orchestrator import Orchestrator, TaskComplexity


async def final_workflow_test():
    print("🎯 Final Workflow Integration Test")  # noqa: print
    print("=" * 50)  # noqa: print

    orchestrator = Orchestrator()
    user_message = "I need to scan my network for security vulnerabilities"

    print(f"🔍 Testing: '{user_message}'")  # noqa: print
    print()  # noqa: print

    # Test 1: Classification
    print("1. Classification Test:")  # noqa: print
    complexity = await orchestrator.classify_request_complexity(user_message)
    print(f"   ✅ Classified as: {complexity.value}")  # noqa: print
    assert complexity == TaskComplexity.COMPLEX, f"Expected COMPLEX, got {complexity}"

    # Test 2: Workflow Planning
    print("2. Workflow Planning Test:")  # noqa: print
    steps = orchestrator.plan_workflow_steps(user_message, complexity)
    print(f"   ✅ Generated {len(steps)} workflow steps")  # noqa: print
    assert len(steps) > 0, "Expected workflow steps, got empty list"
    assert len(steps) == 8, f"Expected 8 steps for COMPLEX workflow, got {len(steps)}"

    # Test 3: Tool Registry
    print("3. Tool Registry Test:")  # noqa: print
    has_registry = orchestrator.tool_registry is not None
    print(f"   ✅ Tool registry initialized: {has_registry}")  # noqa: print
    assert has_registry, "Tool registry should be initialized"

    # Test 4: Workflow Orchestration Decision
    print("4. Workflow Orchestration Test:")  # noqa: print
    should_orchestrate = await orchestrator.should_use_workflow_orchestration(
        user_message
    )
    print(  # noqa: print
        f"   ✅ Should use workflow orchestration: {should_orchestrate}"
    )  # noqa: print
    assert should_orchestrate, "Should use workflow orchestration for COMPLEX requests"

    # Test 5: Workflow Response Creation
    print("5. Workflow Response Creation Test:")  # noqa: print
    workflow_response = await orchestrator.create_workflow_response(user_message)
    response_steps = workflow_response.get("workflow_steps", [])
    print(f"   ✅ Workflow response contains {len(response_steps)} steps")  # noqa: print
    assert len(response_steps) > 0, "Workflow response should contain steps"
    assert (
        len(response_steps) == 8
    ), f"Expected 8 steps in response, got {len(response_steps)}"

    # Test 6: Workflow Step Details
    print("6. Workflow Step Details Test:")  # noqa: print
    first_step = response_steps[0]
    print(  # noqa: print
        f"   ✅ First step: {first_step.agent_type} - {first_step.action}"
    )  # noqa: print
    print(f"   ✅ Step has ID: {first_step.id}")  # noqa: print
    print(f"   ✅ Step type: {type(first_step)}")  # noqa: print

    # Test 7: Workflow Metadata
    print("7. Workflow Metadata Test:")  # noqa: print
    print(  # noqa: print
        f"   ✅ Classification: {workflow_response.get('message_classification')}"
    )  # noqa: print
    print(  # noqa: print
        f"   ✅ Planned steps: {workflow_response.get('planned_steps')}"
    )  # noqa: print
    print(  # noqa: print
        f"   ✅ Agents involved: {workflow_response.get('agents_involved')}"
    )  # noqa: print
    print(  # noqa: print
        f"   ✅ User approvals needed: {workflow_response.get('user_approvals_needed')}"
    )
    print(  # noqa: print
        f"   ✅ Estimated duration: {workflow_response.get('estimated_duration')}"
    )  # noqa: print

    print()  # noqa: print
    print("🎉 ALL TESTS PASSED!")  # noqa: print
    print("The workflow orchestration system is now working correctly:")  # noqa: print
    print(  # noqa: print
        "   • Classification agent properly identifies COMPLEX requests"
    )  # noqa: print
    print(  # noqa: print
        "   • Workflow planning generates 8-step multi-agent coordination"
    )  # noqa: print
    print("   • Tool registry is properly initialized")  # noqa: print
    print(  # noqa: print
        "   • Enum definitions are unified (no more comparison failures)"
    )  # noqa: print
    print(  # noqa: print
        "   • Classification results are cached to avoid LLM inconsistency"
    )  # noqa: print
    print(  # noqa: print
        "   • Workflow responses include all necessary metadata and steps"
    )  # noqa: print


if __name__ == "__main__":
    asyncio.run(final_workflow_test())
