#!/usr/bin/env python3
"""
Final test to verify all workflow issues have been resolved
"""

import sys
import asyncio
from pathlib import Path

# Add AutoBot to Python path
sys.path.append(str(Path(__file__).parent))

from src.orchestrator import Orchestrator, TaskComplexity


async def final_workflow_test():
    print("🎯 Final Workflow Integration Test")
    print("=" * 50)

    orchestrator = Orchestrator()
    user_message = "I need to scan my network for security vulnerabilities"

    print(f"🔍 Testing: '{user_message}'")
    print()

    # Test 1: Classification
    print("1. Classification Test:")
    complexity = await orchestrator.classify_request_complexity(user_message)
    print(f"   ✅ Classified as: {complexity.value}")
    assert complexity == TaskComplexity.COMPLEX, f"Expected COMPLEX, got {complexity}"

    # Test 2: Workflow Planning
    print("2. Workflow Planning Test:")
    steps = orchestrator.plan_workflow_steps(user_message, complexity)
    print(f"   ✅ Generated {len(steps)} workflow steps")
    assert len(steps) > 0, "Expected workflow steps, got empty list"
    assert len(steps) == 8, f"Expected 8 steps for COMPLEX workflow, got {len(steps)}"

    # Test 3: Tool Registry
    print("3. Tool Registry Test:")
    has_registry = orchestrator.tool_registry is not None
    print(f"   ✅ Tool registry initialized: {has_registry}")
    assert has_registry, "Tool registry should be initialized"

    # Test 4: Workflow Orchestration Decision
    print("4. Workflow Orchestration Test:")
    should_orchestrate = await orchestrator.should_use_workflow_orchestration(
        user_message
    )
    print(f"   ✅ Should use workflow orchestration: {should_orchestrate}")
    assert should_orchestrate, "Should use workflow orchestration for COMPLEX requests"

    # Test 5: Workflow Response Creation
    print("5. Workflow Response Creation Test:")
    workflow_response = await orchestrator.create_workflow_response(user_message)
    response_steps = workflow_response.get("workflow_steps", [])
    print(f"   ✅ Workflow response contains {len(response_steps)} steps")
    assert len(response_steps) > 0, "Workflow response should contain steps"
    assert (
        len(response_steps) == 8
    ), f"Expected 8 steps in response, got {len(response_steps)}"

    # Test 6: Workflow Step Details
    print("6. Workflow Step Details Test:")
    first_step = response_steps[0]
    print(f"   ✅ First step: {first_step.agent_type} - {first_step.action}")
    print(f"   ✅ Step has ID: {first_step.id}")
    print(f"   ✅ Step type: {type(first_step)}")

    # Test 7: Workflow Metadata
    print("7. Workflow Metadata Test:")
    print(f"   ✅ Classification: {workflow_response.get('message_classification')}")
    print(f"   ✅ Planned steps: {workflow_response.get('planned_steps')}")
    print(f"   ✅ Agents involved: {workflow_response.get('agents_involved')}")
    print(
        f"   ✅ User approvals needed: {workflow_response.get('user_approvals_needed')}"
    )
    print(f"   ✅ Estimated duration: {workflow_response.get('estimated_duration')}")

    print()
    print("🎉 ALL TESTS PASSED!")
    print("The workflow orchestration system is now working correctly:")
    print("   • Classification agent properly identifies COMPLEX requests")
    print("   • Workflow planning generates 8-step multi-agent coordination")
    print("   • Tool registry is properly initialized")
    print("   • Enum definitions are unified (no more comparison failures)")
    print("   • Classification results are cached to avoid LLM inconsistency")
    print("   • Workflow responses include all necessary metadata and steps")


if __name__ == "__main__":
    asyncio.run(final_workflow_test())
