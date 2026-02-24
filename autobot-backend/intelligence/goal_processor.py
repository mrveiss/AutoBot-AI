# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Natural Language Goal Processing Module

This module processes natural language goals and converts them into
structured intents for the intelligent agent system.
"""

import asyncio
import logging
import re
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from enum import Enum
from typing import Dict, List

logger = logging.getLogger(__name__)

# Issue #380: Pre-compiled regex patterns for warning generation
_SUDO_ROOT_RE = re.compile(r"sudo|root")
_INSTALL_DOWNLOAD_RE = re.compile(r"install|download")
_NETWORK_SCAN_PORT_RE = re.compile(r"network|scan|port")


class GoalCategory(Enum):
    """Categories of goals the system can handle."""

    NETWORK = "network"
    SYSTEM = "system"
    FILES = "files"
    DEVELOPMENT = "development"
    SECURITY = "security"
    MONITORING = "monitoring"
    UNKNOWN = "unknown"


class RiskLevel(Enum):
    """Risk levels for different operations."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class ProcessedGoal:
    """Processed goal with structured information."""

    original_goal: str
    intent: str
    explanation: str
    category: GoalCategory
    confidence: float
    risk_level: RiskLevel
    warnings: List[str] = field(default_factory=list)
    suggested_commands: List[str] = field(default_factory=list)


