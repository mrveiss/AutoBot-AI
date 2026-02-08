#!/usr/bin/env python3
"""
Debug script to test tool registry initialization in orchestrator
"""

import sys
from pathlib import Path

# Add AutoBot to Python path
sys.path.append(str(Path(__file__).parent))

from src.orchestrator import Orchestrator


def test_orchestrator_initialization():
    print("🔧 Testing Orchestrator initialization...")

    # Create orchestrator instance
    orchestrator = Orchestrator()

    # Check tool registry
    print(f"Tool registry exists: {hasattr(orchestrator, 'tool_registry')}")
    print(f"Tool registry value: {orchestrator.tool_registry}")

    if orchestrator.tool_registry:
        print("✅ Tool registry is initialized")
        print(f"Tool registry type: {type(orchestrator.tool_registry)}")

        # Test tool execution
        print("\n🧪 Testing tool execution...")
        try:
            # List available tools
            available_tools = orchestrator.available_tools
            print(f"Available tools: {list(available_tools.keys())[:5]}...")

        except Exception as e:
            print(f"Error testing tool execution: {e}")
    else:
        print("❌ Tool registry is not initialized")
        print(
            f"Available attributes with 'tool': {[attr for attr in dir(orchestrator) if 'tool' in attr.lower()]}"
        )

        # Check dependencies
        print(f"Local worker exists: {hasattr(orchestrator, 'local_worker')}")
        print(f"Local worker value: {getattr(orchestrator, 'local_worker', None)}")
        print(f"Knowledge base exists: {hasattr(orchestrator, 'knowledge_base')}")
        print(f"Knowledge base value: {getattr(orchestrator, 'knowledge_base', None)}")


def test_workflow_execution():
    print("\n🚀 Testing workflow execution...")

    orchestrator = Orchestrator()

    # Test the problematic method
    import asyncio

    async def test_execution():
        action = {
            "tool_name": "respond_conversationally",
            "tool_args": {"response_text": "test response"},
        }
        messages = []

        try:
            result = await orchestrator._execute_planned_action(action, messages)
            print(f"Execution result: {result}")
        except Exception as e:
            print(f"Execution failed: {e}")

    asyncio.run(test_execution())


if __name__ == "__main__":
    test_orchestrator_initialization()
    test_workflow_execution()
