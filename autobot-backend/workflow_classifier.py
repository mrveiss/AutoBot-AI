# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Workflow Classification System
Manages classification rules and keywords in Redis for dynamic updates
"""

import json
import logging
from typing import Any, Dict, List, Optional

import redis
from autobot_types import TaskComplexity
from constants.threshold_constants import StringParsingConstants

from autobot_shared.redis_client import get_redis_client

logger = logging.getLogger(__name__)

# Performance optimization: O(1) lookup for workflow classification (Issue #326)
CRITICAL_CATEGORIES = {"security", "network", "system"}
INSTALLATION_KEYWORDS = {"install", "setup", "configure"}

# Issue #380: Module-level frozensets to avoid repeated list creation in classify_complexity
_SECURITY_NETWORK_KEYWORDS = frozenset({"scan", "security", "vulnerabilities"})
_NETWORK_KEYWORDS = frozenset({"network", "port", "firewall"})
_COMPLEX_KEYWORDS = frozenset(
    {"install", "setup", "configure", "guide", "tutorial", "how to"}
)
_RESEARCH_KEYWORDS = frozenset(
    {"find", "search", "tools", "best", "recommend", "compare"}
)

# Issue #281: Default classification keywords extracted from _initialize_default_rules
DEFAULT_CLASSIFICATION_KEYWORDS = {
    "research": [
        "find",
        "search",
        "tools",
        "best",
        "recommend",
        "compare",
        "need",
        "what",
        "which",
        "whats new",
        "what's new",
        "latest",
        "current",
        "news",
        "updates",
        ".com",
        ".lv",
        ".net",
        ".org",
        "website",
        "site",
    ],
    "install": ["install", "setup", "configure", "deploy", "run", "execute", "start"],
    "complex": ["how to", "guide", "tutorial", "step by step", "plan", "strategy"],
    "security": [
        "scan",
        "security",
        "vulnerabilities",
        "penetration",
        "exploit",
        "audit",
        "assess",
    ],
    "network": ["network", "port", "firewall", "tcp", "udp", "lan", "wan", "router"],
    "system": ["system", "server", "machine", "host", "computer", "device"],
}

# Issue #281: Default classification rules extracted from _initialize_default_rules
DEFAULT_CLASSIFICATION_RULES = {
    "security_network": {
        "condition": "any_security AND any_network",
        "complexity": "complex",
        "priority": 100,
    },
    "multiple_research": {
        "condition": "research >= 2 OR has_tools",
        "complexity": "complex",
        "priority": 90,
    },
    "installation": {
        "condition": "install >= 1",
        "complexity": "complex",
        "priority": 80,
    },
    "single_research": {
        "condition": "research >= 1",
        "complexity": "complex",
        "priority": 70,
    },
    "complex_request": {
        "condition": "complex >= 2",
        "complexity": "complex",
        "priority": 60,
    },
}


class WorkflowClassifier:
    """Manages workflow classification rules in Redis."""

    def __init__(self, redis_client: Optional[redis.Redis] = None):
        """Initialize workflow classifier with Redis client and default rules."""
        self.redis_client = redis_client or get_redis_client()
        self.rules_key = "autobot:workflow:classification:rules"
        self.keywords_key = "autobot:workflow:classification:keywords"
        # Only initialize if Redis client is available
        if self.redis_client:
            try:
                self._initialize_default_rules()
            except Exception as e:
                logger.error("Failed to initialize classification rules: %s", e)
                self.redis_client = None

    def _initialize_default_rules(self):
        """Initialize default classification rules if not present.

        Issue #281: Refactored to use module-level constants.
        Reduced from 98 to ~15 lines (85% reduction).
        """
        if not self.redis_client.exists(self.keywords_key):
            self.redis_client.set(
                self.keywords_key, json.dumps(DEFAULT_CLASSIFICATION_KEYWORDS)
            )
            logger.info("Initialized default classification keywords")

        if not self.redis_client.exists(self.rules_key):
            self.redis_client.set(
                self.rules_key, json.dumps(DEFAULT_CLASSIFICATION_RULES)
            )
            logger.info("Initialized default classification rules")

    def get_keywords(self, category: str) -> List[str]:
        """Get keywords for a specific category."""
        try:
            keywords_data = self.redis_client.get(self.keywords_key)
            if keywords_data:
                keywords = json.loads(keywords_data)
                return keywords.get(category, [])
        except Exception as e:
            logger.error("Error getting keywords: %s", e)
        return []

    def add_keywords(self, category: str, new_keywords: List[str]):
        """Add new keywords to a category."""
        try:
            keywords_data = self.redis_client.get(self.keywords_key)
            keywords = json.loads(keywords_data) if keywords_data else {}

            if category not in keywords:
                keywords[category] = []

            # Add new keywords, avoiding duplicates (O(1) lookup - Issue #326)
            existing_keywords_lower = {k.lower() for k in keywords[category]}
            for keyword in new_keywords:
                # Cache keyword.lower() to avoid repeated computation (Issue #323)
                keyword_lower = keyword.lower()
                if keyword_lower not in existing_keywords_lower:
                    keywords[category].append(keyword_lower)
                    existing_keywords_lower.add(keyword_lower)

            self.redis_client.set(self.keywords_key, json.dumps(keywords))
            logger.info("Added %s keywords to category %s", len(new_keywords), category)
        except Exception as e:
            logger.error("Error adding keywords: %s", e)

    def _count_keyword_matches(
        self, keywords: Dict[str, List[str]], message_lower: str
    ) -> Dict[str, Any]:
        """Count keyword matches for classification. Issue #620.

        Args:
            keywords: Dictionary of category to keyword list mappings
            message_lower: Lowercased message to search

        Returns:
            Dictionary of keyword counts and match flags
        """
        keyword_counts = {}
        for category, keyword_list in keywords.items():
            if category in CRITICAL_CATEGORIES:
                keyword_counts[f"any_{category}"] = any(
                    kw in message_lower for kw in keyword_list
                )
            else:
                keyword_counts[category] = sum(
                    1 for kw in keyword_list if kw in message_lower
                )
        keyword_counts["has_tools"] = "tools" in message_lower
        return keyword_counts

    def _evaluate_rules_for_complexity(
        self, rules: Dict[str, Any], keyword_counts: Dict[str, Any]
    ) -> Optional[TaskComplexity]:
        """Evaluate classification rules to determine complexity. Issue #620.

        Args:
            rules: Dictionary of rule configurations
            keyword_counts: Dictionary of keyword match counts

        Returns:
            TaskComplexity if a rule matches, None otherwise
        """
        sorted_rules = sorted(
            rules.items(), key=lambda x: x[1].get("priority", 0), reverse=True
        )
        for rule_name, rule_config in sorted_rules:
            condition = rule_config.get("condition", "")
            complexity = rule_config.get("complexity", "simple")
            if self._evaluate_condition(condition, keyword_counts):
                return TaskComplexity(complexity)
        return None

    def classify_request(self, user_message: str) -> TaskComplexity:
        """Classify user request using Redis-stored rules and keywords."""
        message_lower = user_message.lower()

        if not self.redis_client:
            logger.warning("Redis not available, using fallback classification")
            return self._fallback_classification(message_lower)

        try:
            keywords_data = self.redis_client.get(self.keywords_key)
            keywords = json.loads(keywords_data) if keywords_data else {}

            keyword_counts = self._count_keyword_matches(keywords, message_lower)

            rules_data = self.redis_client.get(self.rules_key)
            rules = json.loads(rules_data) if rules_data else {}

            result = self._evaluate_rules_for_complexity(rules, keyword_counts)
            return result if result else TaskComplexity.SIMPLE

        except Exception as e:
            logger.error("Error in classification: %s", e)
            return self._fallback_classification(message_lower)

    def _fallback_classification(self, message_lower: str) -> TaskComplexity:
        """Simple fallback classification without Redis."""
        # Issue #380: Use module-level frozensets instead of recreating lists
        # Check for security/network combined
        has_security = any(kw in message_lower for kw in _SECURITY_NETWORK_KEYWORDS)
        has_network = any(kw in message_lower for kw in _NETWORK_KEYWORDS)
        if has_security and has_network:
            return TaskComplexity.COMPLEX

        # Check for complex tasks - Issue #380: Use module-level frozenset
        complex_count = sum(1 for kw in _COMPLEX_KEYWORDS if kw in message_lower)
        if complex_count >= 2:
            return TaskComplexity.COMPLEX

        # Check for installation tasks (O(1) lookup - Issue #326)
        if any(kw in message_lower for kw in INSTALLATION_KEYWORDS):
            return TaskComplexity.COMPLEX

        # Check for research tasks - Issue #380: Use module-level frozenset
        research_count = sum(1 for kw in _RESEARCH_KEYWORDS if kw in message_lower)
        if research_count >= 1:
            return TaskComplexity.COMPLEX

        return TaskComplexity.SIMPLE

    def _evaluate_condition(self, condition: str, context: Dict[str, Any]) -> bool:
        """Evaluate a simple condition string."""
        try:
            # Replace variable names with their values
            for var_name, value in context.items():
                condition = condition.replace(var_name, str(value))

            # Replace AND/OR with Python operators
            condition = condition.replace(" AND ", " and ").replace(" OR ", " or ")

            # Safely evaluate the condition using AST parser
            from utils.safe_expression_evaluator import safe_evaluator

            # Create evaluation context with variable values
            eval_context = {}

            # Extract variables for evaluation
            for var_name, value in context.items():
                # Convert to appropriate type for evaluation
                if isinstance(value, str) and value.isdigit():
                    eval_context[var_name] = int(value)
                elif (
                    isinstance(value, str)
                    and value.lower() in StringParsingConstants.BOOL_STRING_VALUES
                ):
                    eval_context[var_name] = value.lower() == "true"
                else:
                    eval_context[var_name] = value

            return safe_evaluator.evaluate(condition, eval_context)
        except Exception as e:
            logger.error("Error evaluating condition '%s': %s", condition, e)
            return False

    def get_classification_stats(self) -> Dict[str, Any]:
        """Get statistics about classification rules and keywords."""
        try:
            keywords_data = self.redis_client.get(self.keywords_key)
            keywords = json.loads(keywords_data) if keywords_data else {}

            rules_data = self.redis_client.get(self.rules_key)
            rules = json.loads(rules_data) if rules_data else {}

            stats = {
                "total_categories": len(keywords),
                "total_keywords": sum(len(kw_list) for kw_list in keywords.values()),
                "total_rules": len(rules),
                "categories": {cat: len(kw_list) for cat, kw_list in keywords.items()},
                "rules": list(rules.keys()),
            }

            return stats
        except Exception as e:
            logger.error("Error getting stats: %s", e)
            return {}


# CLI tool for managing classification rules
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Manage workflow classification rules")
    parser.add_argument(
        "action", choices=["stats", "add-keyword", "test"], help="Action to perform"
    )
    parser.add_argument("--category", help="Keyword category")
    parser.add_argument("--keyword", help="Keyword to add")
    parser.add_argument("--message", help="Message to test classification")

    args = parser.parse_args()

    classifier = WorkflowClassifier()

    if args.action == "stats":
        stats = classifier.get_classification_stats()
        print("Classification Statistics:")  # noqa: print
        print(f"Total Categories: {stats['total_categories']}")  # noqa: print
        print(f"Total Keywords: {stats['total_keywords']}")  # noqa: print
        print(f"Total Rules: {stats['total_rules']}")  # noqa: print
        print("\nCategories:")  # noqa: print
        for cat, count in stats["categories"].items():
            print(f"  {cat}: {count} keywords")  # noqa: print

    elif args.action == "add-keyword":
        if args.category and args.keyword:
            classifier.add_keywords(args.category, [args.keyword])
            print(  # noqa: print
                f"Added '{args.keyword}' to category '{args.category}'"
            )  # noqa: print
        else:
            print("Error: --category and --keyword required")  # noqa: print

    elif args.action == "test":
        if args.message:
            complexity = classifier.classify_request(args.message)
            print(f"Message: '{args.message}'")  # noqa: print
            print(f"Classification: {complexity.value}")  # noqa: print
        else:
            print("Error: --message required")  # noqa: print
