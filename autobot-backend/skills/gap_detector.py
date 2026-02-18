# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Skill Gap Detector (Phase 4)

Identifies when AutoBot lacks a capability by monitoring agent outputs
and failed tool calls.
"""
import logging
import re
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional, Set

logger = logging.getLogger(__name__)

_EXPLICIT_PATTERNS = [
    r"i don't have a tool (to|for) (.+?)[\.\n]",
    r"i cannot (.+?) because (i lack|there is no|no tool)",
    r"no skill (available|exists) (for|to) (.+?)[\.\n]",
    r"capability unavailable[:\s]+(.+?)[\.\n]",
    r"i need a? ?(.+?) skill to",
]

_USER_HINT_PATTERNS = [
    r"can you (.+?)\?",
    r"please (.+?) for me",
    r"i need you to (.+)",
]


class GapTrigger(str, Enum):
    """Source event that triggered a capability gap detection."""

    EXPLICIT = "explicit"  # agent said "I don't have a tool for..."
    FAILED_CALL = "failed_call"  # tool_call resolved to no handler
    USER_HINT = "user_hint"  # user requested something no skill covers


@dataclass
class GapResult:
    """Result of a capability gap detection event."""

    trigger: GapTrigger
    capability: str  # human-readable description of missing capability
    context: Dict[str, Any]  # original event data for the generator


class SkillGapDetector:
    """Analyzes agent output and tool events to detect capability gaps."""

    def __init__(self, available_tools: List[str]) -> None:
        """Initialize with the set of currently available tool names."""
        self.available_tools: Set[str] = set(available_tools)

    def analyze_agent_output(self, text: str) -> Optional[GapResult]:
        """Scan agent output text for explicit gap signals."""
        lower = text.lower()
        for pattern in _EXPLICIT_PATTERNS:
            match = re.search(pattern, lower)
            if match:
                capability = _extract_capability(match)
                return GapResult(
                    trigger=GapTrigger.EXPLICIT,
                    capability=capability,
                    context={"agent_output": text[:500]},
                )
        return None

    def analyze_failed_tool_call(
        self, tool_name: str, args: Dict[str, Any]
    ) -> Optional[GapResult]:
        """Detect gap when a requested tool doesn't exist in available_tools."""
        if tool_name in self.available_tools:
            return None
        return GapResult(
            trigger=GapTrigger.FAILED_CALL,
            capability=f"tool named '{tool_name}' with args {list(args.keys())}",
            context={"tool_name": tool_name, "args": args},
        )

    def analyze_user_message(self, message: str) -> Optional[GapResult]:
        """Detect when user requests something no existing skill covers."""
        lower = message.lower()
        for pattern in _USER_HINT_PATTERNS:
            match = re.search(pattern, lower)
            if match:
                action = match.group(1).strip()
                if not self._any_tool_matches(action):
                    return GapResult(
                        trigger=GapTrigger.USER_HINT,
                        capability=action,
                        context={"user_message": message},
                    )
        return None

    def _any_tool_matches(self, action: str) -> bool:
        """Return True if any word in action appears in a known tool name."""
        words = set(action.split())
        return any(any(w in tool for w in words) for tool in self.available_tools)


def _extract_capability(match: re.Match) -> str:
    """Extract the capability description from a regex match object."""
    groups = [g for g in match.groups() if g and len(g) > 3]
    return groups[-1].strip() if groups else match.group(0)
