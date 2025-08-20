"""
Workflow Classification System
Manages classification rules and keywords in Redis for dynamic updates
"""

import json
import logging
from typing import Any, Dict, List, Optional

import redis

from src.autobot_types import TaskComplexity
from src.utils.redis_client import get_redis_client

logger = logging.getLogger(__name__)


class WorkflowClassifier:
    """Manages workflow classification rules in Redis."""

    def __init__(self, redis_client: Optional[redis.Redis] = None):
        self.redis_client = redis_client or get_redis_client()
        self.rules_key = "autobot:workflow:classification:rules"
        self.keywords_key = "autobot:workflow:classification:keywords"
        # Only initialize if Redis client is available
        if self.redis_client:
            try:
                self._initialize_default_rules()
            except Exception as e:
                logger.error(f"Failed to initialize classification rules: {e}")
                self.redis_client = None

    def _initialize_default_rules(self):
        """Initialize default classification rules if not present."""
        if not self.redis_client.exists(self.keywords_key):
            default_keywords = {
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
                "install": [
                    "install",
                    "setup",
                    "configure",
                    "deploy",
                    "run",
                    "execute",
                    "start",
                ],
                "complex": [
                    "how to",
                    "guide",
                    "tutorial",
                    "step by step",
                    "plan",
                    "strategy",
                ],
                "security": [
                    "scan",
                    "security",
                    "vulnerabilities",
                    "penetration",
                    "exploit",
                    "audit",
                    "assess",
                ],
                "network": [
                    "network",
                    "port",
                    "firewall",
                    "tcp",
                    "udp",
                    "lan",
                    "wan",
                    "router",
                ],
                "system": ["system", "server", "machine", "host", "computer", "device"],
            }
            self.redis_client.set(self.keywords_key, json.dumps(default_keywords))
            logger.info("Initialized default classification keywords")

        if not self.redis_client.exists(self.rules_key):
            default_rules = {
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
            self.redis_client.set(self.rules_key, json.dumps(default_rules))
            logger.info("Initialized default classification rules")

    def get_keywords(self, category: str) -> List[str]:
        """Get keywords for a specific category."""
        try:
            keywords_data = self.redis_client.get(self.keywords_key)
            if keywords_data:
                keywords = json.loads(keywords_data)
                return keywords.get(category, [])
        except Exception as e:
            logger.error(f"Error getting keywords: {e}")
        return []

    def add_keywords(self, category: str, new_keywords: List[str]):
        """Add new keywords to a category."""
        try:
            keywords_data = self.redis_client.get(self.keywords_key)
            keywords = json.loads(keywords_data) if keywords_data else {}

            if category not in keywords:
                keywords[category] = []

            # Add new keywords, avoiding duplicates
            for keyword in new_keywords:
                if keyword.lower() not in [k.lower() for k in keywords[category]]:
                    keywords[category].append(keyword.lower())

            self.redis_client.set(self.keywords_key, json.dumps(keywords))
            logger.info(f"Added {len(new_keywords)} keywords to category {category}")
        except Exception as e:
            logger.error(f"Error adding keywords: {e}")

    def classify_request(self, user_message: str) -> TaskComplexity:
        """Classify user request using Redis-stored rules and keywords."""
        message_lower = user_message.lower()

        # Fall back to simple classification if Redis not available
        if not self.redis_client:
            logger.warning("Redis not available, using fallback classification")
            return self._fallback_classification(message_lower)

        try:
            # Get keywords from Redis
            keywords_data = self.redis_client.get(self.keywords_key)
            keywords = json.loads(keywords_data) if keywords_data else {}

            # Count keyword matches
            keyword_counts = {}
            for category, keyword_list in keywords.items():
                if category in ["security", "network", "system"]:
                    # For these categories, check if ANY keyword matches
                    keyword_counts[f"any_{category}"] = any(
                        kw in message_lower for kw in keyword_list
                    )
                else:
                    # For others, count occurrences
                    keyword_counts[category] = sum(
                        1 for kw in keyword_list if kw in message_lower
                    )

            # Special checks
            keyword_counts["has_tools"] = "tools" in message_lower

            # Get rules from Redis
            rules_data = self.redis_client.get(self.rules_key)
            rules = json.loads(rules_data) if rules_data else {}

            # Sort rules by priority
            sorted_rules = sorted(
                rules.items(), key=lambda x: x[1].get("priority", 0), reverse=True
            )

            # Evaluate rules
            for rule_name, rule_config in sorted_rules:
                condition = rule_config.get("condition", "")
                complexity = rule_config.get("complexity", "simple")

                # Simple condition evaluation (can be made more sophisticated)
                if self._evaluate_condition(condition, keyword_counts):
                    return TaskComplexity(complexity)

            return TaskComplexity.SIMPLE

        except Exception as e:
            logger.error(f"Error in classification: {e}")
            # Fallback to simple classification
            return self._fallback_classification(message_lower)

    def _fallback_classification(self, message_lower: str) -> TaskComplexity:
        """Simple fallback classification without Redis."""
        # Simple keyword-based classification
        complex_keywords = [
            "install",
            "setup",
            "configure",
            "guide",
            "tutorial",
            "how to",
        ]
        research_keywords = ["find", "search", "tools", "best", "recommend", "compare"]

        # Check for security/network combined
        has_security = any(
            kw in message_lower for kw in ["scan", "security", "vulnerabilities"]
        )
        has_network = any(kw in message_lower for kw in ["network", "port", "firewall"])
        if has_security and has_network:
            return TaskComplexity.COMPLEX

        # Check for complex tasks
        complex_count = sum(1 for kw in complex_keywords if kw in message_lower)
        if complex_count >= 2:
            return TaskComplexity.COMPLEX

        # Check for installation tasks
        if any(kw in message_lower for kw in ["install", "setup", "configure"]):
            return TaskComplexity.COMPLEX

        # Check for research tasks
        research_count = sum(1 for kw in research_keywords if kw in message_lower)
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
            from src.utils.safe_expression_evaluator import safe_evaluator

            # Create evaluation context with variable values
            eval_context = {}

            # Extract variables for evaluation
            for var_name, value in variables.items():
                # Convert to appropriate type for evaluation
                if isinstance(value, str) and value.isdigit():
                    eval_context[var_name] = int(value)
                elif isinstance(value, str) and value.lower() in ("true", "false"):
                    eval_context[var_name] = value.lower() == "true"
                else:
                    eval_context[var_name] = value

            return safe_evaluator.evaluate(condition, eval_context)
        except Exception as e:
            logger.error(f"Error evaluating condition '{condition}': {e}")
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
            logger.error(f"Error getting stats: {e}")
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
        print("Classification Statistics:")
        print(f"Total Categories: {stats['total_categories']}")
        print(f"Total Keywords: {stats['total_keywords']}")
        print(f"Total Rules: {stats['total_rules']}")
        print("\nCategories:")
        for cat, count in stats["categories"].items():
            print(f"  {cat}: {count} keywords")

    elif args.action == "add-keyword":
        if args.category and args.keyword:
            classifier.add_keywords(args.category, [args.keyword])
            print(f"Added '{args.keyword}' to category '{args.category}'")
        else:
            print("Error: --category and --keyword required")

    elif args.action == "test":
        if args.message:
            complexity = classifier.classify_request(args.message)
            print(f"Message: '{args.message}'")
            print(f"Classification: {complexity.value}")
        else:
            print("Error: --message required")
