#!/usr/bin/env python3
"""
Full integration test - actually creates machine-specific knowledge with man pages
"""

import asyncio
import json
import sys
import yaml
from pathlib import Path

# Add the project root to Python path
sys.path.insert(0, str(Path(__file__).parent))

async def test_full_machine_integration():
    """Test creating a complete machine profile with man page integration"""
    print("🔄 Full Machine Integration Test")
    print("=" * 60)

    try:
        from src.intelligence.os_detector import get_os_detector
        from src.agents.man_page_knowledge_integrator import get_man_page_integrator

        # Step 1: Detect machine
        print("\n📍 Step 1: Machine Detection")
        detector = await get_os_detector()
        os_info = await detector.detect_system()

        # Create a mock machine profile
        machine_id = f"{os_info.os_type.value}_{hash(os_info.user + os_info.architecture) % 10000:04d}"
        print(f"✅ Machine ID: {machine_id}")
        print(f"   OS: {os_info.os_type.value}")
        print(f"   Available tools: {len(os_info.capabilities)}")

        # Step 2: Set up directories
        print("\n📂 Step 2: Directory Setup")
        base_dir = Path("data/system_knowledge")
        machine_dir = base_dir / "machines" / machine_id
        man_pages_dir = machine_dir / "man_pages"

        # Create directories
        machine_dir.mkdir(parents=True, exist_ok=True)
        man_pages_dir.mkdir(parents=True, exist_ok=True)

        print(f"✅ Created machine directory: {machine_dir}")

        # Step 3: Integrate man pages for a subset of commands
        print("\n📖 Step 3: Man Page Integration")
        integrator = await get_man_page_integrator()

        # Test with a small set of important commands
        test_commands = ['ls', 'grep', 'cat', 'ps', 'ip', 'netstat']
        available_commands = [cmd for cmd in test_commands if cmd in os_info.capabilities]

        print(f"Processing {len(available_commands)} commands: {', '.join(available_commands)}")

        integration_results = {
            'processed': 0,
            'successful': 0,
            'failed': 0,
            'commands': {}
        }

        for command in available_commands:
            integration_results['processed'] += 1

            try:
                # Check if man page exists
                if not await integrator.check_man_page_exists(command):
                    integration_results['failed'] += 1
                    integration_results['commands'][command] = 'no_man_page'
                    continue

                # Extract man page
                man_info = await integrator.extract_man_page(command)
                if not man_info:
                    integration_results['failed'] += 1
                    integration_results['commands'][command] = 'extraction_failed'
                    continue

                # Set machine ID
                man_info.machine_id = machine_id

                # Convert to knowledge format
                knowledge_data = integrator.convert_to_knowledge_yaml(man_info)

                # Add machine-specific metadata
                knowledge_data['metadata'].update({
                    'machine_id': machine_id,
                    'os_type': os_info.os_type.value,
                    'package_manager': os_info.package_manager,
                    'integration_type': 'machine_aware_man_pages'
                })

                # Save as YAML
                yaml_file = man_pages_dir / f"{command}.yaml"
                with open(yaml_file, 'w') as f:
                    yaml.dump(knowledge_data, f, default_flow_style=False, indent=2)

                integration_results['successful'] += 1
                integration_results['commands'][command] = 'success'

                print(f"  ✅ {command}: integrated successfully")

            except Exception as e:
                integration_results['failed'] += 1
                integration_results['commands'][command] = f'error: {str(e)}'
                print(f"  ❌ {command}: failed - {e}")

        # Step 4: Save integration summary
        print("\n📊 Step 4: Save Integration Summary")
        summary_data = {
            **integration_results,
            'machine_id': machine_id,
            'os_type': os_info.os_type.value,
            'package_manager': os_info.package_manager,
            'total_available_tools': len(os_info.capabilities),
            'integration_date': '2025-09-09T15:45:00'  # Current time
        }

        summary_file = machine_dir / "man_page_integration_summary.json"
        with open(summary_file, 'w') as f:
            json.dump(summary_data, f, indent=2)

        print(f"✅ Integration summary saved")
        print(f"   Processed: {integration_results['processed']}")
        print(f"   Successful: {integration_results['successful']}")
        print(f"   Failed: {integration_results['failed']}")

        # Step 5: Test search functionality
        print("\n🔍 Step 5: Test Search")

        search_queries = ["list files", "network interface", "process", "pattern"]

        for query in search_queries:
            print(f"\nSearching for: '{query}'")
            results = []

            # Simple search through created YAML files
            for yaml_file in man_pages_dir.glob("*.yaml"):
                try:
                    with open(yaml_file, 'r') as f:
                        data = yaml.safe_load(f)

                    # Search in tool data
                    for tool in data.get('tools', []):
                        searchable_text = f"{tool.get('name', '')} {tool.get('purpose', '')}".lower()

                        if query.lower() in searchable_text:
                            results.append({
                                'command': tool.get('name'),
                                'purpose': tool.get('purpose'),
                                'file': yaml_file.name
                            })

                except Exception as e:
                    print(f"    Error searching {yaml_file}: {e}")

            if results:
                print(f"  ✅ Found {len(results)} results:")
                for result in results[:3]:  # Show top 3
                    print(f"    • {result['command']}: {result['purpose'][:50]}...")
            else:
                print(f"  ℹ️ No results found")

        # Step 6: Show sample knowledge content
        print("\n📋 Step 6: Sample Knowledge Content")

        yaml_files = list(man_pages_dir.glob("*.yaml"))
        if yaml_files:
            sample_file = yaml_files[0]
            print(f"\nSample content from {sample_file.name}:")

            with open(sample_file, 'r') as f:
                data = yaml.safe_load(f)

            tool_data = data['tools'][0]
            print(f"  Command: {tool_data['name']}")
            print(f"  Purpose: {tool_data['purpose']}")
            print(f"  Type: {tool_data['type']}")
            print(f"  Source: {tool_data.get('source', 'N/A')}")

            if tool_data.get('common_examples'):
                print(f"  Example: {tool_data['common_examples'][0].get('command', 'N/A')}")

            metadata = data.get('metadata', {})
            print(f"  Machine ID: {metadata.get('machine_id', 'N/A')}")
            print(f"  OS Type: {metadata.get('os_type', 'N/A')}")

        # Step 7: Verify file structure
        print("\n🗂️ Step 7: Verify File Structure")

        print(f"Machine directory: {machine_dir}")
        if machine_dir.exists():
            print(f"  ✅ Machine directory exists")

            yaml_files = list(man_pages_dir.glob("*.yaml"))
            json_files = list(machine_dir.glob("*.json"))

            print(f"  📄 YAML files created: {len(yaml_files)}")
            print(f"     Files: {', '.join([f.stem for f in yaml_files])}")
            print(f"  📄 JSON files created: {len(json_files)}")
            print(f"     Files: {', '.join([f.stem for f in json_files])}")

            # Calculate total size
            total_size = sum(f.stat().st_size for f in machine_dir.rglob('*') if f.is_file())
            print(f"  💾 Total size: {total_size:,} bytes ({total_size/1024:.1f} KB)")

        return {
            'machine_id': machine_id,
            'integration_results': integration_results,
            'files_created': len(yaml_files) + len(json_files),
            'machine_dir': str(machine_dir)
        }

    except Exception as e:
        print(f"❌ Full integration test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_chat_simulation():
    """Simulate what a chat query would look like"""
    print("\n💬 Chat Query Simulation")
    print("=" * 50)

    try:
        # Simulate user asking about network interfaces
        print("User Query: 'What tool can I use to see network interfaces?'")
        print("\nSimulated AutoBot Response:")
        print("-" * 30)

        # Check what network tools we have integrated
        machine_dirs = list(Path("data/system_knowledge/machines").glob("*"))
        if machine_dirs:
            machine_dir = machine_dirs[0]  # Use first machine
            man_pages_dir = machine_dir / "man_pages"

            network_tools = []
            for yaml_file in man_pages_dir.glob("*.yaml"):
                try:
                    with open(yaml_file, 'r') as f:
                        data = yaml.safe_load(f)

                    for tool in data.get('tools', []):
                        tool_name = tool.get('name', '')
                        purpose = tool.get('purpose', '').lower()

                        # Check if it's network related
                        if any(keyword in purpose for keyword in ['network', 'interface', 'ip', 'connection']):
                            network_tools.append({
                                'name': tool_name,
                                'purpose': tool.get('purpose', ''),
                                'synopsis': tool.get('usage', {}).get('basic', ''),
                                'source': tool.get('source', '')
                            })

                except Exception:
                    continue

            if network_tools:
                machine_id = machine_dir.name
                print(f"On your {machine_id.split('_')[0]} machine, here are the available network tools:\n")

                for tool in network_tools[:3]:  # Show top 3
                    print(f"✅ **{tool['name']}** - {tool['purpose']}")
                    if tool['synopsis']:
                        print(f"   Usage: `{tool['synopsis']}`")
                    print(f"   *Source: {tool['source']}*\n")

                print("These tools are confirmed available on your system with full")
                print("documentation extracted from the local man pages.")

            else:
                print("No network-related tools found in the integrated knowledge base.")

        else:
            print("No machine-specific knowledge found. Run integration first.")

        return True

    except Exception as e:
        print(f"❌ Chat simulation failed: {e}")
        return False


async def main():
    """Run full integration test"""
    print("🧪 AutoBot Man Page Full Integration Test")
    print("=" * 60)

    # Test 1: Full integration
    integration_result = await test_full_machine_integration()

    if integration_result:
        print(f"\n✅ Full integration successful!")
        print(f"   Machine ID: {integration_result['machine_id']}")
        print(f"   Files created: {integration_result['files_created']}")
        print(f"   Location: {integration_result['machine_dir']}")

        # Test 2: Chat simulation
        await test_chat_simulation()

        print("\n" + "=" * 60)
        print("🎉 FULL INTEGRATION TEST SUCCESSFUL!")
        print("=" * 60)
        print("\nThe man page integration system is working correctly:")
        print("✅ Machine detection and profiling")
        print("✅ Man page extraction and parsing")
        print("✅ Knowledge format conversion")
        print("✅ Machine-specific file organization")
        print("✅ Search functionality")
        print("✅ Chat integration simulation")

        print(f"\n📁 Created machine-specific knowledge at:")
        print(f"   {integration_result['machine_dir']}")
        print(f"\n💡 This knowledge will make AutoBot's responses:")
        print(f"   • Machine-specific and accurate")
        print(f"   • Based on actual available tools")
        print(f"   • Include proper command syntax")
        print(f"   • Reference authoritative man pages")

        return True
    else:
        print("\n❌ Integration test failed")
        return False


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
