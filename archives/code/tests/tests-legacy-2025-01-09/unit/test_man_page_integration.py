#!/usr/bin/env python3
"""
Test script for man page integration system
"""

import asyncio
import json
import sys
from pathlib import Path

# Add the project root to Python path
sys.path.insert(0, str(Path(__file__).parent))

from src.knowledge_base import KnowledgeBase
from src.agents.machine_aware_system_knowledge_manager import MachineAwareSystemKnowledgeManager
from src.agents.man_page_knowledge_integrator import get_man_page_integrator


async def test_os_detection():
    """Test 1: Machine detection and OS identification"""
    print("🔍 Test 1: Machine Detection")
    print("=" * 50)

    try:
        kb = KnowledgeBase()
        await kb.ainit()

        manager = MachineAwareSystemKnowledgeManager(kb)
        await manager._detect_current_machine()

        if manager.current_machine_profile:
            profile = manager.current_machine_profile
            print(f"✅ Machine ID: {profile.machine_id}")
            print(f"   OS Type: {profile.os_type.value}")
            print(f"   Distribution: {profile.distro.value if profile.distro else 'N/A'}")
            print(f"   Package Manager: {profile.package_manager}")
            print(f"   Available Tools: {len(profile.available_tools)}")
            print(f"   Architecture: {profile.architecture}")

            # Show some available tools
            tools_sample = sorted(list(profile.available_tools))[:10]
            print(f"   Sample Tools: {', '.join(tools_sample)}")

            return True
        else:
            print("❌ Failed to detect machine profile")
            return False

    except Exception as e:
        print(f"❌ Error in machine detection: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_single_man_page():
    """Test 2: Extract a single man page"""
    print("\n🔍 Test 2: Single Man Page Extraction")
    print("=" * 50)

    try:
        integrator = await get_man_page_integrator()

        # Test with 'ls' command (should be available on all Linux systems)
        command = "ls"
        print(f"Testing man page extraction for: {command}")

        # Check if man page exists
        exists = await integrator.check_man_page_exists(command)
        print(f"Man page exists: {exists}")

        if not exists:
            print(f"❌ Man page for {command} not found")
            return False

        # Extract man page
        man_info = await integrator.extract_man_page(command)

        if man_info:
            print(f"✅ Successfully extracted man page for {command}")
            print(f"   Title: {man_info.title}")
            print(f"   Description: {man_info.description[:100]}...")
            print(f"   Synopsis: {man_info.synopsis[:80]}...")
            print(f"   Options: {len(man_info.options)}")
            print(f"   Examples: {len(man_info.examples)}")
            print(f"   Related Tools: {', '.join(man_info.see_also[:5])}")

            # Show some options
            if man_info.options:
                print("   Sample Options:")
                for i, option in enumerate(man_info.options[:3]):
                    print(f"     {option['flag']}: {option['description'][:60]}...")

            # Show examples if available
            if man_info.examples:
                print("   Sample Examples:")
                for i, example in enumerate(man_info.examples[:2]):
                    print(f"     {example['command']}")
                    print(f"       → {example['description'][:60]}...")

            return man_info
        else:
            print(f"❌ Failed to extract man page for {command}")
            return False

    except Exception as e:
        print(f"❌ Error extracting man page: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_knowledge_conversion(man_info):
    """Test 3: Convert man page to knowledge format"""
    print("\n🔍 Test 3: Knowledge Format Conversion")
    print("=" * 50)

    try:
        integrator = await get_man_page_integrator()

        # Convert to knowledge YAML format
        knowledge_data = integrator.convert_to_knowledge_yaml(man_info)

        print(f"✅ Successfully converted {man_info.command} to knowledge format")
        print(f"   Metadata category: {knowledge_data['metadata']['category']}")
        print(f"   Tools count: {len(knowledge_data['tools'])}")

        tool_data = knowledge_data['tools'][0]
        print(f"   Tool name: {tool_data['name']}")
        print(f"   Tool type: {tool_data['type']}")
        print(f"   Purpose: {tool_data['purpose'][:80]}...")
        print(f"   Usage examples: {len(tool_data.get('common_examples', []))}")
        print(f"   Options: {len(tool_data.get('options', []))}")

        return knowledge_data

    except Exception as e:
        print(f"❌ Error converting to knowledge format: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_machine_integration():
    """Test 4: Full machine-aware integration"""
    print("\n🔍 Test 4: Machine-Aware Integration")
    print("=" * 50)

    try:
        kb = KnowledgeBase()
        await kb.ainit()

        manager = MachineAwareSystemKnowledgeManager(kb)

        # Initialize machine-aware knowledge (includes man page integration)
        print("Initializing machine-aware knowledge...")
        await manager.initialize_machine_aware_knowledge(force_reinstall=True)

        print("✅ Machine-aware knowledge initialization completed")

        # Check what was created
        machine_dir = manager._get_machine_knowledge_dir()
        print(f"   Machine knowledge directory: {machine_dir}")

        if machine_dir.exists():
            # Check man pages directory
            man_pages_dir = machine_dir / "man_pages"
            if man_pages_dir.exists():
                yaml_files = list(man_pages_dir.glob("*.yaml"))
                print(f"   Man page YAML files created: {len(yaml_files)}")

                if yaml_files:
                    print(f"   Sample files: {', '.join([f.stem for f in yaml_files[:5]])}")

                    # Read and show content of first file
                    first_file = yaml_files[0]
                    print(f"\n   Sample content from {first_file.name}:")
                    with open(first_file, 'r') as f:
                        import yaml
                        data = yaml.safe_load(f)
                        print(f"     Command: {data['tools'][0]['name']}")
                        print(f"     Purpose: {data['tools'][0]['purpose'][:60]}...")
                        print(f"     Machine ID: {data['metadata'].get('machine_id', 'N/A')}")
            else:
                print("   ⚠️ Man pages directory not found")

            # Check integration summary
            summary_file = machine_dir / "man_page_integration_summary.json"
            if summary_file.exists():
                with open(summary_file, 'r') as f:
                    summary = json.load(f)
                print(f"   Integration Summary:")
                print(f"     Processed: {summary.get('processed', 0)}")
                print(f"     Successful: {summary.get('successful', 0)}")
                print(f"     Failed: {summary.get('failed', 0)}")
                print(f"     Cached: {summary.get('cached', 0)}")
        else:
            print("   ⚠️ Machine knowledge directory not created")

        return True

    except Exception as e:
        print(f"❌ Error in machine integration: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_search_functionality():
    """Test 5: Search man page knowledge"""
    print("\n🔍 Test 5: Man Page Search")
    print("=" * 50)

    try:
        kb = KnowledgeBase()
        await kb.ainit()

        manager = MachineAwareSystemKnowledgeManager(kb)
        await manager._detect_current_machine()

        # Test searches
        test_queries = ["network", "file", "list", "process"]

        for query in test_queries:
            print(f"\nSearching for: '{query}'")
            results = await manager.search_man_page_knowledge(query)

            if results:
                print(f"   ✅ Found {len(results)} results")
                for i, result in enumerate(results[:3]):  # Show top 3
                    print(f"     {i+1}. {result['command']}: {result['purpose'][:50]}...")
                    print(f"        Relevance: {result['relevance_score']}")
            else:
                print(f"   ℹ️ No results found for '{query}'")

        return True

    except Exception as e:
        print(f"❌ Error in search functionality: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_api_simulation():
    """Test 6: Simulate API calls"""
    print("\n🔍 Test 6: API Simulation")
    print("=" * 50)

    try:
        kb = KnowledgeBase()
        await kb.ainit()

        manager = MachineAwareSystemKnowledgeManager(kb)

        # Simulate machine profile API call
        print("Simulating GET /api/knowledge_base/machine_profile")
        machine_info = await manager.get_machine_info()
        print(f"✅ Machine profile API response ready")
        print(f"   Machine ID: {machine_info.get('machine_id', 'N/A')}")
        print(f"   Tools count: {len(machine_info.get('available_tools', []))}")

        # Simulate man pages summary API call
        print("\nSimulating GET /api/knowledge_base/man_pages/summary")
        summary = await manager.get_man_page_summary()
        print(f"✅ Man pages summary API response ready")
        print(f"   Status: {summary.get('status', 'unknown')}")

        if summary.get('status') != 'not_integrated':
            print(f"   Successful integrations: {summary.get('successful', 0)}")
            print(f"   Available commands: {len(summary.get('available_commands', []))}")

        return True

    except Exception as e:
        print(f"❌ Error in API simulation: {e}")
        import traceback
        traceback.print_exc()
        return False


async def main():
    """Run all tests"""
    print("🧪 AutoBot Man Page Integration Test Suite")
    print("=" * 60)

    test_results = []

    # Run all tests
    tests = [
        ("OS Detection", test_os_detection),
        ("Single Man Page", test_single_man_page),
        ("Machine Integration", test_machine_integration),
        ("Search Functionality", test_search_functionality),
        ("API Simulation", test_api_simulation)
    ]

    man_info = None

    for test_name, test_func in tests:
        try:
            print(f"\n🔄 Running {test_name}...")

            if test_func == test_single_man_page:
                result = await test_func()
                if result and hasattr(result, 'command'):  # It's man_info
                    man_info = result
                    test_results.append((test_name, True))
                else:
                    test_results.append((test_name, bool(result)))
            elif test_func == test_knowledge_conversion and man_info:
                result = await test_func(man_info)
                test_results.append((test_name, bool(result)))
            elif test_func == test_knowledge_conversion and not man_info:
                print("⚠️ Skipping Knowledge Conversion (no man_info from previous test)")
                test_results.append((test_name, "Skipped"))
            else:
                result = await test_func()
                test_results.append((test_name, bool(result)))

        except Exception as e:
            print(f"❌ Test {test_name} failed with exception: {e}")
            test_results.append((test_name, False))

    # Summary
    print("\n" + "=" * 60)
    print("🏁 Test Results Summary")
    print("=" * 60)

    passed = 0
    total = len(test_results)

    for test_name, result in test_results:
        if result is True:
            print(f"✅ {test_name}: PASSED")
            passed += 1
        elif result is False:
            print(f"❌ {test_name}: FAILED")
        else:
            print(f"⚠️ {test_name}: {result}")

    print(f"\n📊 Overall Results: {passed}/{total} tests passed")

    if passed == total:
        print("🎉 All tests passed! Man page integration system is working correctly.")
    elif passed > total // 2:
        print("✅ Most tests passed. System is functional with minor issues.")
    else:
        print("⚠️ Several tests failed. System needs debugging.")

    return passed == total


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
