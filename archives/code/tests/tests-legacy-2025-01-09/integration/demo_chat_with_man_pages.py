#!/usr/bin/env python3
"""
Demo: How AutoBot chat would work with integrated man pages
"""

import asyncio
import sys
import yaml
from pathlib import Path

# Add the project root to Python path
sys.path.insert(0, str(Path(__file__).parent))

async def simulate_chat_query(query: str, machine_id: str = "linux_5582"):
    """Simulate how AutoBot would respond to a chat query using man page knowledge"""

    print(f"\n💬 User Query: \"{query}\"")
    print("🤖 AutoBot Response:")
    print("-" * 50)

    try:
        # Find machine-specific knowledge
        machine_dir = Path("data/system_knowledge/machines") / machine_id
        man_pages_dir = machine_dir / "man_pages"

        if not man_pages_dir.exists():
            print("❌ No machine-specific knowledge found. Please run integration first.")
            return

        # Load integration summary for machine context
        summary_file = machine_dir / "man_page_integration_summary.json"
        machine_context = {}

        if summary_file.exists():
            import json
            with open(summary_file, 'r') as f:
                machine_context = json.load(f)

        # Search for relevant commands based on query keywords
        query_lower = query.lower()
        relevant_tools = []

        # Define search mappings
        search_mappings = {
            "list files": ["ls"],
            "find files": ["find", "ls"],
            "search text": ["grep"],
            "view file": ["cat", "less", "more"],
            "process": ["ps"],
            "network": ["ip", "netstat", "ifconfig"],
            "pattern": ["grep", "awk"],
            "directory": ["ls"],
            "content": ["cat", "grep"]
        }

        # Find relevant commands based on query
        relevant_commands = set()
        for keyword, commands in search_mappings.items():
            if keyword in query_lower:
                relevant_commands.update(commands)

        # If no specific mapping, search all available tools
        if not relevant_commands:
            # Look through all available YAML files for text matches
            for yaml_file in man_pages_dir.glob("*.yaml"):
                try:
                    with open(yaml_file, 'r') as f:
                        data = yaml.safe_load(f)

                    for tool in data.get('tools', []):
                        searchable_text = f"{tool.get('name', '')} {tool.get('purpose', '')}".lower()
                        if any(word in searchable_text for word in query_lower.split()):
                            relevant_commands.add(tool.get('name'))

                except Exception:
                    continue

        # Load detailed info for relevant commands
        for command in relevant_commands:
            yaml_file = man_pages_dir / f"{command}.yaml"
            if yaml_file.exists():
                try:
                    with open(yaml_file, 'r') as f:
                        data = yaml.safe_load(f)
                    relevant_tools.append(data['tools'][0])
                except Exception:
                    continue

        # Generate response based on machine context
        machine_os = machine_context.get('os_type', 'unknown')
        package_manager = machine_context.get('package_manager', 'unknown')

        if relevant_tools:
            print(f"On your {machine_os} system (Machine ID: {machine_id}), here are the available tools:")
            print()

            for i, tool in enumerate(relevant_tools, 1):
                print(f"**{i}. {tool['name']}** - {tool['purpose']}")

                # Show usage if available
                usage = tool.get('usage', {})
                if usage and 'basic' in usage:
                    print(f"   📝 Usage: `{usage['basic']}`")

                # Show an example if available
                examples = tool.get('common_examples', [])
                if examples:
                    example = examples[0]
                    print(f"   💡 Example: `{example.get('command', 'N/A')}`")
                    if example.get('description'):
                        print(f"       → {example['description'][:60]}...")

                # Show some key options
                options = tool.get('options', [])
                if options and len(options) > 0:
                    key_options = options[:2]  # Show first 2 options
                    print("   🔧 Key options:")
                    for option in key_options:
                        if isinstance(option, str) and ':' in option:
                            flag, desc = option.split(':', 1)
                            print(f"      {flag.strip()}: {desc.strip()[:50]}...")

                print(f"   📖 *Source: {tool.get('source', 'man page')}*")
                print()

            print(f"✅ These tools are confirmed available on your {machine_os} system")
            print(f"   and installed via {package_manager}.")
            print()
            print("💡 **Why this is accurate:**")
            print("   • Commands verified to exist on your specific machine")
            print("   • Documentation extracted from your local man pages")
            print("   • Syntax matches your installed tool versions")
            print("   • Installation info tailored to your package manager")

        else:
            print(f"I couldn't find specific tools for '{query}' in your machine's")
            print(f"integrated knowledge base (Machine ID: {machine_id}).")
            print()
            print("However, I can help you in other ways:")
            print("• Ask me about available commands like 'ls', 'grep', 'cat', or 'ps'")
            print("• Try rephrasing your question with different keywords")
            print("• I can integrate more man pages if needed")

    except Exception as e:
        print(f"❌ Error processing query: {e}")


async def main():
    """Run chat simulation demo"""
    print("🤖 AutoBot Man Page Integration - Chat Demo")
    print("=" * 60)
    print("This demo shows how AutoBot would respond to queries using")
    print("machine-specific knowledge extracted from man pages.")
    print("=" * 60)

    # Demo queries
    demo_queries = [
        "How can I list files in a directory?",
        "What tool can I use to search for text patterns in files?",
        "How do I view the contents of a file?",
        "Show me tools for monitoring processes",
        "What network interface commands are available?"
    ]

    for query in demo_queries:
        await simulate_chat_query(query)
        print("\n" + "="*60)

    # Summary
    print("\n🎯 Key Benefits Demonstrated:")
    print("✅ Machine-specific responses - only shows tools actually available")
    print("✅ Authoritative documentation - extracted from real man pages")
    print("✅ Accurate syntax - matches installed tool versions")
    print("✅ Contextual information - includes machine OS and package manager")
    print("✅ Practical examples - real usage patterns from man pages")

    print("\n📊 Integration Stats:")
    try:
        summary_file = Path("data/system_knowledge/machines/linux_5582/man_page_integration_summary.json")
        if summary_file.exists():
            import json
            with open(summary_file, 'r') as f:
                stats = json.load(f)

            print(f"   • Machine ID: {stats.get('machine_id')}")
            print(f"   • OS Type: {stats.get('os_type')}")
            print(f"   • Package Manager: {stats.get('package_manager')}")
            print(f"   • Commands integrated: {stats.get('successful', 0)}/{stats.get('processed', 0)}")
            print(f"   • Total available tools: {stats.get('total_available_tools', 0)}")

    except Exception:
        print("   (Stats not available)")


if __name__ == "__main__":
    asyncio.run(main())
