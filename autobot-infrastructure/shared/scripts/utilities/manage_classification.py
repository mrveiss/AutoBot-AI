#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
AutoBot Classification Management Utility
Manage workflow classification keywords and rules in Redis
"""

import json
import logging
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

# Add AutoBot to Python path
sys.path.append(str(Path(__file__).parent))

# Add project root for terminal input handler
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from utils.terminal_input_handler import safe_input
from workflow_classifier import WorkflowClassifier


def _show_initial_stats(classifier: WorkflowClassifier) -> None:
    """Show initial classification statistics.

    Helper for main (Issue #825).
    """
    stats = classifier.get_classification_stats()
    logger.info("📊 Current Statistics:")
    logger.info(f"   Categories: {stats.get('total_categories', 0)}")
    logger.info(f"   Keywords: {stats.get('total_keywords', 0)}")
    logger.info(f"   Rules: {stats.get('total_rules', 0)}")
    logger.info("")

    logger.info("📝 Categories and Keywords:")
    for category, count in stats.get("categories", {}).items():
        keywords = classifier.get_keywords(category)
        logger.info(f"   {category}: {keywords}")
    logger.info("")


def _handle_add_keywords(classifier: WorkflowClassifier) -> None:
    """Handle adding keywords to category.

    Helper for main (Issue #825).
    """
    category = safe_input("Enter category: ", default="test").strip()
    keywords_input = safe_input(
        "Enter keywords (comma-separated): ", default="test,example"
    ).strip()
    if category and keywords_input:
        keywords = [kw.strip() for kw in keywords_input.split(",")]
        classifier.add_keywords(category, keywords)
        logger.info(f"✅ Added {len(keywords)} keywords to {category}")


def _handle_test_classification(classifier: WorkflowClassifier) -> None:
    """Handle testing message classification.

    Helper for main (Issue #825).
    """
    message = safe_input("Enter message to classify: ", default="test message").strip()
    if message:
        complexity = classifier.classify_request(message)
        logger.info(f"📋 Classification: {complexity.value}")


def _handle_add_security_keywords(classifier: WorkflowClassifier) -> None:
    """Handle adding security keywords.

    Helper for main (Issue #825).
    """
    security_keywords = [
        "pentest",
        "vulnerability",
        "malware",
        "threat",
        "attack",
        "breach",
        "intrusion",
        "forensics",
        "hardening",
        "compliance",
    ]
    classifier.add_keywords("security", security_keywords)

    network_keywords = [
        "subnet",
        "vlan",
        "dns",
        "dhcp",
        "proxy",
        "gateway",
        "switch",
        "hub",
        "wireless",
        "ethernet",
    ]
    classifier.add_keywords("network", network_keywords)

    logger.info("✅ Added extended security and network keywords")


def main():
    """Entry point for workflow classification management utility."""
    classifier = WorkflowClassifier()

    logger.info("🤖 AutoBot Classification Management")
    logger.info("=" * 50)

    _show_initial_stats(classifier)

    # Interactive management
    while True:
        logger.info("Actions:")
        logger.info("1. Add keywords to category")
        logger.info("2. Test message classification")
        logger.info("3. Show statistics")
        logger.info("4. Add security keywords")
        logger.info("5. Exit")

        choice = safe_input("\nChoice (1-5): ", default="5").strip()

        if choice == "1":
            _handle_add_keywords(classifier)
        elif choice == "2":
            _handle_test_classification(classifier)
        elif choice == "3":
            stats = classifier.get_classification_stats()
            logger.info(json.dumps(stats, indent=2))
        elif choice == "4":
            _handle_add_security_keywords(classifier)
        elif choice == "5":
            logger.info("👋 Goodbye!")
            break
        else:
            logger.error("❌ Invalid choice")

        logger.info("")


if __name__ == "__main__":
    main()
