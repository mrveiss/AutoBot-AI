#!/usr/bin/env python3
"""
Test script for MCP Manual Integration Service

This script tests the real MCP server integration for manual page and help lookup.
"""

import asyncio
import logging
import sys
import os

# Add the src directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from mcp_manual_integration import MCPManualService, lookup_system_manual, get_command_help, search_system_documentation

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def test_manual_lookup():
    """Test manual page lookup functionality."""
    print("\n=== Testing Manual Lookup ===")

    service = MCPManualService()

    # Test common commands
    test_commands = ['ls', 'grep', 'cat', 'curl', 'nonexistent_command']

    for command in test_commands:
        print(f"\nTesting manual lookup for: {command}")
        try:
            result = await service.lookup_manual(f"manual for {command}", command)
            if result:
                print(f"✓ Found manual for {command}")
                print(f"  Description: {result.get('description', 'N/A')}")
                print(f"  Source: {result.get('source', 'N/A')}")
                print(f"  Synopsis: {result.get('synopsis', 'N/A')[:100]}...")
            else:
                print(f"✗ No manual found for {command}")
        except Exception as e:
            print(f"✗ Error looking up manual for {command}: {e}")


async def test_help_lookup():
    """Test command help lookup functionality."""
    print("\n=== Testing Help Lookup ===")

    service = MCPManualService()

    # Test common commands
    test_commands = ['ls', 'curl', 'python3', 'git', 'nonexistent_command']

    for command in test_commands:
        print(f"\nTesting help lookup for: {command}")
        try:
            result = await service._real_help_lookup(command)
            if result:
                print(f"✓ Found help for {command}")
                print(f"  Description: {result.get('description', 'N/A')}")
                print(f"  Source: {result.get('source', 'N/A')}")
                print(f"  Content length: {len(result.get('content', ''))}")
            else:
                print(f"✗ No help found for {command}")
        except Exception as e:
            print(f"✗ Error looking up help for {command}: {e}")


async def test_documentation_search():
    """Test documentation search functionality."""
    print("\n=== Testing Documentation Search ===")

    service = MCPManualService()

    # Test different queries
    test_queries = ['autobot', 'linux', 'git', 'python', 'help']

    for query in test_queries:
        print(f"\nTesting documentation search for: {query}")
        try:
            result = await service._real_documentation_search(query)
            if result and result.get('results'):
                print(f"✓ Found {len(result['results'])} results for '{query}'")
                for i, doc_result in enumerate(result['results'][:3]):  # Show first 3
                    print(f"  {i+1}. {doc_result.get('title', 'No title')}")
                    print(f"     Source: {doc_result.get('source', 'Unknown')}")
                    print(f"     Relevance: {doc_result.get('relevance', 0):.2f}")
            else:
                print(f"✗ No documentation found for '{query}'")
        except Exception as e:
            print(f"✗ Error searching documentation for '{query}': {e}")


async def test_convenience_functions():
    """Test the convenience functions."""
    print("\n=== Testing Convenience Functions ===")

    # Test lookup_system_manual
    print("\nTesting lookup_system_manual...")
    try:
        result = await lookup_system_manual("how to use ls command")
        if result:
            print(f"✓ lookup_system_manual returned result for 'ls'")
        else:
            print("✗ lookup_system_manual returned None")
    except Exception as e:
        print(f"✗ Error in lookup_system_manual: {e}")

    # Test get_command_help
    print("\nTesting get_command_help...")
    try:
        result = await get_command_help("curl")
        if result:
            print(f"✓ get_command_help returned {len(result)} characters for 'curl'")
        else:
            print("✗ get_command_help returned None")
    except Exception as e:
        print(f"✗ Error in get_command_help: {e}")

    # Test search_system_documentation
    print("\nTesting search_system_documentation...")
    try:
        result = await search_system_documentation("autobot")
        if result:
            print(f"✓ search_system_documentation returned {len(result)} results")
        else:
            print("✗ search_system_documentation returned empty list")
    except Exception as e:
        print(f"✗ Error in search_system_documentation: {e}")


async def test_command_manager_integration():
    """Test integration with CommandManualManager."""
    print("\n=== Testing CommandManualManager Integration ===")

    service = MCPManualService()

    if service.command_manager:
        print("✓ CommandManualManager is available")

        # Test if we can get an existing manual
        try:
            manual = service.command_manager.get_manual('ls')
            if manual:
                print(f"✓ Found stored manual for 'ls': {manual.description}")
            else:
                print("- No stored manual for 'ls' (this is normal for first run)")
        except Exception as e:
            print(f"✗ Error accessing CommandManualManager: {e}")
    else:
        print("✗ CommandManualManager is not available")


async def test_safety_features():
    """Test security and safety features."""
    print("\n=== Testing Safety Features ===")

    service = MCPManualService()

    # Test safe command validation
    safe_commands = ['ls --help', 'curl --help', 'git help']
    unsafe_commands = ['rm --help', 'sudo --help', 'dd --help']

    print("\nTesting safe commands:")
    for cmd in safe_commands:
        cmd_args = cmd.split()
        is_safe = service._is_safe_command(cmd_args)
        print(f"  {cmd}: {'✓ Safe' if is_safe else '✗ Unsafe'}")

    print("\nTesting unsafe commands:")
    for cmd in unsafe_commands:
        cmd_args = cmd.split()
        is_safe = service._is_safe_command(cmd_args)
        print(f"  {cmd}: {'✗ Unsafe (good)' if not is_safe else '✓ Safe (unexpected)'}")


async def main():
    """Run all tests."""
    print("Starting MCP Manual Integration Tests")
    print("=" * 50)

    # Run tests
    await test_manual_lookup()
    await test_help_lookup()
    await test_documentation_search()
    await test_convenience_functions()
    await test_command_manager_integration()
    await test_safety_features()

    print("\n" + "=" * 50)
    print("MCP Manual Integration Tests Complete")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nTests interrupted by user")
    except Exception as e:
        print(f"\nTest execution failed: {e}")
        sys.exit(1)