class GoalProcessor:
    """Natural language goal processor."""

    def __init__(self):
        """Initialize the goal processor."""
        self._intent_patterns = self._build_intent_patterns()
        self._risk_patterns = self._build_risk_patterns()

    def _build_intent_patterns(self) -> Dict[str, Dict]:
        """
        Build intent recognition patterns.

        Issue #281: Refactored from 149 lines to use extracted category builders.
        """
        patterns: Dict[str, Dict] = {}
        patterns.update(self._get_network_intents())
        patterns.update(self._get_system_intents())
        patterns.update(self._get_file_intents())
        patterns.update(self._get_development_intents())
        patterns.update(self._get_monitoring_intents())
        return patterns

    def _get_network_intents(self) -> Dict[str, Dict]:
        """Network operation intent patterns. Issue #281: Extracted helper."""
        return {
            "get_ip_address": {
                "patterns": [
                    r"what.{0,10}my.{0,10}ip",
                    r"show.{0,10}ip.{0,10}address",
                    r"get.{0,10}ip",
                    r"find.{0,10}ip",
                    r"current.{0,10}ip",
                ],
                "category": GoalCategory.NETWORK,
                "explanation": "Get your current IP address",
                "risk": RiskLevel.LOW,
            },
            "network_scan": {
                "patterns": [
                    r"scan.{0,10}network",
                    r"find.{0,10}devices",
                    r"network.{0,10}devices",
                    r"what.{0,10}devices.{0,10}network",
                    r"discover.{0,10}hosts",
                ],
                "category": GoalCategory.NETWORK,
                "explanation": "Scan the network for connected devices",
                "risk": RiskLevel.MEDIUM,
            },
            "port_scan": {
                "patterns": [
                    r"scan.{0,10}ports?",
                    r"open.{0,10}ports?",
                    r"check.{0,10}ports?",
                    r"port.{0,10}scan",
                ],
                "category": GoalCategory.SECURITY,
                "explanation": "Scan for open ports on a target",
                "risk": RiskLevel.HIGH,
            },
        }

    def _system_info_intent(self) -> Dict:
        """System info intent definition. Issue #620."""
        return {
            "patterns": [
                r"system.{0,10}info",
                r"show.{0,10}system",
                r"system.{0,10}details",
                r"computer.{0,10}info",
                r"hardware.{0,10}info",
            ],
            "category": GoalCategory.SYSTEM,
            "explanation": "Display system information and specifications",
            "risk": RiskLevel.LOW,
        }

    def _system_update_intent(self) -> Dict:
        """System update intent definition. Issue #620."""
        return {
            "patterns": [
                r"update.{0,10}system",
                r"system.{0,10}update",
                r"os.{0,10}update",
                r"upgrade.{0,10}system",
                r"install.{0,10}updates",
            ],
            "category": GoalCategory.SYSTEM,
            "explanation": "Update the operating system",
            "risk": RiskLevel.HIGH,
        }

    def _disk_usage_intent(self) -> Dict:
        """Disk usage intent definition. Issue #620."""
        return {
            "patterns": [
                r"disk.{0,10}usage",
                r"storage.{0,10}space",
                r"check.{0,10}disk",
                r"free.{0,10}space",
                r"disk.{0,10}space",
            ],
            "category": GoalCategory.SYSTEM,
            "explanation": "Check disk usage and available storage",
            "risk": RiskLevel.LOW,
        }

    def _list_processes_intent(self) -> Dict:
        """List processes intent definition. Issue #620."""
        return {
            "patterns": [
                r"list.{0,10}processes",
                r"show.{0,10}processes",
                r"running.{0,10}processes",
                r"ps.{0,10}list",
                r"find.{0,10}python.{0,10}processes",
            ],
            "category": GoalCategory.SYSTEM,
            "explanation": "List running processes",
            "risk": RiskLevel.LOW,
        }

    def _get_system_intents(self) -> Dict[str, Dict]:
        """System operation intent patterns. Issue #620."""
        return {
            "system_info": self._system_info_intent(),
            "system_update": self._system_update_intent(),
            "disk_usage": self._disk_usage_intent(),
            "list_processes": self._list_processes_intent(),
        }

    def _get_file_intents(self) -> Dict[str, Dict]:
        """File operation intent patterns. Issue #281: Extracted helper."""
        return {
            "list_files": {
                "patterns": [
                    r"list.{0,10}files",
                    r"show.{0,10}files",
                    r"ls.{0,10}directory",
                    r"directory.{0,10}contents",
                    r"files.{0,10}current.{0,10}directory",
                ],
                "category": GoalCategory.FILES,
                "explanation": "List files in the current or specified directory",
                "risk": RiskLevel.LOW,
            },
            "find_files": {
                "patterns": [
                    r"find.{0,10}files?",
                    r"search.{0,10}files?",
                    r"locate.{0,10}files?",
                    r"grep.{0,10}files?",
                ],
                "category": GoalCategory.FILES,
                "explanation": "Search for files matching criteria",
                "risk": RiskLevel.LOW,
            },
            "backup_files": {
                "patterns": [
                    r"backup.{0,20}(home|directory|files?)",
                    r"create.{0,10}backup",
                    r"archive.{0,10}files?",
                ],
                "category": GoalCategory.FILES,
                "explanation": "Create backup of files or directories",
                "risk": RiskLevel.MEDIUM,
            },
        }

    def _get_development_intents(self) -> Dict[str, Dict]:
        """Development operation intent patterns. Issue #281: Extracted helper."""
        return {
            "install_package": {
                "patterns": [
                    r"install.{0,20}(docker|nginx|apache|mysql|postgresql|node|python|git)",  # noqa: E501
                    r"setup.{0,20}(docker|nginx|apache|mysql|postgresql|node|python|git)",  # noqa: E501
                    r"deploy.{0,20}(docker|nginx|apache|mysql|postgresql|node|python|git)",  # noqa: E501
                ],
                "category": GoalCategory.DEVELOPMENT,
                "explanation": "Install development tools or packages",
                "risk": RiskLevel.MEDIUM,
            },
        }

    def _get_monitoring_intents(self) -> Dict[str, Dict]:
        """Monitoring operation intent patterns. Issue #281: Extracted helper."""
        return {
            "system_monitoring": {
                "patterns": [
                    r"monitor.{0,10}system",
                    r"performance.{0,10}monitor",
                    r"system.{0,10}performance",
                    r"cpu.{0,10}usage",
                    r"memory.{0,10}usage",
                ],
                "category": GoalCategory.MONITORING,
                "explanation": "Monitor system performance and resources",
                "risk": RiskLevel.LOW,
            },
        }

    def _build_risk_patterns(self) -> Dict[str, RiskLevel]:
        """Build risk assessment patterns."""
        return {
            # Critical risk patterns
            r"rm.{0,5}-r": RiskLevel.CRITICAL,
            r"format.{0,10}disk": RiskLevel.CRITICAL,
            r"delete.{0,10}all": RiskLevel.CRITICAL,
            r"destroy.{0,10}data": RiskLevel.CRITICAL,
            # High risk patterns
            r"sudo.{0,10}rm": RiskLevel.HIGH,
            r"chmod.{0,10}777": RiskLevel.HIGH,
            r"disable.{0,10}firewall": RiskLevel.HIGH,
            r"root.{0,10}access": RiskLevel.HIGH,
            # Medium risk patterns
            r"install.{0,10}software": RiskLevel.MEDIUM,
            r"modify.{0,10}system": RiskLevel.MEDIUM,
            r"change.{0,10}permissions": RiskLevel.MEDIUM,
            # Low risk patterns are default
        }

    def _find_best_intent_match(
        self, user_input_lower: str
    ) -> tuple[tuple[str, Dict] | None, float]:
        """
        Find the best matching intent for user input.

        Args:
            user_input_lower: Lowercase user input string

        Returns:
            Tuple of (best_match, best_confidence). Issue #620.
        """
        best_match = None
        best_confidence = 0.0

        for intent_name, intent_data in self._intent_patterns.items():
            for pattern in intent_data["patterns"]:
                if re.search(pattern, user_input_lower):
                    confidence = self._calculate_pattern_confidence(
                        pattern, user_input_lower
                    )
                    if confidence > best_confidence:
                        best_confidence = confidence
                        best_match = (intent_name, intent_data)

        return best_match, best_confidence

    def _build_matched_goal(
        self,
        user_input: str,
        user_input_lower: str,
        intent_name: str,
        intent_data: Dict,
        confidence: float,
    ) -> ProcessedGoal:
        """
        Build ProcessedGoal for a matched intent.

        Args:
            user_input: Original user input
            user_input_lower: Lowercase user input
            intent_name: Name of matched intent
            intent_data: Intent pattern data
            confidence: Match confidence score

        Returns:
            ProcessedGoal for matched intent. Issue #620.
        """
        risk_level = self._assess_risk_level(user_input_lower, intent_data["risk"])
        warnings = self._generate_warnings(user_input_lower, risk_level)

        return ProcessedGoal(
            original_goal=user_input,
            intent=intent_name,
            explanation=intent_data["explanation"],
            category=intent_data["category"],
            confidence=confidence,
            risk_level=risk_level,
            warnings=warnings,
        )

    def _build_unknown_goal(
        self, user_input: str, user_input_lower: str
    ) -> ProcessedGoal:
        """
        Build ProcessedGoal for an unknown/unmatched intent.

        Args:
            user_input: Original user input
            user_input_lower: Lowercase user input

        Returns:
            ProcessedGoal for unknown intent. Issue #620.
        """
        category = self._guess_category(user_input_lower)
        risk_level = self._assess_risk_level(user_input_lower, RiskLevel.LOW)

        return ProcessedGoal(
            original_goal=user_input,
            intent="unknown_goal",
            explanation=f"Unknown request: {user_input}",
            category=category,
            confidence=0.1,
            risk_level=risk_level,
            warnings=self._generate_warnings(user_input_lower, risk_level),
        )

    async def process_goal(self, user_input: str) -> ProcessedGoal:
        """
        Process a natural language goal into structured intent.

        Args:
            user_input: Natural language input from user

        Returns:
            ProcessedGoal: Processed goal with structured information
        """
        user_input_lower = user_input.lower().strip()
        logger.info("Processing goal: %s", user_input)

        best_match, best_confidence = self._find_best_intent_match(user_input_lower)

        if best_match:
            intent_name, intent_data = best_match
            return self._build_matched_goal(
                user_input, user_input_lower, intent_name, intent_data, best_confidence
            )
        else:
            return self._build_unknown_goal(user_input, user_input_lower)

    def _calculate_pattern_confidence(self, pattern: str, user_input: str) -> float:
        """Calculate confidence score for pattern match."""
        # Base confidence for regex match
        base_confidence = 0.6

        # Boost confidence based on input length and pattern specificity
        pattern_specificity = len(
            pattern.replace(r".{0,10}", "").replace(r".{0,20}", "")
        )
        input_length = len(user_input)

        # Longer, more specific patterns get higher confidence
        specificity_boost = min(0.3, pattern_specificity / 50)

        # Shorter inputs that match get higher confidence (more direct)
        length_boost = max(0, (50 - input_length) / 100)

        return min(0.95, base_confidence + specificity_boost + length_boost)

    def _assess_risk_level(self, user_input: str, base_risk: RiskLevel) -> RiskLevel:
        """Assess the risk level of the user input."""
        max_risk = base_risk

        for pattern, risk_level in self._risk_patterns.items():
            if re.search(pattern, user_input):
                if risk_level.value > max_risk.value:
                    max_risk = risk_level

        return max_risk

    def _generate_warnings(self, user_input: str, risk_level: RiskLevel) -> List[str]:
        """Generate warnings based on risk assessment."""
        warnings = []

        if risk_level == RiskLevel.CRITICAL:
            warnings.append(
                "⚠️ CRITICAL: This operation could cause " "permanent data loss"
            )
            warnings.append("Please ensure you have backups before proceeding")
        elif risk_level == RiskLevel.HIGH:
            warnings.append(
                "This operation requires elevated privileges and "
                "could affect system stability"
            )
        elif risk_level == RiskLevel.MEDIUM:
            warnings.append("This operation will make changes to your system")

        # Specific pattern warnings (Issue #380: use pre-compiled patterns)
        if _SUDO_ROOT_RE.search(user_input):
            warnings.append("Administrative privileges will be required")

        if _INSTALL_DOWNLOAD_RE.search(user_input):
            warnings.append(
                "Software will be downloaded and installed " "from external sources"
            )

        if _NETWORK_SCAN_PORT_RE.search(user_input):
            warnings.append("Network operations may be detected by security systems")

        return warnings

    def _get_category_keywords(self) -> Dict[GoalCategory, List[str]]:
        """Return category to keywords mapping for category guessing. Issue #620."""
        return {
            GoalCategory.NETWORK: [
                "network",
                "ip",
                "connect",
                "ping",
                "url",
                "port",
                "scan",
            ],
            GoalCategory.SYSTEM: [
                "system",
                "os",
                "update",
                "install",
                "service",
                "process",
            ],
            GoalCategory.FILES: [
                "file",
                "directory",
                "folder",
                "backup",
                "copy",
                "move",
            ],
            GoalCategory.DEVELOPMENT: [
                "code",
                "git",
                "build",
                "deploy",
                "docker",
                "npm",
            ],
            GoalCategory.SECURITY: [
                "security",
                "firewall",
                "password",
                "encrypt",
                "permissions",
            ],
            GoalCategory.MONITORING: ["monitor", "performance", "cpu", "memory", "log"],
        }

    def _guess_category(self, user_input: str) -> GoalCategory:
        """Guess the category for unknown goals. Issue #620."""
        category_keywords = self._get_category_keywords()
        for category, keywords in category_keywords.items():
            if any(keyword in user_input for keyword in keywords):
                return category
        return GoalCategory.UNKNOWN

    async def get_similar_intents(
        self, user_input: str, limit: int = 5
    ) -> List[ProcessedGoal]:
        """
        Get similar intents for partially understood goals.

        Args:
            user_input: Original user input
            limit: Maximum number of suggestions

        Returns:
            List[ProcessedGoal]: Similar intent suggestions
        """
        user_input_lower = user_input.lower()
        similarities = []

        for intent_name, intent_data in self._intent_patterns.items():
            # Calculate similarity with explanation text
            similarity = SequenceMatcher(
                None, user_input_lower, intent_data["explanation"].lower()
            ).ratio()

            if similarity > 0.2:  # Minimum similarity threshold
                goal = ProcessedGoal(
                    original_goal=f"Suggestion: {intent_data['explanation']}",
                    intent=intent_name,
                    explanation=intent_data["explanation"],
                    category=intent_data["category"],
                    confidence=similarity,
                    risk_level=intent_data["risk"],
                )
                similarities.append(goal)

        # Sort by similarity and return top matches
        similarities.sort(key=lambda x: x.confidence, reverse=True)
        return similarities[:limit]

    def get_supported_categories(self) -> List[str]:
        """Get list of supported goal categories."""
        return [
            category.value
            for category in GoalCategory
            if category != GoalCategory.UNKNOWN
        ]

    def get_supported_intents(self) -> List[str]:
        """Get list of supported intents."""
        return list(self._intent_patterns.keys())

    def add_custom_intent(
        self,
        intent_name: str,
        patterns: List[str],
        category: GoalCategory,
        explanation: str,
        risk_level: RiskLevel = RiskLevel.LOW,
    ):
        """
        Add a custom intent pattern.

        Args:
            intent_name: Unique intent identifier
            patterns: List of regex patterns to match
            category: Goal category
            explanation: Human-readable explanation
            risk_level: Risk level for this intent
        """
        self._intent_patterns[intent_name] = {
            "patterns": patterns,
            "category": category,
            "explanation": explanation,
            "risk": risk_level,
        }

        logger.info("Added custom intent: %s", intent_name)


