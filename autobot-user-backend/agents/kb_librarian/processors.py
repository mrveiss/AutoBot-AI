# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Result processors for KB Librarian search and research operations.

Extracted from enhanced_kb_librarian.py as part of Issue #381 god class refactoring.
"""

import re
from typing import Any, Dict, List

from .text_extraction import TextExtractor
from .types import (
    LIMITATION_KEYWORDS,
    OFFICIAL_DOC_DOMAINS,
    PERFORMANCE_KEYWORDS,
    TOOL_INFO_OPTIONAL_FIELDS,
)


class ResultProcessor:
    """Helper class for processing search results and extracting data."""

    @classmethod
    def find_official_docs(cls, results: Dict[str, Any]) -> str:
        """Find official documentation URLs from research results."""
        for result in results.values():
            sources = result.get("sources", [])
            for source in sources:
                url = source.get("url", "")
                if any(domain in url for domain in OFFICIAL_DOC_DOMAINS):
                    return url
        return "N/A"

    @classmethod
    def extract_limitations(cls, results: Dict[str, Any]) -> str:
        """Extract tool limitations from research."""
        limitations = []
        for result in results.values():
            summary = result.get("summary", "")
            lines = summary.split("\n")
            for line in lines:
                if any(word in line.lower() for word in LIMITATION_KEYWORDS):
                    limitations.append(line.strip())

        return (
            "\n".join(limitations[:3])
            if limitations
            else "See documentation for limitations"
        )

    @classmethod
    def extract_performance_notes(cls, results: Dict[str, Any]) -> str:
        """Extract performance-related information."""
        perf_notes = []
        for result in results.values():
            summary = result.get("summary", "")
            lines = summary.split("\n")
            for line in lines:
                if any(word in line.lower() for word in PERFORMANCE_KEYWORDS):
                    perf_notes.append(line.strip())

        return (
            "\n".join(perf_notes[:3])
            if perf_notes
            else "Performance varies with input size"
        )

    @classmethod
    def extract_tool_info(
        cls, results: List[Dict], tool_type: str
    ) -> List[Dict[str, Any]]:
        """Extract tool information from KB search results."""
        tools = []

        for result in results:
            content = result.get("content", "")
            metadata = result.get("metadata", {})

            if metadata.get("type") == "tool_documentation":
                tool_name = metadata.get("tool_name")
                if tool_name:
                    tools.append(
                        {
                            "name": tool_name,
                            "source": "knowledge_base",
                            "confidence": result.get("score", 0.5),
                            "content": content,
                        }
                    )

        return tools

    @classmethod
    def extract_tools_from_content(
        cls, content: str, title: str, tool_type: str
    ) -> List[Dict[str, Any]]:
        """Extract tool names and descriptions from web content."""
        tools = []

        tool_patterns = {
            "network scan": ["nmap", "masscan", "zmap", "angry ip scanner", "arp-scan"],
            "port scan": ["nmap", "masscan", "netcat", "nc", "telnet"],
            "web scraping": ["wget", "curl", "httrack", "scrapy", "beautifulsoup"],
            "file search": ["find", "locate", "grep", "ag", "ripgrep", "fd"],
            "process monitor": ["htop", "top", "ps", "pstree", "lso"],
            "disk usage": ["d", "du", "ncdu", "baobab", "qdirstat"],
            "network monitor": ["iftop", "nethogs", "vnstat", "bmon", "nload"],
        }

        patterns = tool_patterns.get(tool_type.lower(), [])

        content_lower = content.lower()
        for pattern in patterns:
            if pattern in content_lower:
                start = max(0, content_lower.find(pattern) - 50)
                end = min(
                    len(content), content_lower.find(pattern) + len(pattern) + 100
                )
                context = content[start:end]

                tools.append(
                    {"name": pattern, "context": context, "source_title": title}
                )

        return tools

    @classmethod
    def deduplicate_results(cls, results: List[Dict]) -> List[Dict]:
        """Deduplicate search results based on content similarity."""
        unique = []
        seen_content = set()

        for result in results:
            content_hash = hash(result.get("content", "")[:100])
            if content_hash not in seen_content:
                seen_content.add(content_hash)
                unique.append(result)

        return unique

    @classmethod
    def deduplicate_tools(cls, tools: List[Dict]) -> List[Dict]:
        """Deduplicate tool list."""
        unique_tools = {}

        for tool in tools:
            name = tool["name"]
            if name not in unique_tools:
                unique_tools[name] = tool
            else:
                existing = unique_tools[name]
                if len(tool.get("context", "")) > len(existing.get("context", "")):
                    unique_tools[name] = tool

        return list(unique_tools.values())


class ToolInfoData:
    """Data class for tool information - encapsulates tool data with methods."""

    def __init__(self, name: str, tool_type: str = "command-line tool"):
        """Initialize tool info with name, type, and default metadata fields."""
        self.name = name
        self.type = tool_type
        self.category = "general"
        self.platform = "linux"
        self.purpose = None
        self.installation = None
        self.requirements = None
        self.package_name = None
        self.usage = None
        self.syntax = None
        self.command_examples = []
        self.output_formats = None
        self.advanced_usage = None
        self.features = None
        self.troubleshooting = None
        self.error_codes = None
        self.common_issues = []
        self.integrations = None
        self.related_tools = []
        self.security_notes = None
        self.best_practices = []
        self.documentation_url = None
        self.verified = "unverified"
        self.limitations = None
        self.performance = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        result = {
            "name": self.name,
            "type": self.type,
            "category": self.category,
            "platform": self.platform,
        }
        for key in TOOL_INFO_OPTIONAL_FIELDS:
            val = getattr(self, key, None)
            if val is not None:
                result[key] = val
        if self.command_examples:
            result["command_examples"] = self.command_examples
        if self.common_issues:
            result["common_issues"] = self.common_issues
        if self.related_tools:
            result["related_tools"] = self.related_tools
        if self.best_practices:
            result["best_practices"] = self.best_practices
        return result

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ToolInfoData":
        """Create from dictionary."""
        tool = cls(data.get("name", "unknown"), data.get("type", "command-line tool"))
        for key, value in data.items():
            if hasattr(tool, key):
                setattr(tool, key, value)
        return tool


class ResearchResultsProcessor:
    """Processes web research results into structured tool information."""

    def __init__(self, tool_name: str, results: Dict[str, Any]):
        """Initialize processor with tool name and raw research results."""
        self.tool_name = tool_name
        self.results = results

    def build_tool_info(self, tool_type: str, category: str) -> ToolInfoData:
        """Build comprehensive tool info from research results."""
        tool = ToolInfoData(self.tool_name, tool_type)
        tool.category = category

        # Process installation results
        if "installation" in self.results:
            summary = self.results["installation"].get("summary", "")
            tool.installation = TextExtractor.extract_installation_commands(summary)
            tool.requirements = TextExtractor.extract_requirements(summary)
            tool.package_name = self._determine_package_name(summary)

        # Process usage results
        if "usage" in self.results:
            summary = self.results["usage"].get("summary", "")
            tool.usage = summary
            tool.syntax = TextExtractor.extract_command_syntax(summary)
            tool.command_examples = TextExtractor.extract_detailed_examples(summary)
            tool.output_formats = TextExtractor.extract_output_formats(summary)

        # Process advanced results
        if "advanced" in self.results:
            summary = self.results["advanced"].get("summary", "")
            tool.advanced_usage = summary
            tool.features = TextExtractor.extract_advanced_features(summary)

        # Process troubleshooting results
        if "troubleshooting" in self.results:
            summary = self.results["troubleshooting"].get("summary", "")
            tool.troubleshooting = summary
            tool.error_codes = TextExtractor.extract_error_codes(summary)
            tool.common_issues = TextExtractor.extract_common_issues(summary)

        # Process integration results
        if "integration" in self.results:
            summary = self.results["integration"].get("summary", "")
            tool.integrations = summary
            tool.related_tools = TextExtractor.extract_related_tools(summary)

        # Process security results
        if "security" in self.results:
            summary = self.results["security"].get("summary", "")
            tool.security_notes = summary
            tool.best_practices = TextExtractor.extract_security_practices(summary)

        # Add metadata
        tool.documentation_url = ResultProcessor.find_official_docs(self.results)
        tool.verified = "web_research"
        tool.limitations = ResultProcessor.extract_limitations(self.results)
        tool.performance = ResultProcessor.extract_performance_notes(self.results)

        return tool

    def _determine_package_name(self, installation_text: str) -> str:
        """Determine package name from tool name and installation text."""
        package_mappings = {
            "nmap": "nmap",
            "netcat": "netcat",
            "nc": "netcat",
            "wireshark": "wireshark",
            "tcpdump": "tcpdump",
            "curl": "curl",
            "wget": "wget",
            "git": "git",
            "docker": "docker.io",
            "python": "python3",
            "pip": "python3-pip",
            "node": "nodejs",
            "npm": "npm",
        }

        if self.tool_name.lower() in package_mappings:
            return package_mappings[self.tool_name.lower()]

        install_pattern = (
            r"(?:apt|apt-get|yum|dnf|pacman|brew|pip|npm)\s+install\s+(?:-[yS]\s+)?(\S+)"
        )
        match = re.search(install_pattern, installation_text)
        if match:
            return match.group(1)

        return self.tool_name.lower()


__all__ = ["ResultProcessor", "ToolInfoData", "ResearchResultsProcessor"]
