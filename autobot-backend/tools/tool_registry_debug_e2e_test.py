#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""
Debug script to test tool registry initialization in orchestrator
"""

import sys
from pathlib import Path

# Add AutoBot to Python path
sys.path.append(str(Path(__file__).parent))

from orchestrator import Orchestrator


def test_orchestrator_initialization():
    print("🔧 Testing Orchestrator initialization...")  # noqa: print

    # Create orchestrator instance
    orchestrator = Orchestrator()

    # Check tool registry
    print(f"Tool registry exists: {hasattr(orchestrator, 'tool_registry')}")  # noqa: print  # noqa: print
    print(f"Tool registry value: {orchestrator.tool_registry}")  # noqa: print

    if orchestrator.tool_registry:
        print("✅ Tool registry is initialized")  # noqa: print
        print(f"Tool registry type: {type(orchestrator.tool_registry)}")  # noqa: print

        # Test tool execution
        print("\n🧪 Testing tool execution...")  # noqa: print
        try:
            # List available tools
            available_tools = orchestrator.available_tools
            print(f"Available tools: {list(available_tools.keys())[:5]}...")  # noqa: print  # noqa: print

        except Exception as e:
            print(f"Error testing tool execution: {e}")  # noqa: print
    else:
        print("❌ Tool registry is not initialized")  # noqa: print
        print(  # noqa: print
            f"Available attributes with 'tool': {[attr for attr in dir(orchestrator) if 'tool' in attr.lower()]}"
        )

        # Check dependencies
        print(f"Local worker exists: {hasattr(orchestrator, 'local_worker')}")  # noqa: print  # noqa: print
        print(f"Local worker value: {getattr(orchestrator, 'local_worker', None)}")  # noqa: print  # noqa: print
        print(f"Knowledge base exists: {hasattr(orchestrator, 'knowledge_base')}")  # noqa: print  # noqa: print
        print(f"Knowledge base value: {getattr(orchestrator, 'knowledge_base', None)}")  # noqa: print  # noqa: print


def test_workflow_execution():
    print("\n🚀 Testing workflow execution...")  # noqa: print

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
            print(f"Execution result: {result}")  # noqa: print
        except Exception as e:
            print(f"Execution failed: {e}")  # noqa: print

    asyncio.run(test_execution())


if __name__ == "__main__":
    test_orchestrator_initialization()
    test_workflow_execution()
