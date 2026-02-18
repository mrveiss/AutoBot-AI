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

from agents.web_research_integration import ResearchType
from security.secure_web_research import SecureWebResearch

# Set up logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Security features summary (#825)
SECURITY_FEATURES = [
    "Input validation and sanitization",
    "Domain reputation checking",
    "Content filtering and malware detection",
    "Network isolation (private IP blocking)",
    "Threat intelligence integration",
    "User confirmation for risky queries",
    "Comprehensive logging and monitoring",
]


async def _demo_safe_query(secure_research):
    """Demo 1: Test a safe research query.

    Helper for demo_secure_research (#825).
    """
    logger.info("\n1. Testing safe research query...")
    safe_query = "Python web application security best practices"

    result = await secure_research.conduct_secure_research(
        query=safe_query,
        research_type=ResearchType.BASIC,
        max_results=3,
        require_user_confirmation=False,
    )

    logger.info("   Query: %s", safe_query)
    logger.info("   Status: %s", result["status"])
    logger.info("   Risk Level: %s", result["security"]["risk_level"])
    logger.info("   Results Found: %s", len(result["results"]))
    if result.get("security", {}).get("warnings"):
        logger.warning(
            "   Warnings: %s",
            ", ".join(result["security"]["warnings"]),
        )


async def _demo_risky_query(secure_research):
    """Demo 2: Test a risky query requiring confirmation.

    Helper for demo_secure_research (#825).
    """
    logger.info("\n2. Testing query requiring user confirmation...")
    risky_query = "how to find system vulnerabilities for penetration testing"

    risky_result = await secure_research.conduct_secure_research(
        query=risky_query,
        research_type=ResearchType.BASIC,
        max_results=3,
        require_user_confirmation=True,
    )

    logger.info("   Query: %s", risky_query)
    logger.info("   Status: %s", risky_result["status"])
    logger.info("   Risk Level: %s", risky_result["security"]["risk_level"])
    if risky_result.get("confirmation_required"):
        logger.warning("   User confirmation required before proceeding")
        logger.info(
            "   Risk Factors: %s",
            ", ".join(risky_result.get("risk_factors", [])),
        )


async def _demo_malicious_query(secure_research):
    """Demo 3: Test a malicious query that should be blocked.

    Helper for demo_secure_research (#825).
    """
    logger.info("\n3. Testing malicious query (should be blocked)...")
    malicious_query = "<script>alert('xss')</script> malware download"

    blocked_result = await secure_research.conduct_secure_research(
        query=malicious_query,
        research_type=ResearchType.BASIC,
        max_results=3,
        require_user_confirmation=False,
    )

    logger.info("   Query: %s", malicious_query)
    logger.info("   Status: %s", blocked_result["status"])
    logger.info(
        "   Threats Detected: %s",
        ", ".join(blocked_result["security"]["threats_detected"]),
    )
    logger.info("   Query blocked for security reasons")


async def _demo_domain_safety(secure_research):
    """Demo 4: Test domain safety validation.

    Helper for demo_secure_research (#825).
    """
    logger.info("\n4. Testing domain safety validation...")
    test_domains = [
        "https://github.com",
        "https://malware.com",
        "http://192.168.1.1/admin",
    ]

    for domain in test_domains:
        domain_result = await secure_research.check_domain_safety(domain)
        status = "safe" if domain_result["safe"] else "blocked"
        logger.info("   [%s] %s: %s", status, domain, domain_result["reason"])


async def _demo_security_stats(secure_research):
    """Demo 5-6: Security statistics and component tests.

    Helper for demo_secure_research (#825).
    """
    logger.info("\n5. Security statistics...")
    stats = secure_research.get_security_statistics()
    sec_stats = stats["security_stats"]

    logger.info("   Queries Validated: %s", sec_stats["queries_validated"])
    logger.info("   Queries Blocked: %s", sec_stats["queries_blocked"])
    logger.info("   Domains Checked: %s", sec_stats["domains_checked"])
    logger.info("   Threats Detected: %s", sec_stats["threats_detected"])
    logger.info("   Block Rate: %s%%", stats["rates"]["block_rate"])

    logger.info("\n6. Testing security components...")
    component_test = await secure_research.test_security_components()

    overall_status = component_test["overall_status"]
    logger.info("   Security Components: %s", overall_status.upper())

    for component, details in component_test["components"].items():
        logger.info("     %s: %s", component, details["status"])


async def demo_secure_research():
    """Demonstrate secure web research capabilities"""

    logger.info("AutoBot Secure Web Research Demo")
    logger.info("=" * 60)

    async with SecureWebResearch() as secure_research:
        await _demo_safe_query(secure_research)
        await _demo_risky_query(secure_research)
        await _demo_malicious_query(secure_research)
        await _demo_domain_safety(secure_research)
        await _demo_security_stats(secure_research)

    logger.info("\n" + "=" * 60)
    logger.info("Demo completed - Secure web research is operational!")
    logger.info("\nKey Security Features Enabled:")
    for feature in SECURITY_FEATURES:
        logger.info("  - %s", feature)


async def demo_validation_only():
    """Demonstrate validation without actual web research"""

    logger.info("\nQuick Validation Demo")
    logger.info("-" * 30)

    async with SecureWebResearch() as secure_research:
        test_queries = [
            ("Python Django tutorial", "Should be safe"),
            ("how to hack WiFi password", "Suspicious keywords"),
            ("<script>alert('xss')</script>", "Script injection"),
            ("machine learning algorithms", "Should be safe"),
            ("'; DROP TABLE users; --", "SQL injection"),
        ]

        for query, expected in test_queries:
            result = await secure_research.validate_research_query(query)

            status = "safe" if result["safe"] else "blocked"
            logger.info(
                "   [%s] [%s] %s | %s",
                status,
                result["risk_level"],
                query[:40],
                expected,
            )

            if result["threats_detected"]:
                logger.info(
                    "        Threats: %s",
                    ", ".join(result["threats_detected"]),
                )


if __name__ == "__main__":
    logger.info("Choose demo mode:")
    logger.info("1. Full secure web research demo")
    logger.info("2. Validation only demo (faster)")

    try:
        choice = input("Enter choice (1 or 2): ").strip()

        if choice == "1":
            asyncio.run(demo_secure_research())
        elif choice == "2":
            asyncio.run(demo_validation_only())
        else:
            logger.info("Invalid choice. Running validation demo...")
            asyncio.run(demo_validation_only())

    except KeyboardInterrupt:
        logger.info("\nDemo interrupted by user")
    except Exception as e:
        logger.error("Demo error: %s", e)
        sys.exit(1)
