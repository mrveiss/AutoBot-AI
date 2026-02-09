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
import logging

logger = logging.getLogger(__name__)

sys.path.append("/home/kali/Desktop/AutoBot")

from llm_self_awareness import get_llm_self_awareness
from middleware.llm_awareness_middleware import get_awareness_injector


async def test_awareness_system():
    """Test the LLM awareness system components"""
    logger.info("🤖 Testing AutoBot LLM Self-Awareness System\n")

    try:
        # Initialize awareness system
        awareness = get_llm_self_awareness()
        injector = get_awareness_injector()

        logger.info("1. System Context Overview")
        logger.info("-" * 50)
        context = await awareness.get_system_context(include_detailed=False)
        logger.info(f"System: {context['system_identity']['name']}")
        logger.info(f"Current Phase: {context['system_identity']['current_phase']}")
        logger.info(f"System Maturity: {context['system_identity']['system_maturity']}%")
        logger.info(f"Active Capabilities: {context['current_capabilities']['count']}")

        logger.info("\nCapability Categories:")
        for category, caps in context["current_capabilities"]["categories"].items():
            logger.info(f"  - {category.title()}: {len(caps)} capabilities")

        logger.info("\n2. Capability Summary")
        logger.info("-" * 50)
        summary = awareness.create_capability_summary()
        # Show first few lines of summary
        summary_lines = summary.split("\n")[:15]
        logger.info("\n".join(summary_lines))
        if len(summary.split("\n")) > 15:
            logger.info("... (truncated)")

        logger.info("\n3. Prompt Injection Test")
        logger.info("-" * 50)
        test_prompts = [
            "How can I use the workflow system?",
            "What AI capabilities do I have?",
            "Help me with system monitoring",
        ]

        for prompt in test_prompts:
            logger.info(f"\nOriginal: {prompt}")
            enhanced = await awareness.inject_awareness_context(
                prompt, context_level="basic"
            )
            # Show just the injected context part (first few lines)
            context_lines = enhanced.split("\n")[:8]
            logger.info("Enhanced with context:")
            logger.info("\n".join(context_lines))
            logger.info("... (context continues) ...")
            logger.info("")

        logger.info("\n4. Query Analysis Test")
        logger.info("-" * 50)
        test_queries = [
            "What can I do with AI features?",
            "How do I progress to the next phase?",
            "What monitoring capabilities are available?",
        ]

        for query in test_queries:
            logger.info(f"\nQuery: {query}")
            analysis = await awareness.get_phase_aware_response(query)
            print(
                f"Relevant Capabilities: {len(analysis['context']['relevant_capabilities'])}"
            )
            if analysis["recommendations"]:
                logger.info("Recommendations:")
                for rec in analysis["recommendations"]:
                    print(
                        f"  - {rec['type']}: {rec.get('suggestion', rec.get('next_action', 'See details'))}"
                    )

        logger.info("\n5. System Metrics")
        logger.info("-" * 50)
        metrics = context["system_metrics"]
        operational = context["operational_status"]

        logger.info(f"Maturity Score: {metrics['maturity_score']}%")
        logger.info(f"Validation Score: {metrics['validation_score']}%")
        print(
            f"Auto-progression: {'Enabled' if operational['auto_progression_enabled'] else 'Disabled'}"
        )
        logger.info(f"Milestones Achieved: {operational['milestones_achieved']}")

        logger.info("\n6. System Prompt Generation")
        logger.info("-" * 50)
        system_prompt = await injector.get_system_prompt_prefix(detailed=False)
        logger.info("Generated System Prompt:")
        logger.info(system_prompt)

        logger.info("\n✅ LLM Self-Awareness System Test Complete!")
        print(
            f"System is operating at {context['system_identity']['system_maturity']}% maturity"
        )

        # Export awareness data for inspection
        export_path = await awareness.export_awareness_data()
        logger.info(f"\n📄 Detailed awareness data exported to: {export_path}")

    except Exception as e:
        logger.error(f"❌ Error during awareness system test: {e}")
        import traceback

        traceback.print_exc()


async def test_api_integration():
    """Test API integration with awareness system"""
    logger.info("\n🌐 Testing API Integration")
    logger.info("-" * 50)

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
                            logger.info(f"✅ {endpoint}: {data.get('status', 'unknown')}")
                        else:
                            logger.warning(f"⚠️ {endpoint}: HTTP {response.status}")
                except Exception as e:
                    logger.error(f"❌ {endpoint}: {str(e)}")

        logger.info("\nAPI integration test complete!")

    except ImportError:
        logger.warning("⚠️ aiohttp not available, skipping API tests")
    except Exception as e:
        logger.error(f"❌ API integration test failed: {e}")


if __name__ == "__main__":
    logger.info("AutoBot LLM Self-Awareness Test Suite")
    logger.info("=" * 50)

    # Run main awareness system test
    asyncio.run(test_awareness_system())

    # Test API integration if backend is running
    try:
        asyncio.run(test_api_integration())
    except Exception as e:
        logger.warning(f"\n⚠️ API integration test skipped: {e}")