if __name__ == "__main__":
    """Test the goal processor functionality."""

    async def test_processor():
        """Test goal processor with various natural language inputs."""
        processor = GoalProcessor()

        test_goals = [
            "what is my ip address?",
            "scan the network for devices",
            "update the operating system",
            "list files in current directory",
            "show system information",
            "install docker and nginx",
            "backup my home directory",
            "find all python processes",
            "check disk usage",
            "monitor system performance",
            "this is a completely unknown request",
        ]

        logger.info("=== Goal Processing Test ===")

        for goal in test_goals:
            logger.info("\nGoal: {goal}")
            logger.info("-" * 50)

            processed = await processor.process_goal(goal)

            logger.info("Intent: {processed.intent}")
            logger.info("Category: {processed.category.value}")
            logger.info("Confidence: {processed.confidence:.2f}")
            logger.info("Risk Level: {processed.risk_level.value}")
            logger.info("Explanation: {processed.explanation}")

            if processed.warnings:
                logger.info("Warnings:")
                for warning in processed.warnings:
                    logger.info("  - {warning}")

        # Test similar intents
        logger.info("\n\n=== Similar Intents Test ===")
        similar = await processor.get_similar_intents("show network info", limit=3)

        for suggestion in similar:
            print(  # noqa: print
                f"- {suggestion.explanation} "
                f"(confidence: {suggestion.confidence:.2f})"
            )

    asyncio.run(test_processor())
