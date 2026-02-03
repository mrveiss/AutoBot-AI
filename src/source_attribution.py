# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Source Attribution and Transparency System
Tracks and formats information sources for all responses
"""

import gc
import json
import logging
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Union

logger = logging.getLogger(__name__)


class SourceType(Enum):
    """Types of information sources"""

    KNOWLEDGE_BASE = "knowledge_base"
    WEB_SEARCH = "web_search"
    SYSTEM_STATE = "system_state"
    TOOL_OUTPUT = "tool_output"
    LLM_TRAINING = "llm_training"
    USER_INPUT = "user_input"
    CONFIGURATION = "configuration"
    DOCUMENTATION = "documentation"
    API_RESPONSE = "api_response"
    FILE_CONTENT = "file_content"


class SourceReliability(Enum):
    """Reliability levels for sources"""

    VERIFIED = "verified"  # System state, tool output
    HIGH = "high"  # KB, official docs
    MEDIUM = "medium"  # Web search, API responses
    LOW = "low"  # User input, unverified sources
    UNKNOWN = "unknown"  # Cannot determine reliability


@dataclass
class Source:
    """Represents a single information source"""

    type: SourceType
    reliability: SourceReliability
    content: str
    timestamp: datetime
    metadata: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        return {
            "type": self.type.value,
            "reliability": self.reliability.value,
            "content": self.content,
            "timestamp": self.timestamp.isoformat(),
            "metadata": self.metadata,
        }

    def format_citation(self) -> str:
        """Format source as a citation string"""
        source_icon = {
            SourceType.KNOWLEDGE_BASE: "📚",
            SourceType.WEB_SEARCH: "🌐",
            SourceType.SYSTEM_STATE: "💻",
            SourceType.TOOL_OUTPUT: "🔧",
            SourceType.LLM_TRAINING: "🤖",
            SourceType.USER_INPUT: "👤",
            SourceType.CONFIGURATION: "⚙️",
            SourceType.DOCUMENTATION: "📖",
            SourceType.API_RESPONSE: "🔌",
            SourceType.FILE_CONTENT: "📄",
        }

        icon = source_icon.get(self.type, "📋")

        # Build citation
        citation = f"{icon} "

        # Add source name
        if "name" in self.metadata:
            citation += f"{self.metadata['name']}"
        else:
            citation += f"{self.type.value.replace('_', ' ').title()}"

        # Add specific identifiers
        if "kb_entry_id" in self.metadata:
            citation += f" (KB #{self.metadata['kb_entry_id']})"
        elif "url" in self.metadata:
            citation += f" ({self.metadata['url']})"
        elif "file_path" in self.metadata:
            citation += f" ({self.metadata['file_path']})"
        elif "command" in self.metadata:
            citation += f" (Command: {self.metadata['command']})"

        # Add confidence if available
        if "confidence" in self.metadata:
            citation += f" [{self.metadata['confidence']:.0%} confidence]"

        return citation


class SourceAttributionManager:
    """Manages source attribution for responses"""

    def __init__(self):
        """Initialize source attribution manager with source tracking and limits."""
        self.sources: List[Source] = []
        self.current_response_sources: List[Source] = []
        # Memory leak protection - configurable limits
        self.max_sources = 1000  # Maximum total sources to keep
        self.cleanup_threshold = 1200  # Trigger cleanup at 120% of limit

    def add_source(
        self,
        source_type: Union[SourceType, str],
        content: str,
        reliability: Union[SourceReliability, str] = SourceReliability.UNKNOWN,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Source:
        """Add a new source to the current response"""
        # Handle string inputs
        if isinstance(source_type, str):
            source_type = SourceType(source_type)
        if isinstance(reliability, str):
            reliability = SourceReliability(reliability)

        source = Source(
            type=source_type,
            reliability=reliability,
            content=content[:500],  # Limit content length
            timestamp=datetime.now(),
            metadata=metadata or {},
        )

        self.current_response_sources.append(source)
        self.sources.append(source)

        # Prevent memory leak by cleaning up old sources
        self._cleanup_sources_if_needed()

        logger.debug("Added source: %s", source.format_citation())
        return source

    def _cleanup_sources_if_needed(self):
        """Clean up old sources to prevent memory leaks"""
        if len(self.sources) > self.cleanup_threshold:
            # Keep most recent sources within the limit
            old_count = len(self.sources)
            self.sources = self.sources[-self.max_sources :]
            # Force garbage collection to free memory immediately
            gc.collect()
            logger.info(
                "SOURCE CLEANUP: Trimmed sources from %d to %d (limit: %d) and freed memory",
                old_count,
                len(self.sources),
                self.max_sources,
            )

    def add_kb_source(
        self,
        content: str,
        entry_id: str,
        confidence: float = 1.0,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Source:
        """Add a Knowledge Base source"""
        kb_metadata = {
            "kb_entry_id": entry_id,
            "confidence": confidence,
            **(metadata or {}),
        }

        return self.add_source(
            SourceType.KNOWLEDGE_BASE, content, SourceReliability.HIGH, kb_metadata
        )

    def add_web_source(
        self,
        content: str,
        url: str,
        title: Optional[str] = None,
        domain_reliability: Optional[str] = None,
    ) -> Source:
        """Add a web search source"""
        reliability = SourceReliability.MEDIUM
        if domain_reliability == "official":
            reliability = SourceReliability.HIGH
        elif domain_reliability == "unknown":
            reliability = SourceReliability.LOW

        web_metadata = {
            "url": url,
            "title": title or url,
            "domain_reliability": domain_reliability,
        }

        return self.add_source(
            SourceType.WEB_SEARCH, content, reliability, web_metadata
        )

    def add_system_source(
        self, content: str, command: Optional[str] = None, output_type: str = "command"
    ) -> Source:
        """Add a system/tool output source"""
        system_metadata = {"output_type": output_type}
        if command:
            system_metadata["command"] = command

        return self.add_source(
            (
                SourceType.SYSTEM_STATE
                if output_type == "state"
                else SourceType.TOOL_OUTPUT
            ),
            content,
            SourceReliability.VERIFIED,
            system_metadata,
        )

    def format_attribution_block(self) -> str:
        """Format all current sources as an attribution block"""
        if not self.current_response_sources:
            return ""

        lines = ["📋 **Sources:**"]

        # Group by type
        by_type: Dict[SourceType, List[Source]] = {}
        for source in self.current_response_sources:
            if source.type not in by_type:
                by_type[source.type] = []
            by_type[source.type].append(source)

        # Format each type
        for source_type, sources in by_type.items():
            for source in sources:
                lines.append(f"- {source.format_citation()}")

        return "\n".join(lines)

    def get_reliability_summary(self) -> Dict[str, int]:
        """Get count of sources by reliability level"""
        summary = {}
        for source in self.current_response_sources:
            level = source.reliability.value
            summary[level] = summary.get(level, 0) + 1
        return summary

    def clear_current_sources(self):
        """Clear sources for current response (keep history)"""
        self.current_response_sources = []

    def to_json(self) -> str:
        """Export current sources as JSON"""
        return json.dumps(
            [s.to_dict() for s in self.current_response_sources], indent=2
        )


# Global instance
source_manager = SourceAttributionManager()


def track_source(source_type: Union[SourceType, str], content: str, **kwargs) -> Source:
    """Convenience function to track a source"""
    return source_manager.add_source(source_type, content, **kwargs)


def get_attribution() -> str:
    """Get formatted attribution for current response"""
    return source_manager.format_attribution_block()


def clear_sources():
    """Clear current response sources"""
    source_manager.clear_current_sources()
