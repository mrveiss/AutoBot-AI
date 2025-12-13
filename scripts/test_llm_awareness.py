#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Test script for LLM Self-Awareness system
Demonstrates the functionality of the awareness injection system
"""

import asyncio
import sys

sys.path.append("/home/kali/Desktop/AutoBot")

from src.llm_self_awareness import get_llm_self_awareness
from src.middleware.llm_awareness_middleware import get_awareness_injector


async def test_awareness_system():
    """Test the LLM awareness system components"""
    print("🤖 Testing AutoBot LLM Self-Awareness System\n")

    try:
        # Initialize awareness system
        awareness = get_llm_self_awareness()
        injector = get_awareness_injector()

        print("1. System Context Overview")
        print("-" * 50)
        context = await awareness.get_system_context(include_detailed=False)
        print(f"System: {context['system_identity']['name']}")
        print(f"Current Phase: {context['system_identity']['current_phase']}")
        print(f"System Maturity: {context['system_identity']['system_maturity']}%")
        print(f"Active Capabilities: {context['current_capabilities']['count']}")

        print("\nCapability Categories:")
        for category, caps in context["current_capabilities"]["categories"].items():
            print(f"  - {category.title()}: {len(caps)} capabilities")

        print("\n2. Capability Summary")
        print("-" * 50)
        summary = awareness.create_capability_summary()
        # Show first few lines of summary
        summary_lines = summary.split("\n")[:15]
        print("\n".join(summary_lines))
        if len(summary.split("\n")) > 15:
            print("... (truncated)")

        print("\n3. Prompt Injection Test")
        print("-" * 50)
        test_prompts = [
            "How can I use the workflow system?",
            "What AI capabilities do I have?",
            "Help me with system monitoring",
        ]

        for prompt in test_prompts:
            print(f"\nOriginal: {prompt}")
            enhanced = await awareness.inject_awareness_context(
                prompt, context_level="basic"
            )
            # Show just the injected context part (first few lines)
            context_lines = enhanced.split("\n")[:8]
            print("Enhanced with context:")
            print("\n".join(context_lines))
            print("... (context continues) ...")
            print()

        print("\n4. Query Analysis Test")
        print("-" * 50)
        test_queries = [
            "What can I do with AI features?",
            "How do I progress to the next phase?",
            "What monitoring capabilities are available?",
        ]

        for query in test_queries:
            print(f"\nQuery: {query}")
            analysis = await awareness.get_phase_aware_response(query)
            print(
                f"Relevant Capabilities: {len(analysis['context']['relevant_capabilities'])}"
            )
            if analysis["recommendations"]:
                print("Recommendations:")
                for rec in analysis["recommendations"]:
                    print(
                        f"  - {rec['type']}: {rec.get('suggestion', rec.get('next_action', 'See details'))}"
                    )

        print("\n5. System Metrics")
        print("-" * 50)
        metrics = context["system_metrics"]
        operational = context["operational_status"]

        print(f"Maturity Score: {metrics['maturity_score']}%")
        print(f"Validation Score: {metrics['validation_score']}%")
        print(
            f"Auto-progression: {'Enabled' if operational['auto_progression_enabled'] else 'Disabled'}"
        )
        print(f"Milestones Achieved: {operational['milestones_achieved']}")

        print("\n6. System Prompt Generation")
        print("-" * 50)
        system_prompt = await injector.get_system_prompt_prefix(detailed=False)
        print("Generated System Prompt:")
        print(system_prompt)

        print("\n✅ LLM Self-Awareness System Test Complete!")
        print(
            f"System is operating at {context['system_identity']['system_maturity']}% maturity"
        )

        # Export awareness data for inspection
        export_path = await awareness.export_awareness_data()
        print(f"\n📄 Detailed awareness data exported to: {export_path}")

    except Exception as e:
        print(f"❌ Error during awareness system test: {e}")
        import traceback

        traceback.print_exc()


async def test_api_integration():
    """Test API integration with awareness system"""
    print("\n🌐 Testing API Integration")
    print("-" * 50)

    try:
        import aiohttp

        # Test awareness endpoints
        endpoints_to_test = [
            "ServiceURLs.BACKEND_LOCAL/api/llm-awareness/status",
            "ServiceURLs.BACKEND_LOCAL/api/llm-awareness/context",
            "ServiceURLs.BACKEND_LOCAL/api/llm-awareness/capabilities",
        ]

        async with aiohttp.ClientSession() as session:
            for endpoint in endpoints_to_test:
                try:
                    async with session.get(endpoint) as response:
                        if response.status == 200:
                            data = await response.json()
                            print(f"✅ {endpoint}: {data.get('status', 'unknown')}")
                        else:
                            print(f"⚠️ {endpoint}: HTTP {response.status}")
                except Exception as e:
                    print(f"❌ {endpoint}: {str(e)}")

        print("\nAPI integration test complete!")

    except ImportError:
        print("⚠️ aiohttp not available, skipping API tests")
    except Exception as e:
        print(f"❌ API integration test failed: {e}")


if __name__ == "__main__":
    print("AutoBot LLM Self-Awareness Test Suite")
    print("=" * 50)

    # Run main awareness system test
    asyncio.run(test_awareness_system())

    # Test API integration if backend is running
    try:
        asyncio.run(test_api_integration())
    except Exception as e:
        print(f"\n⚠️ API integration test skipped: {e}")
