# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Enhanced KB Librarian Agent - Main facade class.

Manages tool knowledge, coordinates with other agents, and handles dynamic tool
discovery. Refactored from god class into focused package (Issue #381).
"""

import asyncio
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from agents.web_research_assistant import WebResearchAssistant
from event_manager import event_manager
from knowledge_base import KnowledgeBase

from .formatters import ToolInfoFormatter
from .parsers import InstructionParser
from .processors import ResearchResultsProcessor, ResultProcessor, ToolInfoData
from .text_extraction import TextExtractor

logger = logging.getLogger(__name__)


def _build_basic_info_section(tool_info: Dict[str, Any], tool_name: str) -> str:
    """
    Build the basic information section of tool documentation.

    Extracts tool name, type, category, platform, and purpose. Issue #620.

    Args:
        tool_info: Tool information dictionary
        tool_name: Name of the tool

    Returns:
        Formatted basic information section string
    """
    return f"""TOOL DOCUMENTATION: {tool_name}
==================================================

BASIC INFORMATION:
- Name: {tool_name}
- Type: {tool_info.get('type', 'command-line tool')}
- Category: {tool_info.get('category', 'general')}
- Platform: {tool_info.get('platform', 'linux')}
- Purpose: {tool_info.get('purpose', 'N/A')}"""


def _build_installation_section(tool_info: Dict[str, Any]) -> str:
    """
    Build the installation and requirements section of tool documentation.

    Covers installation instructions and system requirements. Issue #620.

    Args:
        tool_info: Tool information dictionary

    Returns:
        Formatted installation section string
    """
    return f"""INSTALLATION:
{tool_info.get('installation', 'No installation information available')}

SYSTEM REQUIREMENTS:
{tool_info.get('requirements', 'Standard Linux system')}"""


def _build_usage_section(tool_info: Dict[str, Any]) -> str:
    """
    Build the usage and commands section of tool documentation.

    Covers basic usage, syntax, examples, and advanced usage. Issue #620.

    Args:
        tool_info: Tool information dictionary

    Returns:
        Formatted usage section string
    """
    return f"""BASIC USAGE:
{tool_info.get('usage', 'No usage information available')}

COMMAND SYNTAX:
{tool_info.get('syntax', 'See man page for syntax')}

COMMON COMMANDS & EXAMPLES:
{ToolInfoFormatter.format_command_examples(tool_info.get('command_examples', []))}

ADVANCED USAGE:
{tool_info.get('advanced_usage', 'See documentation for advanced features')}"""


def _build_troubleshooting_section(tool_info: Dict[str, Any]) -> str:
    """
    Build the troubleshooting and operational section of tool documentation.

    Covers troubleshooting, output formats, integrations, security, errors,
    performance, limitations, and related tools. Issue #620.

    Args:
        tool_info: Tool information dictionary

    Returns:
        Formatted troubleshooting section string
    """
    return f"""TROUBLESHOOTING:
{tool_info.get('troubleshooting', 'Check man page and documentation for issues')}

OUTPUT FORMATS:
{tool_info.get('output_formats', 'Standard text output')}

INTEGRATION WITH OTHER TOOLS:
{tool_info.get('integrations', 'Can be used with standard Unix tools via pipes')}

SECURITY CONSIDERATIONS:
{tool_info.get('security_notes', 'Use with appropriate permissions')}

ERROR CODES & MEANINGS:
{tool_info.get('error_codes', 'Standard Unix exit codes')}

PERFORMANCE NOTES:
{tool_info.get('performance', 'Performance varies with input size')}

KNOWN LIMITATIONS:
{tool_info.get('limitations', 'See documentation for limitations')}

RELATED TOOLS:
{tool_info.get('related_tools', [])}"""


def _build_resources_section(tool_info: Dict[str, Any]) -> str:
    """
    Build the external resources section of tool documentation.

    Covers documentation URLs, source code, tutorials, and forums. Issue #620.

    Args:
        tool_info: Tool information dictionary

    Returns:
        Formatted resources section string
    """
    return f"""EXTERNAL RESOURCES:
- Official Documentation: {tool_info.get('documentation_url', 'N/A')}
- Source Code: {tool_info.get('source_url', 'N/A')}
- Tutorial Links: {tool_info.get('tutorials', [])}
- Community Forums: {tool_info.get('forums', [])}"""


def _build_metadata_section(tool_info: Dict[str, Any]) -> str:
    """
    Build the metadata section of tool documentation.

    Covers timestamps, verification status, and usage stats. Issue #620.

    Args:
        tool_info: Tool information dictionary

    Returns:
        Formatted metadata section string
    """
    return f"""METADATA:
- Added: {datetime.now().isoformat()}
- Last Updated: {datetime.now().isoformat()}
- Verification Status: {tool_info.get('verified', 'unverified')}
- Usage Count: 0
- Success Rate: N/A
"""


def _build_tool_document_content(tool_info: Dict[str, Any], tool_name: str) -> str:
    """
    Build document content string for tool storage.

    Issue #665: Extracted from store_tool_knowledge to reduce function length.
    Issue #620: Further refactored using Extract Method pattern.

    Args:
        tool_info: Tool information dictionary
        tool_name: Name of the tool

    Returns:
        Formatted document content string
    """
    sections = [
        _build_basic_info_section(tool_info, tool_name),
        _build_installation_section(tool_info),
        _build_usage_section(tool_info),
        _build_troubleshooting_section(tool_info),
        _build_resources_section(tool_info),
        _build_metadata_section(tool_info),
    ]
    return "\n\n".join(sections)


class EnhancedKBLibrarian:
    """
    Librarian that can search KB and coordinate with other agents for tool
    discovery.

    Refactored to use focused modules for text extraction, formatting,
    and result processing (Issue #381).
    """

    def __init__(self, knowledge_base: KnowledgeBase):
        """Initialize discoverer with knowledge base, web assistant, and cache."""
        self.knowledge_base = knowledge_base
        self.web_assistant = WebResearchAssistant()
        self.tool_cache = {}
        self._cache_lock = asyncio.Lock()

    async def search_tool_knowledge(self, tool_type: str) -> Dict[str, Any]:
        """Search for tool information in KB."""
        logger.info("Searching KB for tool type: %s", tool_type)

        search_queries = [
            f"{tool_type} tool",
            f"{tool_type} command",
            f"{tool_type} utility",
            f"how to {tool_type}",
            f"{tool_type} software",
        ]

        all_results = []
        for query in search_queries:
            results = await self.knowledge_base.search(query, n_results=5)
            all_results.extend(results)

        unique_results = ResultProcessor.deduplicate_results(all_results)
        tools_found = ResultProcessor.extract_tool_info(unique_results, tool_type)

        return {
            "query": tool_type,
            "tools_found": tools_found,
            "documents_count": len(unique_results),
            "from_cache": False,
        }

    def _collect_valid_results(
        self, extraction_results: List[Any]
    ) -> List[Dict[str, Any]]:
        """Collect valid results from gather, skipping exceptions."""
        tools = []
        for result in extraction_results:
            if isinstance(result, Exception):
                continue
            tools.extend(result)
        return tools

    async def _get_detailed_tools(
        self, top_tools: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Get detailed info for top tools in parallel."""
        if not top_tools:
            return []

        tool_infos = await asyncio.gather(
            *[self._get_detailed_tool_info(tool["name"]) for tool in top_tools],
            return_exceptions=True,
        )

        detailed_tools = []
        for tool, tool_info in zip(top_tools, tool_infos):
            if isinstance(tool_info, Exception) or not tool_info:
                continue
            detailed_tools.append({**tool, **tool_info})
        return detailed_tools

    async def _process_web_research_results(
        self, tool_type: str, web_results: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Process successful web research results."""
        sources = web_results.get("sources", [])

        async def extract_from_source(source: Dict[str, Any]) -> List[Dict[str, Any]]:
            """Extract tool information from a single web source."""
            content = source.get("content", "")
            title = source.get("title", "")
            return ResultProcessor.extract_tools_from_content(content, title, tool_type)

        extraction_results = await asyncio.gather(
            *[extract_from_source(source) for source in sources[:5]],
            return_exceptions=True,
        )

        tools = self._collect_valid_results(extraction_results)
        unique_tools = ResultProcessor.deduplicate_tools(tools)
        return await self._get_detailed_tools(unique_tools[:3])

    async def request_tool_research(self, tool_type: str) -> List[Dict[str, Any]]:
        """Ask WebAssistant to research tools when KB doesn't have info (thread-safe)."""
        logger.info("Requesting web research for tool type: %s", tool_type)

        async with self._cache_lock:
            if tool_type in self.tool_cache:
                logger.info("Returning cached results for %s", tool_type)
                return list(self.tool_cache[tool_type])

        research_query = f"best {tool_type} tools linux command line"
        web_results = await self.web_assistant.research_query(research_query)

        if web_results.get("status") != "success":
            logger.error("Web research failed for %s", tool_type)
            return []

        detailed_tools = await self._process_web_research_results(
            tool_type, web_results
        )

        async with self._cache_lock:
            self.tool_cache[tool_type] = detailed_tools

        await self._store_tool_research_results(tool_type, detailed_tools)
        return detailed_tools

    async def store_tool_knowledge(self, tool_info: Dict[str, Any]):
        """
        Store comprehensive tool information and documentation in KB.

        Issue #665: Refactored to use _build_tool_document_content helper.
        """
        tool_name = tool_info.get("name", "unknown")
        document_content = _build_tool_document_content(tool_info, tool_name)

        metadata = {
            "tool_name": tool_name,
            "category": "tools",
            "type": "tool_documentation",
            "source": "web_research",
            "timestamp": datetime.now().isoformat(),
        }

        await self.knowledge_base.store_fact(document_content, metadata=metadata)
        logger.info("Stored knowledge for tool: %s", tool_name)

        await event_manager.publish(
            "knowledge_update",
            {
                "type": "new_tool",
                "tool_name": tool_name,
                "message": f"Added knowledge about {tool_name} to the knowledge base",
            },
        )

    async def get_tool_instructions(self, tool_name: str) -> Dict[str, Any]:
        """Get installation and usage instructions for a specific tool."""
        search_results = await self.knowledge_base.search(
            f"{tool_name} installation usage", n_results=3
        )

        if search_results:
            instructions = InstructionParser.extract_instructions(
                search_results, tool_name
            )
            if instructions:
                return instructions

        logger.info("Tool %s not found in KB, researching...", tool_name)
        tool_info = await self._research_specific_tool(tool_name)

        if tool_info:
            tool_dict = (
                tool_info.to_dict() if hasattr(tool_info, "to_dict") else tool_info
            )
            await self.store_tool_knowledge(tool_dict)
            return tool_dict

        return {"name": tool_name, "error": "Could not find instructions for this tool"}

    async def _research_specific_tool(self, tool_name: str) -> Optional[ToolInfoData]:
        """Research a specific tool comprehensively."""
        research_queries = {
            "installation": f"how to install {tool_name} linux ubuntu debian",
            "usage": f"{tool_name} tutorial examples command line",
            "advanced": f"{tool_name} advanced usage options flags",
            "troubleshooting": f"{tool_name} common errors problems solutions",
            "integration": f"{tool_name} integration with other tools pipes",
            "security": f"{tool_name} security considerations best practices",
        }

        async def execute_query(query_type: str, query: str) -> tuple:
            """Execute a single research query and return typed result tuple."""
            try:
                result = await self.web_assistant.research_query(query)
                if result.get("status") == "success":
                    return (query_type, result)
                return (query_type, None)
            except Exception as e:
                logger.debug("Research query failed for %s: %s", query_type, e)
                return (query_type, None)

        query_results = await asyncio.gather(
            *[execute_query(qt, q) for qt, q in research_queries.items()],
            return_exceptions=True,
        )

        results = {}
        for item in query_results:
            if isinstance(item, Exception):
                continue
            query_type, result = item
            if result is not None:
                results[query_type] = result

        if not results:
            return None

        processor = ResearchResultsProcessor(tool_name, results)
        tool_type = self._determine_tool_type(tool_name)
        category = self._categorize_tool(tool_name, "")
        tool_info = processor.build_tool_info(tool_type, category)

        return tool_info

    def _determine_tool_type(self, tool_name: str) -> str:
        """Determine tool type based on name patterns."""
        type_patterns = {
            "steganography": ["steghide", "zsteg", "outguess", "jsteg"],
            "file_analysis": ["binwalk", "foremost", "scalpel", "photorec"],
            "network": ["nmap", "netcat", "wireshark", "tcpdump"],
            "forensics": ["volatility", "rekall", "autopsy", "sleuthkit"],
            "security": ["metasploit", "burpsuite", "sqlmap", "nikto"],
            "system": ["htop", "iftop", "lso", "strace"],
            "development": ["git", "gcc", "make", "docker"],
        }

        for tool_type, tools in type_patterns.items():
            if tool_name.lower() in tools:
                return tool_type
        return "command-line tool"

    def _categorize_tool(self, tool_name: str, description: str) -> str:
        """Categorize tool based on name and description."""
        categories = {
            "network": ["network", "port", "scan", "tcp", "udp", "ip", "ethernet"],
            "security": [
                "security",
                "vulnerability",
                "exploit",
                "penetration",
                "audit",
            ],
            "monitoring": ["monitor", "watch", "track", "observe", "metric"],
            "file": ["file", "directory", "search", "find", "locate"],
            "system": ["system", "process", "cpu", "memory", "disk"],
            "development": ["git", "compile", "build", "debug", "development"],
        }

        text = (tool_name + " " + description).lower()

        for category, keywords in categories.items():
            if any(keyword in text for keyword in keywords):
                return category

        return "general"

    async def _store_tool_research_results(
        self, tool_type: str, tools: List[Dict[str, Any]]
    ):
        """Store research results in KB for future use."""
        if not tools:
            return

        tool_summaries = [
            f"""
{i}. {tool['name']}
   Purpose: {tool.get('purpose', 'N/A')}
   Installation: {tool.get('installation', 'N/A')[:200]}...
"""
            for i, tool in enumerate(tools, 1)
        ]

        summary_content = f"""
Tool Research Results: {tool_type}
Date: {datetime.now().isoformat()}

Found {len(tools)} tools for {tool_type}:

{"".join(tool_summaries)}
"""

        metadata = {
            "type": "tool_research_summary",
            "tool_type": tool_type,
            "tools_count": len(tools),
            "timestamp": datetime.now().isoformat(),
        }

        await self.knowledge_base.store_fact(summary_content, metadata=metadata)

        for tool in tools:
            await self.store_tool_knowledge(tool)

    async def _get_detailed_tool_info(self, tool_name: str) -> Optional[Dict[str, Any]]:
        """Get detailed information about a specific tool."""
        query = f"{tool_name} tool description features"
        results = await self.web_assistant.research_query(query)

        if results.get("status") == "success" and results.get("summary"):
            summary = results["summary"]

            info = {
                "purpose": TextExtractor.extract_purpose(summary, tool_name),
                "features": TextExtractor.extract_features(summary),
                "platform": "linux",
                "category": self._categorize_tool(tool_name, summary),
            }

            return info

        return None

    def _build_system_doc_header(
        self, doc_title: str, doc_type: str, doc_info: Dict[str, Any]
    ) -> str:
        """
        Build the header section of system documentation content.

        Args:
            doc_title: Title of the documentation.
            doc_type: Type of documentation.
            doc_info: Full documentation info dictionary.

        Returns:
            Formatted header section string.

        Issue #620.
        """
        return f"""
SYSTEM DOCUMENTATION: {doc_title}
==================================================

TYPE: {doc_type}
CATEGORY: {doc_info.get('category', 'system')}

OVERVIEW:
{doc_info.get('overview', 'No overview available')}

PROCEDURES:
{ToolInfoFormatter.format_procedures(doc_info.get('procedures', []))}

PREREQUISITES:
{doc_info.get('prerequisites', 'None specified')}

STEP-BY-STEP GUIDE:
{ToolInfoFormatter.format_steps(doc_info.get('steps', []))}
"""

    def _build_system_doc_footer(self, doc_info: Dict[str, Any]) -> str:
        """
        Build the footer section of system documentation content.

        Args:
            doc_info: Full documentation info dictionary.

        Returns:
            Formatted footer section string.

        Issue #620.
        """
        timestamp = datetime.now().isoformat()
        return f"""
COMMON ISSUES & SOLUTIONS:
{ToolInfoFormatter.format_troubleshooting(doc_info.get('common_issues', []))}

BEST PRACTICES:
{ToolInfoFormatter.format_best_practices(doc_info.get('best_practices', []))}

RELATED DOCUMENTATION:
{doc_info.get('related_docs', [])}

EXAMPLES:
{ToolInfoFormatter.format_documentation_examples(doc_info.get('examples', []))}

VERIFICATION STEPS:
{ToolInfoFormatter.format_verification_steps(doc_info.get('verification', []))}

METADATA:
- Added: {timestamp}
- Last Updated: {timestamp}
- Verification Status: {doc_info.get('verified', 'unverified')}
- Complexity Level: {doc_info.get('complexity', 'medium')}
"""

    def _build_system_doc_content(
        self, doc_title: str, doc_type: str, doc_info: Dict[str, Any]
    ) -> str:
        """
        Build the full document content string for system documentation.

        Args:
            doc_title: Title of the documentation.
            doc_type: Type of documentation.
            doc_info: Full documentation info dictionary.

        Returns:
            Formatted document content string.

        Issue #620.
        """
        header = self._build_system_doc_header(doc_title, doc_type, doc_info)
        footer = self._build_system_doc_footer(doc_info)
        return header + footer

    def _build_system_doc_metadata(
        self, doc_title: str, doc_type: str, doc_info: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Build metadata dictionary for system documentation storage.

        Args:
            doc_title: Title of the documentation.
            doc_type: Type of documentation.
            doc_info: Full documentation info dictionary.

        Returns:
            Metadata dictionary for storage.

        Issue #620.
        """
        return {
            "type": "system_documentation",
            "doc_type": doc_type,
            "category": doc_info.get("category", "system"),
            "title": doc_title,
            "timestamp": datetime.now().isoformat(),
        }

    async def store_system_documentation(self, doc_info: Dict[str, Any]):
        """
        Store general system documentation and procedures.

        Args:
            doc_info: Documentation information dictionary.

        Issue #620: Refactored to use extracted helper methods.
        """
        doc_type = doc_info.get("type", "general")
        doc_title = doc_info.get("title", "System Documentation")

        document_content = self._build_system_doc_content(doc_title, doc_type, doc_info)
        metadata = self._build_system_doc_metadata(doc_title, doc_type, doc_info)

        await self.knowledge_base.store_fact(document_content, metadata=metadata)
        logger.info("Stored system documentation: %s", doc_title)

    def _build_workflow_document_content(
        self, workflow_name: str, workflow_info: Dict[str, Any]
    ) -> str:
        """
        Build the document content string for workflow documentation.

        Issue #620.
        """
        timestamp = datetime.now().isoformat()
        return f"""
WORKFLOW DOCUMENTATION: {workflow_name}
==================================================

WORKFLOW TYPE: {workflow_info.get('type', 'general')}
COMPLEXITY: {workflow_info.get('complexity', 'medium')}
ESTIMATED TIME: {workflow_info.get('estimated_time', 'varies')}

OBJECTIVE:
{workflow_info.get('objective', 'No objective specified')}

PREREQUISITES:
{ToolInfoFormatter.format_prerequisites(workflow_info.get('prerequisites', []))}

REQUIRED TOOLS:
{ToolInfoFormatter.format_tool_requirements(workflow_info.get('required_tools', []))}

WORKFLOW STEPS:
{ToolInfoFormatter.format_workflow_steps(workflow_info.get('workflow_steps', []))}

DECISION POINTS:
{ToolInfoFormatter.format_decision_points(workflow_info.get('decision_points', []))}

OUTPUT/DELIVERABLES:
{workflow_info.get('deliverables', 'Process completion')}

QUALITY CHECKS:
{ToolInfoFormatter.format_quality_checks(workflow_info.get('quality_checks', []))}

COMMON PITFALLS:
{ToolInfoFormatter.format_pitfalls(workflow_info.get('pitfalls', []))}

ALTERNATIVE APPROACHES:
{ToolInfoFormatter.format_alternatives(workflow_info.get('alternatives', []))}

RELATED WORKFLOWS:
{workflow_info.get('related_workflows', [])}

METADATA:
- Added: {timestamp}
- Last Updated: {timestamp}
- Success Rate: {workflow_info.get('success_rate', 'N/A')}
- Difficulty Level: {workflow_info.get('difficulty', 'medium')}
"""

    def _build_workflow_metadata(
        self, workflow_name: str, workflow_info: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Build metadata dictionary for workflow documentation.

        Issue #620.
        """
        return {
            "type": "workflow_documentation",
            "workflow_name": workflow_name,
            "category": workflow_info.get("category", "workflows"),
            "complexity": workflow_info.get("complexity", "medium"),
            "timestamp": datetime.now().isoformat(),
        }

    async def store_workflow_knowledge(self, workflow_info: Dict[str, Any]):
        """Store complete workflow documentation for complex procedures."""
        workflow_name = workflow_info.get("name", "Unknown Workflow")

        document_content = self._build_workflow_document_content(
            workflow_name, workflow_info
        )
        metadata = self._build_workflow_metadata(workflow_name, workflow_info)

        await self.knowledge_base.store_fact(document_content, metadata=metadata)
        logger.info("Stored workflow documentation: %s", workflow_name)


__all__ = ["EnhancedKBLibrarian"]
