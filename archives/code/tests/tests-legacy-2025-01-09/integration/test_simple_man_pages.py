#!/usr/bin/env python3
"""
Simplified test for man page integration - tests core functionality only
"""

import asyncio
import sys
from pathlib import Path

# Add the project root to Python path
sys.path.insert(0, str(Path(__file__).parent))

# Test the core components directly
async def test_os_detection():
    """Test OS detection functionality"""
    print("🔍 Test 1: OS Detection")
    print("=" * 50)

    try:
        from src.intelligence.os_detector import get_os_detector

        detector = await get_os_detector()
        os_info = await detector.detect_system()

        print(f"✅ OS Detection successful")
        print(f"   OS Type: {os_info.os_type.value}")
        print(f"   Distribution: {os_info.distro.value if os_info.distro else 'N/A'}")
        print(f"   Architecture: {os_info.architecture}")
        print(f"   Package Manager: {os_info.package_manager}")
        print(f"   Available Tools: {len(os_info.capabilities)}")
        print(f"   Is WSL: {os_info.is_wsl}")
        print(f"   User: {os_info.user}")

        # Show some tools
        tools_sample = sorted(list(os_info.capabilities))[:15]
        print(f"   Sample Tools: {', '.join(tools_sample)}")

        return os_info

    except Exception as e:
        print(f"❌ OS detection failed: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_man_page_extraction():
    """Test man page extraction"""
    print("\n🔍 Test 2: Man Page Extraction")
    print("=" * 50)

    try:
        from src.agents.man_page_knowledge_integrator import get_man_page_integrator

        integrator = await get_man_page_integrator()

        # Test with common commands
        test_commands = ['ls', 'grep', 'cat', 'ps', 'ping']
        successful_extractions = []

        for command in test_commands:
            print(f"\nTesting: {command}")

            # Check if command exists
            exists = await integrator.check_man_page_exists(command)
            print(f"  Man page exists: {exists}")

            if exists:
                # Extract man page
                man_info = await integrator.extract_man_page(command)
                if man_info:
                    print(f"  ✅ Extracted successfully")
                    print(f"     Title: {man_info.title}")
                    print(f"     Description: {man_info.description[:80]}...")
                    print(f"     Options: {len(man_info.options)}")
                    print(f"     Examples: {len(man_info.examples)}")

                    # Show first option if available
                    if man_info.options:
                        first_option = man_info.options[0]
                        print(f"     Sample option: {first_option['flag']} - {first_option['description'][:40]}...")

                    successful_extractions.append(man_info)
                else:
                    print(f"  ❌ Extraction failed")
            else:
                print(f"  ⚠️ Man page not available")

        print(f"\n📊 Results: {len(successful_extractions)}/{len(test_commands)} successful extractions")

        return successful_extractions

    except Exception as e:
        print(f"❌ Man page extraction test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_knowledge_conversion():
    """Test converting man pages to knowledge format"""
    print("\n🔍 Test 3: Knowledge Conversion")
    print("=" * 50)

    try:
        from src.agents.man_page_knowledge_integrator import get_man_page_integrator

        integrator = await get_man_page_integrator()

        # Extract ls man page for conversion test
        man_info = await integrator.extract_man_page('ls')
        if not man_info:
            print("❌ Could not extract ls man page for conversion test")
            return False

        # Convert to knowledge format
        knowledge_data = integrator.convert_to_knowledge_yaml(man_info)

        print("✅ Conversion successful")
        print(f"   Metadata category: {knowledge_data['metadata']['category']}")
        print(f"   Source: {knowledge_data['metadata']['source']}")
        print(f"   Tools count: {len(knowledge_data['tools'])}")

        tool_data = knowledge_data['tools'][0]
        print(f"   Tool name: {tool_data['name']}")
        print(f"   Tool type: {tool_data['type']}")
        print(f"   Purpose: {tool_data['purpose'][:60]}...")
        print(f"   Usage entries: {len(tool_data.get('usage', {}))}")
        print(f"   Examples: {len(tool_data.get('common_examples', []))}")
        print(f"   Options: {len(tool_data.get('options', []))}")
        print(f"   Related tools: {len(tool_data.get('related_tools', []))}")

        # Show an example if available
        if tool_data.get('common_examples'):
            example = tool_data['common_examples'][0]
            print(f"   Sample example: {example.get('command', 'N/A')}")
            print(f"     Description: {example.get('description', 'N/A')[:50]}...")

        return knowledge_data

    except Exception as e:
        print(f"❌ Knowledge conversion test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_directory_creation():
    """Test that the system creates proper directory structure"""
    print("\n🔍 Test 4: Directory Structure")
    print("=" * 50)

    try:
        base_dir = Path("data/system_knowledge")

        print(f"Checking base directory: {base_dir}")
        if base_dir.exists():
            print("✅ Base system knowledge directory exists")

            # List contents
            contents = list(base_dir.iterdir())
            print(f"   Contents: {[item.name for item in contents if item.is_dir()]}")

            # Check for machines directory
            machines_dir = base_dir / "machines"
            if machines_dir.exists():
                print("✅ Machines directory exists")
                machine_dirs = list(machines_dir.iterdir())
                print(f"   Machine directories: {[d.name for d in machine_dirs if d.is_dir()]}")
            else:
                print("ℹ️ Machines directory doesn't exist yet (will be created during integration)")

            # Check man pages cache directory
            man_cache_dir = base_dir / "man_pages"
            if man_cache_dir.exists():
                print("✅ Man pages cache directory exists")
                cache_files = list(man_cache_dir.glob("*.json"))
                print(f"   Cached man pages: {len(cache_files)}")
            else:
                print("ℹ️ Man pages cache directory doesn't exist yet")

        else:
            print(f"ℹ️ Base directory {base_dir} doesn't exist yet")

        return True

    except Exception as e:
        print(f"❌ Directory structure test failed: {e}")
        return False


async def test_priority_commands_check():
    """Test checking which priority commands are available"""
    print("\n🔍 Test 5: Priority Commands Availability")
    print("=" * 50)

    try:
        from src.agents.man_page_knowledge_integrator import get_man_page_integrator
        from src.intelligence.os_detector import get_os_detector

        integrator = await get_man_page_integrator()
        detector = await get_os_detector()

        # Get available commands on this machine
        os_info = await detector.detect_system()
        available_commands = os_info.capabilities

        # Check intersection with priority commands
        priority_commands = integrator.priority_commands
        available_priority = [cmd for cmd in priority_commands if cmd in available_commands]

        print(f"✅ Priority commands analysis:")
        print(f"   Total priority commands: {len(priority_commands)}")
        print(f"   Available on this machine: {len(available_priority)}")
        print(f"   Coverage: {len(available_priority)/len(priority_commands)*100:.1f}%")

        # Show categories
        network_tools = [cmd for cmd in available_priority if cmd in ['ping', 'curl', 'wget', 'netstat', 'ss', 'nmap', 'arp', 'dig', 'nslookup', 'traceroute', 'ifconfig', 'ip']]
        file_tools = [cmd for cmd in available_priority if cmd in ['ls', 'find', 'grep', 'cat', 'head', 'tail', 'less', 'more', 'wc', 'sort', 'uniq', 'cut', 'awk', 'sed']]
        system_tools = [cmd for cmd in available_priority if cmd in ['ps', 'top', 'htop', 'df', 'du', 'free', 'uname', 'whoami', 'id', 'groups', 'sudo', 'su']]

        print(f"   Network tools available: {len(network_tools)}/{12} ({', '.join(network_tools[:5])}...)")
        print(f"   File tools available: {len(file_tools)}/{14} ({', '.join(file_tools[:5])}...)")
        print(f"   System tools available: {len(system_tools)}/{12} ({', '.join(system_tools[:5])}...)")

        # Check some specific ones
        important_commands = ['ls', 'grep', 'ps', 'ip', 'ping']
        for cmd in important_commands:
            available = cmd in available_commands
            has_man = await integrator.check_man_page_exists(cmd) if available else False
            status = "✅" if available and has_man else "⚠️" if available else "❌"
            print(f"   {status} {cmd}: available={available}, has_man={has_man}")

        return available_priority

    except Exception as e:
        print(f"❌ Priority commands test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


async def main():
    """Run simplified man page integration tests"""
    print("🧪 Simplified Man Page Integration Test")
    print("=" * 60)

    results = []

    # Test 1: OS Detection
    os_info = await test_os_detection()
    results.append(("OS Detection", bool(os_info)))

    # Test 2: Man page extraction
    if os_info and os_info.os_type.value == "linux":
        extractions = await test_man_page_extraction()
        results.append(("Man Page Extraction", bool(extractions)))

        # Test 3: Knowledge conversion
        if extractions:
            knowledge_data = await test_knowledge_conversion()
            results.append(("Knowledge Conversion", bool(knowledge_data)))
    else:
        print("\n⚠️ Skipping man page tests - not on Linux system")
        results.append(("Man Page Extraction", "Skipped - Not Linux"))
        results.append(("Knowledge Conversion", "Skipped - Not Linux"))

    # Test 4: Directory structure
    dir_test = await test_directory_creation()
    results.append(("Directory Structure", dir_test))

    # Test 5: Priority commands
    if os_info and os_info.os_type.value == "linux":
        priority_test = await test_priority_commands_check()
        results.append(("Priority Commands", bool(priority_test)))
    else:
        results.append(("Priority Commands", "Skipped - Not Linux"))

    # Summary
    print("\n" + "=" * 60)
    print("🏁 Test Results Summary")
    print("=" * 60)

    passed = 0
    total = 0

    for test_name, result in results:
        if isinstance(result, bool):
            total += 1
            if result:
                print(f"✅ {test_name}: PASSED")
                passed += 1
            else:
                print(f"❌ {test_name}: FAILED")
        else:
            print(f"⚠️ {test_name}: {result}")

    if total > 0:
        print(f"\n📊 Overall Results: {passed}/{total} tests passed ({passed/total*100:.1f}%)")

        if passed == total:
            print("🎉 All tests passed! Core man page functionality is working.")
        elif passed >= total * 0.8:
            print("✅ Most tests passed. System is largely functional.")
        else:
            print("⚠️ Several tests failed. System needs investigation.")

        return passed == total
    else:
        print("⚠️ No tests were run (possibly not on Linux)")
        return False


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
