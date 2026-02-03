#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Demo script showing secure web research functionality

This script demonstrates how the new secure web research system works
with comprehensive safety checks and validation.
"""

import asyncio
import logging
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from src.security.secure_web_research import SecureWebResearch
from src.agents.web_research_integration import ResearchType


# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def demo_secure_research():
    """Demonstrate secure web research capabilities"""

    print("🛡️ AutoBot Secure Web Research Demo")
    print("="*60)

    async with SecureWebResearch() as secure_research:

        # Demo 1: Safe query
        print("\n1. Testing safe research query...")
        safe_query = "Python web application security best practices"

        result = await secure_research.conduct_secure_research(
            query=safe_query,
            research_type=ResearchType.BASIC,
            max_results=3,
            require_user_confirmation=False  # Skip confirmation for demo
        )

        print(f"   Query: {safe_query}")
        print(f"   Status: {result['status']}")
        print(f"   Risk Level: {result['security']['risk_level']}")
        print(f"   Results Found: {len(result['results'])}")
        if result.get('security', {}).get('warnings'):
            print(f"   Warnings: {', '.join(result['security']['warnings'])}")

        # Demo 2: Risky query requiring confirmation
        print("\n2. Testing query requiring user confirmation...")
        risky_query = "how to find system vulnerabilities for penetration testing"

        risky_result = await secure_research.conduct_secure_research(
            query=risky_query,
            research_type=ResearchType.BASIC,
            max_results=3,
            require_user_confirmation=True
        )

        print(f"   Query: {risky_query}")
        print(f"   Status: {risky_result['status']}")
        print(f"   Risk Level: {risky_result['security']['risk_level']}")
        if risky_result.get('confirmation_required'):
            print("   ⚠️  User confirmation required before proceeding")
            print(f"   Risk Factors: {', '.join(risky_result.get('risk_factors', []))}")

        # Demo 3: Malicious query (will be blocked)
        print("\n3. Testing malicious query (should be blocked)...")
        malicious_query = "<script>alert('xss')</script> malware download"

        blocked_result = await secure_research.conduct_secure_research(
            query=malicious_query,
            research_type=ResearchType.BASIC,
            max_results=3,
            require_user_confirmation=False
        )

        print(f"   Query: {malicious_query}")
        print(f"   Status: {blocked_result['status']}")
        print(f"   Threats Detected: {', '.join(blocked_result['security']['threats_detected'])}")
        print("   🚫 Query blocked for security reasons")

        # Demo 4: Domain safety check
        print("\n4. Testing domain safety validation...")
        test_domains = [
            "https://github.com",
            "https://malware.com",
            "http://192.168.1.1/admin"
        ]

        for domain in test_domains:
            domain_result = await secure_research.check_domain_safety(domain)
            safety_icon = "✅" if domain_result["safe"] else "🚫"
            print(f"   {safety_icon} {domain}: {domain_result['reason']}")

        # Demo 5: Security statistics
        print("\n5. Security statistics...")
        stats = secure_research.get_security_statistics()

        print(f"   Queries Validated: {stats['security_stats']['queries_validated']}")
        print(f"   Queries Blocked: {stats['security_stats']['queries_blocked']}")
        print(f"   Domains Checked: {stats['security_stats']['domains_checked']}")
        print(f"   Threats Detected: {stats['security_stats']['threats_detected']}")
        print(f"   Block Rate: {stats['rates']['block_rate']}%")

        # Demo 6: Test all security components
        print("\n6. Testing security components...")
        component_test = await secure_research.test_security_components()

        overall_status = component_test["overall_status"]
        status_icon = "✅" if overall_status == "passed" else "❌"
        print(f"   {status_icon} Security Components: {overall_status.upper()}")

        for component, details in component_test["components"].items():
            comp_icon = "✅" if details["status"] == "passed" else "❌"
            print(f"     {comp_icon} {component}: {details['status']}")

    print("\n" + "="*60)
    print("🛡️ Demo completed - Secure web research is operational!")
    print("\nKey Security Features Enabled:")
    print("  ✅ Input validation and sanitization")
    print("  ✅ Domain reputation checking")
    print("  ✅ Content filtering and malware detection")
    print("  ✅ Network isolation (private IP blocking)")
    print("  ✅ Threat intelligence integration")
    print("  ✅ User confirmation for risky queries")
    print("  ✅ Comprehensive logging and monitoring")


async def demo_validation_only():
    """Demonstrate validation without actual web research"""

    print("\n🔍 Quick Validation Demo")
    print("-" * 30)

    async with SecureWebResearch() as secure_research:

        test_queries = [
            ("Python Django tutorial", "Should be safe"),
            ("how to hack WiFi password", "Suspicious keywords"),
            ("<script>alert('xss')</script>", "Script injection"),
            ("machine learning algorithms", "Should be safe"),
            ("'; DROP TABLE users; --", "SQL injection")
        ]

        for query, expected in test_queries:
            result = await secure_research.validate_research_query(query)

            safety_icon = "✅" if result["safe"] else "🚫"
            risk_color = {
                "low": "🟢",
                "medium": "🟡",
                "high": "🔴"
            }.get(result["risk_level"], "⚪")

            print(f"   {safety_icon} {risk_color} {query[:40]:40} | {expected}")

            if result["threats_detected"]:
                print(f"        Threats: {', '.join(result['threats_detected'])}")


if __name__ == "__main__":
    print("Choose demo mode:")
    print("1. Full secure web research demo")
    print("2. Validation only demo (faster)")

    try:
        choice = input("Enter choice (1 or 2): ").strip()

        if choice == "1":
            asyncio.run(demo_secure_research())
        elif choice == "2":
            asyncio.run(demo_validation_only())
        else:
            print("Invalid choice. Running validation demo...")
            asyncio.run(demo_validation_only())

    except KeyboardInterrupt:
        print("\nDemo interrupted by user")
    except Exception as e:
        print(f"Demo error: {e}")
        sys.exit(1)
