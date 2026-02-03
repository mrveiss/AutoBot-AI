"""
Enhanced KB Librarian Agent for AutoBot
Manages tool knowledge, coordinates with other agents, and handles dynamic tool
discovery
"""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from src.agents.web_research_assistant import WebResearchAssistant
from src.event_manager import event_manager
from src.knowledge_base import KnowledgeBase

logger = logging.getLogger(__name__)


class EnhancedKBLibrarian:
    """
    Librarian that can search KB and coordinate with other agents for tool
    discovery
    """

    def __init__(self, knowledge_base: KnowledgeBase):
        self.knowledge_base = knowledge_base
        self.web_assistant = WebResearchAssistant()
        self.tool_cache = {}  # Cache for frequently requested tools

    async def search_tool_knowledge(self, tool_type: str) -> Dict[str, Any]:
        """Search for tool information in KB"""
        logger.info(f"Searching KB for tool type: {tool_type}")

        # Search variations
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

        # Deduplicate and rank results
        unique_results = self._deduplicate_results(all_results)

        # Extract tool information from results
        tools_found = self._extract_tool_info(unique_results, tool_type)

        return {
            "query": tool_type,
            "tools_found": tools_found,
            "documents_count": len(unique_results),
            "from_cache": False,
        }

    async def request_tool_research(self, tool_type: str) -> List[Dict[str, Any]]:
        """Ask WebAssistant to research tools when KB doesn't have info"""
        logger.info(f"Requesting web research for tool type: {tool_type}")

        # Check cache first
        if tool_type in self.tool_cache:
            logger.info(f"Returning cached results for {tool_type}")
            return self.tool_cache[tool_type]

        # Research tools on the web
        research_query = f"best {tool_type} tools linux command line"
        web_results = await self.web_assistant.research_query(research_query)

        if web_results.get("status") == "success":
            tools = []
            sources = web_results.get("sources", [])

            # Extract tool mentions from search results
            for source in sources[:5]:  # Top 5 results
                content = source.get("content", "")
                title = source.get("title", "")

                # Look for tool names and descriptions
                extracted_tools = await self._extract_tools_from_content(
                    content, title, tool_type
                )
                tools.extend(extracted_tools)

            # Deduplicate tools
            unique_tools = self._deduplicate_tools(tools)

            # Get detailed information for each tool
            detailed_tools = []
            for tool in unique_tools[:3]:  # Top 3 tools
                tool_info = await self._get_detailed_tool_info(tool["name"])
                if tool_info:
                    detailed_tools.append({**tool, **tool_info})

            # Cache results
            self.tool_cache[tool_type] = detailed_tools

            # Store in KB for future use
            await self._store_tool_research_results(tool_type, detailed_tools)

            return detailed_tools
        else:
            logger.error(f"Web research failed for {tool_type}")
            return []

    async def store_tool_knowledge(self, tool_info: Dict[str, Any]):
        """Store comprehensive tool information and documentation in KB. Issue #620."""
        tool_name = tool_info.get("name", "unknown")
        document_content = self._build_tool_document(tool_info, tool_name)
        metadata = self._build_tool_metadata(tool_name)

        await self.knowledge_base.store_fact(document_content, metadata=metadata)
        logger.info(f"Stored knowledge for tool: {tool_name}")

        await self._publish_tool_knowledge_event(tool_name)

    def _build_tool_document(self, tool_info: Dict[str, Any], tool_name: str) -> str:
        """Build comprehensive structured document for a tool. Issue #620."""
        sections = [
            self._build_tool_header(tool_info, tool_name),
            self._build_tool_installation_section(tool_info),
            self._build_tool_usage_section(tool_info),
            self._build_tool_advanced_section(tool_info),
            self._build_tool_resources_section(tool_info),
            self._build_tool_metadata_section(tool_info),
        ]
        return "\n".join(sections)

    def _build_tool_header(self, tool_info: Dict[str, Any], tool_name: str) -> str:
        """Build tool document header with basic information. Issue #620."""
        return f"""
TOOL DOCUMENTATION: {tool_name}
==================================================

BASIC INFORMATION:
- Name: {tool_name}
- Type: {tool_info.get('type', 'command-line tool')}
- Category: {tool_info.get('category', 'general')}
- Platform: {tool_info.get('platform', 'linux')}
- Purpose: {tool_info.get('purpose', 'N/A')}"""

    def _build_tool_installation_section(self, tool_info: Dict[str, Any]) -> str:
        """Build installation and requirements section. Issue #620."""
        return f"""
INSTALLATION:
{tool_info.get('installation', 'No installation information available')}

SYSTEM REQUIREMENTS:
{tool_info.get('requirements', 'Standard Linux system')}"""

    def _build_tool_usage_section(self, tool_info: Dict[str, Any]) -> str:
        """Build usage and command examples section. Issue #620."""
        return f"""
BASIC USAGE:
{tool_info.get('usage', 'No usage information available')}

COMMAND SYNTAX:
{tool_info.get('syntax', 'See man page for syntax')}

COMMON COMMANDS & EXAMPLES:
{self._format_command_examples(tool_info.get('command_examples', []))}"""

    def _build_tool_advanced_section(self, tool_info: Dict[str, Any]) -> str:
        """Build advanced usage and troubleshooting section. Issue #620."""
        return f"""
ADVANCED USAGE:
{tool_info.get('advanced_usage', 'See documentation for advanced features')}

TROUBLESHOOTING:
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

    def _build_tool_resources_section(self, tool_info: Dict[str, Any]) -> str:
        """Build external resources section. Issue #620."""
        return f"""
EXTERNAL RESOURCES:
- Official Documentation: {tool_info.get('documentation_url', 'N/A')}
- Source Code: {tool_info.get('source_url', 'N/A')}
- Tutorial Links: {tool_info.get('tutorials', [])}
- Community Forums: {tool_info.get('forums', [])}"""

    def _build_tool_metadata_section(self, tool_info: Dict[str, Any]) -> str:
        """Build metadata section with timestamps. Issue #620."""
        return f"""
METADATA:
- Added: {datetime.now().isoformat()}
- Last Updated: {datetime.now().isoformat()}
- Verification Status: {tool_info.get('verified', 'unverified')}
- Usage Count: 0
- Success Rate: N/A
"""

    def _build_tool_metadata(self, tool_name: str) -> Dict[str, Any]:
        """Build metadata dictionary for tool storage. Issue #620."""
        return {
            "tool_name": tool_name,
            "category": "tools",
            "type": "tool_documentation",
            "source": "web_research",
            "timestamp": datetime.now().isoformat(),
        }

    async def _publish_tool_knowledge_event(self, tool_name: str) -> None:
        """Publish event for new tool knowledge availability. Issue #620."""
        await event_manager.publish(
            "knowledge_update",
            {
                "type": "new_tool",
                "tool_name": tool_name,
                "message": f"Added knowledge about {tool_name} to the knowledge base",
            },
        )

    async def get_tool_instructions(self, tool_name: str) -> Dict[str, Any]:
        """Get installation and usage instructions for a specific tool"""
        # Search KB for specific tool instructions
        search_results = await self.knowledge_base.search(
            f"{tool_name} installation usage", n_results=3
        )

        if search_results:
            # Extract instructions from results
            instructions = self._extract_instructions(search_results, tool_name)
            if instructions:
                return instructions

        # If not in KB, research the specific tool
        logger.info(f"Tool {tool_name} not found in KB, researching...")
        tool_info = await self._research_specific_tool(tool_name)

        if tool_info:
            # Store for future use
            await self.store_tool_knowledge(tool_info)
            return tool_info

        return {"name": tool_name, "error": "Could not find instructions for this tool"}

    async def _research_specific_tool(self, tool_name: str) -> Optional[Dict[str, Any]]:
        """
        Research a specific tool comprehensively.

        Issue #620: Refactored to use helper functions for each extraction type.
        """
        results = await self._execute_research_queries(tool_name)
        if not results:
            return None

        tool_info = {
            "name": tool_name,
            "type": self._determine_tool_type(tool_name),
            "category": self._categorize_tool(tool_name, ""),
            "platform": "linux",
        }
        self._extract_installation_info(results, tool_info, tool_name)
        self._extract_usage_info(results, tool_info)
        self._extract_advanced_info(results, tool_info)
        self._extract_troubleshooting_info(results, tool_info)
        self._extract_integration_info(results, tool_info)
        self._extract_security_info(results, tool_info)
        self._add_research_metadata(results, tool_info)
        return tool_info

    async def _execute_research_queries(self, tool_name: str) -> Dict[str, Any]:
        """Execute all research queries for a tool. Issue #620."""
        research_queries = {
            "installation": f"how to install {tool_name} linux ubuntu debian",
            "usage": f"{tool_name} tutorial examples command line",
            "advanced": f"{tool_name} advanced usage options flags",
            "troubleshooting": f"{tool_name} common errors problems solutions",
            "integration": f"{tool_name} integration with other tools pipes",
            "security": f"{tool_name} security considerations best practices",
        }
        results = {}
        for query_type, query in research_queries.items():
            try:
                result = await self.web_assistant.research_query(query)
                if result.get("status") == "success":
                    results[query_type] = result
            except Exception as e:
                logger.debug(f"Research query failed for {query_type}: {e}")
        return results

    def _extract_installation_info(
        self, results: Dict, tool_info: Dict, tool_name: str
    ) -> None:
        """Extract installation information from research results. Issue #620."""
        if "installation" not in results:
            return
        install_summary = results["installation"].get("summary", "")
        tool_info.update(
            {
                "installation": self._extract_installation_commands(install_summary),
                "requirements": self._extract_requirements(install_summary),
                "package_name": self._determine_package_name(
                    tool_name, install_summary
                ),
            }
        )

    def _extract_usage_info(self, results: Dict, tool_info: Dict) -> None:
        """Extract usage information from research results. Issue #620."""
        if "usage" not in results:
            return
        usage_summary = results["usage"].get("summary", "")
        tool_info.update(
            {
                "usage": usage_summary,
                "syntax": self._extract_command_syntax(usage_summary),
                "command_examples": self._extract_detailed_examples(usage_summary),
                "output_formats": self._extract_output_formats(usage_summary),
            }
        )

    def _extract_advanced_info(self, results: Dict, tool_info: Dict) -> None:
        """Extract advanced usage information. Issue #620."""
        if "advanced" not in results:
            return
        advanced_summary = results["advanced"].get("summary", "")
        tool_info.update(
            {
                "advanced_usage": advanced_summary,
                "features": self._extract_advanced_features(advanced_summary),
            }
        )

    def _extract_troubleshooting_info(self, results: Dict, tool_info: Dict) -> None:
        """Extract troubleshooting information. Issue #620."""
        if "troubleshooting" not in results:
            return
        trouble_summary = results["troubleshooting"].get("summary", "")
        tool_info.update(
            {
                "troubleshooting": trouble_summary,
                "error_codes": self._extract_error_codes(trouble_summary),
                "common_issues": self._extract_common_issues(trouble_summary),
            }
        )

    def _extract_integration_info(self, results: Dict, tool_info: Dict) -> None:
        """Extract integration information. Issue #620."""
        if "integration" not in results:
            return
        integration_summary = results["integration"].get("summary", "")
        tool_info.update(
            {
                "integrations": integration_summary,
                "related_tools": self._extract_related_tools(integration_summary),
            }
        )

    def _extract_security_info(self, results: Dict, tool_info: Dict) -> None:
        """Extract security information. Issue #620."""
        if "security" not in results:
            return
        security_summary = results["security"].get("summary", "")
        tool_info.update(
            {
                "security_notes": security_summary,
                "best_practices": self._extract_security_practices(security_summary),
            }
        )

    def _add_research_metadata(self, results: Dict, tool_info: Dict) -> None:
        """Add metadata from research results. Issue #620."""
        tool_info.update(
            {
                "documentation_url": self._find_official_docs(results),
                "verified": "web_research",
                "limitations": self._extract_limitations(results),
                "performance": self._extract_performance_notes(results),
            }
        )

    def _determine_tool_type(self, tool_name: str) -> str:
        """Determine tool type based on name patterns"""
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

    def _extract_requirements(self, text: str) -> str:
        """Extract system requirements from installation text"""
        lines = text.split("\n")
        requirements = []

        for line in lines:
            line_lower = line.lower()
            if any(
                word in line_lower
                for word in ["require", "depend", "need", "prerequisite"]
            ):
                requirements.append(line.strip())

        return "\n".join(requirements) if requirements else "Standard Linux system"

    def _extract_command_syntax(self, text: str) -> str:
        """Extract command syntax patterns"""
        lines = text.split("\n")
        syntax_lines = []

        for line in lines:
            if any(
                pattern in line
                for pattern in ["Usage:", "Syntax:", "SYNOPSIS", "usage:"]
            ):
                syntax_lines.append(line.strip())

        return "\n".join(syntax_lines) if syntax_lines else "See man page for syntax"

    def _extract_detailed_examples(self, text: str) -> List[Dict[str, str]]:
        """Extract detailed command examples with descriptions"""
        examples = []
        lines = text.split("\n")

        current_example = None
        for line in lines:
            line = line.strip()
            if line.startswith("$") or line.startswith("#"):
                if current_example:
                    examples.append(current_example)
                current_example = {
                    "command": line[1:].strip(),
                    "description": "",
                    "expected_output": "",
                }
            elif (
                current_example
                and line
                and not line.startswith("$")
                and not line.startswith("#")
            ):
                # This might be description or output
                if not current_example["description"]:
                    current_example["description"] = line
                elif line.startswith("Output:") or "output" in line.lower():
                    current_example["expected_output"] = line

        if current_example:
            examples.append(current_example)

        return examples

    def _extract_output_formats(self, text: str) -> str:
        """Extract information about output formats"""
        formats = []
        lines = text.split("\n")

        for line in lines:
            line_lower = line.lower()
            if any(
                word in line_lower for word in ["output", "format", "result", "report"]
            ):
                formats.append(line.strip())

        return "\n".join(formats[:3]) if formats else "Standard text output"

    def _extract_advanced_features(self, text: str) -> str:
        """Extract advanced features and capabilities"""
        features = []
        lines = text.split("\n")

        for line in lines:
            line_lower = line.lower()
            if any(
                word in line_lower
                for word in ["feature", "capability", "support", "advanced"]
            ):
                features.append(line.strip())

        return (
            "\n".join(features[:5])
            if features
            else "See documentation for advanced features"
        )

    def _extract_error_codes(self, text: str) -> str:
        """Extract error codes and their meanings"""
        error_info = []
        lines = text.split("\n")

        for line in lines:
            if any(
                pattern in line.lower()
                for pattern in ["error", "exit code", "return code"]
            ):
                error_info.append(line.strip())

        return "\n".join(error_info[:5]) if error_info else "Standard Unix exit codes"

    def _extract_common_issues(self, text: str) -> List[Dict[str, str]]:
        """Extract common issues and solutions"""
        issues = []
        lines = text.split("\n")

        current_issue = None
        for line in lines:
            line = line.strip()
            if any(
                word in line.lower() for word in ["problem", "issue", "error", "fail"]
            ):
                if current_issue:
                    issues.append(current_issue)
                current_issue = {"problem": line, "solution": ""}
            elif current_issue and any(
                word in line.lower() for word in ["solution", "fix", "resolve"]
            ):
                current_issue["solution"] = line

        if current_issue:
            issues.append(current_issue)

        return issues

    def _extract_related_tools(self, text: str) -> List[str]:
        """Extract names of related tools"""
        tools = []
        lines = text.split("\n")

        for line in lines:
            # Look for tool mentions
            words = line.split()
            for word in words:
                word = word.strip(".,()[]{}")
                if (
                    len(word) > 2
                    and word.islower()
                    and not word.isdigit()
                    and any(char in word for char in ["-", "_"])
                    or word in ["grep", "awk", "sed", "find", "xargs"]
                ):
                    tools.append(word)

        return list(set(tools))[:10]  # Remove duplicates, limit to 10

    def _extract_security_practices(self, text: str) -> List[str]:
        """Extract security best practices"""
        practices = []
        lines = text.split("\n")

        for line in lines:
            line_lower = line.lower()
            if any(
                word in line_lower
                for word in ["secure", "safe", "recommend", "best practice"]
            ):
                practices.append(line.strip())

        return practices[:5]

    def _find_official_docs(self, results: Dict[str, Any]) -> str:
        """Find official documentation URLs from research results"""
        for result in results.values():
            sources = result.get("sources", [])
            for source in sources:
                url = source.get("url", "")
                if any(
                    domain in url
                    for domain in ["github.com", "docs.", "man7.org", ".org"]
                ):
                    return url
        return "N/A"

    def _extract_limitations(self, results: Dict[str, Any]) -> str:
        """Extract tool limitations from research"""
        limitations = []
        for result in results.values():
            summary = result.get("summary", "")
            lines = summary.split("\n")
            for line in lines:
                if any(
                    word in line.lower()
                    for word in ["limit", "cannot", "not support", "restriction"]
                ):
                    limitations.append(line.strip())

        return (
            "\n".join(limitations[:3])
            if limitations
            else "See documentation for limitations"
        )

    def _extract_performance_notes(self, results: Dict[str, Any]) -> str:
        """Extract performance-related information"""
        perf_notes = []
        for result in results.values():
            summary = result.get("summary", "")
            lines = summary.split("\n")
            for line in lines:
                if any(
                    word in line.lower()
                    for word in [
                        "performance",
                        "speed",
                        "memory",
                        "cpu",
                        "slow",
                        "fast",
                    ]
                ):
                    perf_notes.append(line.strip())

        return (
            "\n".join(perf_notes[:3])
            if perf_notes
            else "Performance varies with input size"
        )

    def _extract_installation_commands(self, text: str) -> str:
        """Extract installation commands from text"""
        lines = text.split("\n")
        install_commands = []

        for line in lines:
            line = line.strip()
            # Look for common installation patterns
            if any(
                cmd in line
                for cmd in [
                    "apt install",
                    "apt-get install",
                    "yum install",
                    "dnf install",
                    "pacman -S",
                    "brew install",
                    "pip install",
                    "npm install",
                ]
            ):
                install_commands.append(line)

        if install_commands:
            return "\n".join(install_commands)
        else:
            # Look for generic installation instructions
            for line in lines:
                if "install" in line.lower():
                    return line

        return "Installation method not found"

    def _extract_command_examples(self, text: str) -> List[str]:
        """Extract command examples from text"""
        lines = text.split("\n")
        commands = []

        for line in lines:
            line = line.strip()
            # Look for lines that start with $ or #
            if line.startswith("$") or line.startswith("#"):
                command = line[1:].strip()
                if command and len(command) < 200:  # Reasonable command length
                    commands.append(command)
            # Look for code blocks or command patterns
            elif line and not line[0].isupper() and " " in line and len(line) < 100:
                # Heuristic: might be a command
                if any(cmd in line for cmd in ["-", "--", "|", ">", "<"]):
                    commands.append(line)

        return commands[:10]  # Return top 10 examples

    def _determine_package_name(self, tool_name: str, installation_text: str) -> str:
        """Determine the package name from tool name and installation text"""
        # Common package name mappings
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

        # Check if tool name is in mappings
        if tool_name.lower() in package_mappings:
            return package_mappings[tool_name.lower()]

        # Try to extract from installation commands
        import re

        install_pattern = (
            r"(?:apt|apt-get|yum|dnf|pacman|brew|pip|npm)\s+install\s+"
            r"(?:-[yS]\s+)?(\S+)"
        )
        match = re.search(install_pattern, installation_text)
        if match:
            return match.group(1)

        # Default to tool name
        return tool_name.lower()

    def _extract_tool_info(
        self, results: List[Dict], tool_type: str
    ) -> List[Dict[str, Any]]:
        """Extract tool information from KB search results"""
        tools = []

        for result in results:
            content = result.get("content", "")
            metadata = result.get("metadata", {})

            # Check if this is a tool documentation
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

    def _extract_tools_from_content(
        self, content: str, title: str, tool_type: str
    ) -> List[Dict[str, Any]]:
        """Extract tool names and descriptions from web content"""
        tools = []

        # Common tool name patterns based on tool type
        tool_patterns = {
            "network scan": ["nmap", "masscan", "zmap", "angry ip scanner", "arp-scan"],
            "port scan": ["nmap", "masscan", "netcat", "nc", "telnet"],
            "web scraping": ["wget", "curl", "httrack", "scrapy", "beautifulsoup"],
            "file search": ["find", "locate", "grep", "ag", "ripgrep", "fd"],
            "process monitor": ["htop", "top", "ps", "pstree", "lso"],
            "disk usage": ["d", "du", "ncdu", "baobab", "qdirstat"],
            "network monitor": ["iftop", "nethogs", "vnstat", "bmon", "nload"],
        }

        # Get relevant patterns
        patterns = tool_patterns.get(tool_type.lower(), [])

        # Search for tool mentions
        content_lower = content.lower()
        for pattern in patterns:
            if pattern in content_lower:
                # Extract context around the tool mention
                start = max(0, content_lower.find(pattern) - 50)
                end = min(
                    len(content), content_lower.find(pattern) + len(pattern) + 100
                )
                context = content[start:end]

                tools.append(
                    {"name": pattern, "context": context, "source_title": title}
                )

        return tools

    def _deduplicate_results(self, results: List[Dict]) -> List[Dict]:
        """Deduplicate search results based on content similarity"""
        unique = []
        seen_content = set()

        for result in results:
            content_hash = hash(result.get("content", "")[:100])  # Hash first 100 chars
            if content_hash not in seen_content:
                seen_content.add(content_hash)
                unique.append(result)

        return unique

    def _deduplicate_tools(self, tools: List[Dict]) -> List[Dict]:
        """Deduplicate tool list"""
        unique_tools = {}

        for tool in tools:
            name = tool["name"]
            if name not in unique_tools:
                unique_tools[name] = tool
            else:
                # Merge information
                existing = unique_tools[name]
                if len(tool.get("context", "")) > len(existing.get("context", "")):
                    unique_tools[name] = tool

        return list(unique_tools.values())

    def _extract_instructions(
        self, results: List[Dict], tool_name: str
    ) -> Optional[Dict[str, Any]]:
        """Extract installation and usage instructions from KB results"""
        for result in results:
            content = result.get("content", "")
            if self._content_contains_tool(content, tool_name):
                instructions = self._initialize_instructions(tool_name)
                lines = content.split("\n")
                self._parse_content_sections(lines, instructions)

                if self._has_valid_instructions(instructions):
                    return instructions

        return None

    def _content_contains_tool(self, content: str, tool_name: str) -> bool:
        """Check if content contains the specified tool name"""
        return tool_name.lower() in content.lower()

    def _initialize_instructions(self, tool_name: str) -> Dict[str, Any]:
        """Initialize empty instructions structure"""
        return {
            "name": tool_name,
            "installation": "",
            "usage": "",
            "commands": [],
        }

    def _parse_content_sections(
        self, lines: List[str], instructions: Dict[str, Any]
    ) -> None:
        """Parse content lines into instruction sections"""
        current_section = None

        for line in lines:
            line = line.strip()
            section = self._identify_section(line)

            if section:
                current_section = section
            elif current_section and line:
                self._add_content_to_section(current_section, line, instructions)

    def _identify_section(self, line: str) -> Optional[str]:
        """Identify which section a line belongs to"""
        if line.startswith("Installation:"):
            return "installation"
        elif line.startswith("Basic Usage:") or line.startswith("Usage:"):
            return "usage"
        elif line.startswith("Common Commands:"):
            return "commands"
        return None

    def _add_content_to_section(
        self, section: str, line: str, instructions: Dict[str, Any]
    ) -> None:
        """Add content line to the appropriate instruction section"""
        if section == "installation":
            instructions["installation"] += line + "\n"
        elif section == "usage":
            instructions["usage"] += line + "\n"
        elif section == "commands":
            if line.startswith("-") or line.startswith("•"):
                instructions["commands"].append(line[1:].strip())

    def _has_valid_instructions(self, instructions: Dict[str, Any]) -> bool:
        """Check if instructions contain valid content"""
        return bool(instructions["installation"] or instructions["usage"])

    async def _store_tool_research_results(
        self, tool_type: str, tools: List[Dict[str, Any]]
    ):
        """Store research results in KB for future use"""
        if not tools:
            return

        # Create a summary document
        summary_content = """
Tool Research Results: {tool_type}
Date: {datetime.now().isoformat()}

Found {len(tools)} tools for {tool_type}:

"""
        for i, tool in enumerate(tools, 1):
            summary_content += """
{i}. {tool['name']}
   Purpose: {tool.get('purpose', 'N/A')}
   Installation: {tool.get('installation', 'N/A')[:200]}...

"""

        metadata = {
            "type": "tool_research_summary",
            "tool_type": tool_type,
            "tools_count": len(tools),
            "timestamp": datetime.now().isoformat(),
        }

        await self.knowledge_base.store_fact(summary_content, metadata=metadata)

        # Store individual tool information
        for tool in tools:
            await self.store_tool_knowledge(tool)

    async def _get_detailed_tool_info(self, tool_name: str) -> Optional[Dict[str, Any]]:
        """Get detailed information about a specific tool"""
        # Quick research for tool details
        query = f"{tool_name} tool description features"
        results = await self.web_assistant.research_query(query)

        if results.get("status") == "success" and results.get("summary"):
            summary = results["summary"]

            # Extract key information
            info = {
                "purpose": self._extract_purpose(summary, tool_name),
                "features": self._extract_features(summary),
                "platform": "linux",  # Default assumption
                "category": self._categorize_tool(tool_name, summary),
            }

            return info

        return None

    def _extract_purpose(self, text: str, tool_name: str) -> str:
        """Extract tool purpose from text"""
        sentences = text.split(".")
        for sentence in sentences:
            if tool_name.lower() in sentence.lower() and "is" in sentence:
                return sentence.strip()
        return "Tool for various system operations"

    def _extract_features(self, text: str) -> str:
        """Extract tool features from text"""
        # Look for feature indicators
        features = []
        lines = text.split("\n")

        for line in lines:
            if any(
                indicator in line.lower()
                for indicator in ["feature", "support", "can", "allow", "enable"]
            ):
                features.append(line.strip())

        return (
            "\n".join(features[:5])
            if features
            else "Various features for system administration"
        )

    def _categorize_tool(self, tool_name: str, description: str) -> str:
        """Categorize tool based on name and description"""
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

    def _format_command_examples(self, examples: List[Dict[str, str]]) -> str:
        """Format command examples for documentation"""
        if not examples:
            return "No examples available"

        formatted = []
        for i, example in enumerate(examples, 1):
            if isinstance(example, dict):
                cmd = example.get("command", "")
                desc = example.get("description", "")
                output = example.get("expected_output", "")

                formatted.append(f"{i}. {desc}")
                formatted.append(f"   Command: {cmd}")
                if output:
                    formatted.append(f"   Expected Output: {output}")
                formatted.append("")
            else:
                formatted.append(f"{i}. {example}")

        return "\n".join(formatted)

    async def store_system_documentation(self, doc_info: Dict[str, Any]):
        """Store general system documentation and procedures"""
        doc_type = doc_info.get("type", "general")
        doc_title = doc_info.get("title", "System Documentation")

        document_content = """
SYSTEM DOCUMENTATION: {doc_title}
==================================================

TYPE: {doc_type}
CATEGORY: {doc_info.get('category', 'system')}

OVERVIEW:
{doc_info.get('overview', 'No overview available')}

PROCEDURES:
{self._format_procedures(doc_info.get('procedures', []))}

PREREQUISITES:
{doc_info.get('prerequisites', 'None specified')}

STEP-BY-STEP GUIDE:
{self._format_steps(doc_info.get('steps', []))}

COMMON ISSUES & SOLUTIONS:
{self._format_troubleshooting(doc_info.get('common_issues', []))}

BEST PRACTICES:
{self._format_best_practices(doc_info.get('best_practices', []))}

RELATED DOCUMENTATION:
{doc_info.get('related_docs', [])}

EXAMPLES:
{self._format_documentation_examples(doc_info.get('examples', []))}

VERIFICATION STEPS:
{self._format_verification_steps(doc_info.get('verification', []))}

METADATA:
- Added: {datetime.now().isoformat()}
- Last Updated: {datetime.now().isoformat()}
- Verification Status: {doc_info.get('verified', 'unverified')}
- Complexity Level: {doc_info.get('complexity', 'medium')}
"""

        metadata = {
            "type": "system_documentation",
            "doc_type": doc_type,
            "category": doc_info.get("category", "system"),
            "title": doc_title,
            "timestamp": datetime.now().isoformat(),
        }

        await self.knowledge_base.store_fact(document_content, metadata=metadata)
        logger.info(f"Stored system documentation: {doc_title}")

    def _format_procedures(self, procedures: List[Dict[str, str]]) -> str:
        """Format procedure documentation"""
        if not procedures:
            return "No procedures documented"

        formatted = []
        for proc in procedures:
            if isinstance(proc, dict):
                name = proc.get("name", "Unnamed Procedure")
                desc = proc.get("description", "")
                steps = proc.get("steps", [])

                formatted.append(f"• {name}")
                if desc:
                    formatted.append(f"  Description: {desc}")
                if steps:
                    for i, step in enumerate(steps, 1):
                        formatted.append(f"  {i}. {step}")
                formatted.append("")
            else:
                formatted.append(f"• {proc}")

        return "\n".join(formatted)

    def _format_steps(self, steps: List[str]) -> str:
        """Format step-by-step instructions"""
        if not steps:
            return "No steps documented"

        return "\n".join([f"{i}. {step}" for i, step in enumerate(steps, 1)])

    def _format_troubleshooting(self, issues: List[Dict[str, str]]) -> str:
        """Format troubleshooting information"""
        if not issues:
            return "No common issues documented"

        formatted = []
        for issue in issues:
            if isinstance(issue, dict):
                problem = issue.get("problem", "Unknown issue")
                solution = issue.get("solution", "No solution provided")
                formatted.append(f"Problem: {problem}")
                formatted.append(f"Solution: {solution}")
                formatted.append("")
            else:
                formatted.append(f"• {issue}")

        return "\n".join(formatted)

    def _format_best_practices(self, practices: List[str]) -> str:
        """Format best practices"""
        if not practices:
            return "No best practices documented"

        return "\n".join([f"• {practice}" for practice in practices])

    def _format_documentation_examples(self, examples: List[Dict[str, str]]) -> str:
        """Format documentation examples"""
        if not examples:
            return "No examples available"

        formatted = []
        for i, example in enumerate(examples, 1):
            if isinstance(example, dict):
                title = example.get("title", f"Example {i}")
                scenario = example.get("scenario", "")
                commands = example.get("commands", [])

                formatted.append(f"{i}. {title}")
                if scenario:
                    formatted.append(f"   Scenario: {scenario}")
                if commands:
                    formatted.append("   Commands:")
                    for cmd in commands:
                        formatted.append(f"     {cmd}")
                formatted.append("")

        return "\n".join(formatted)

    def _format_verification_steps(self, steps: List[str]) -> str:
        """Format verification steps"""
        if not steps:
            return "No verification steps provided"

        return "\n".join([f"{i}. {step}" for i, step in enumerate(steps, 1)])

    async def store_workflow_knowledge(self, workflow_info: Dict[str, Any]):
        """Store complete workflow documentation for complex procedures"""
        workflow_name = workflow_info.get("name", "Unknown Workflow")

        document_content = """
WORKFLOW DOCUMENTATION: {workflow_name}
==================================================

WORKFLOW TYPE: {workflow_info.get('type', 'general')}
COMPLEXITY: {workflow_info.get('complexity', 'medium')}
ESTIMATED TIME: {workflow_info.get('estimated_time', 'varies')}

OBJECTIVE:
{workflow_info.get('objective', 'No objective specified')}

PREREQUISITES:
{self._format_prerequisites(workflow_info.get('prerequisites', []))}

REQUIRED TOOLS:
{self._format_tool_requirements(workflow_info.get('required_tools', []))}

WORKFLOW STEPS:
{self._format_workflow_steps(workflow_info.get('workflow_steps', []))}

DECISION POINTS:
{self._format_decision_points(workflow_info.get('decision_points', []))}

OUTPUT/DELIVERABLES:
{workflow_info.get('deliverables', 'Process completion')}

QUALITY CHECKS:
{self._format_quality_checks(workflow_info.get('quality_checks', []))}

COMMON PITFALLS:
{self._format_pitfalls(workflow_info.get('pitfalls', []))}

ALTERNATIVE APPROACHES:
{self._format_alternatives(workflow_info.get('alternatives', []))}

RELATED WORKFLOWS:
{workflow_info.get('related_workflows', [])}

METADATA:
- Added: {datetime.now().isoformat()}
- Last Updated: {datetime.now().isoformat()}
- Success Rate: {workflow_info.get('success_rate', 'N/A')}
- Difficulty Level: {workflow_info.get('difficulty', 'medium')}
"""

        metadata = {
            "type": "workflow_documentation",
            "workflow_name": workflow_name,
            "category": workflow_info.get("category", "workflows"),
            "complexity": workflow_info.get("complexity", "medium"),
            "timestamp": datetime.now().isoformat(),
        }

        await self.knowledge_base.store_fact(document_content, metadata=metadata)
        logger.info(f"Stored workflow documentation: {workflow_name}")

    def _format_prerequisites(self, prereqs: List[str]) -> str:
        """Format prerequisites"""
        if not prereqs:
            return "None specified"
        return "\n".join([f"• {prereq}" for prereq in prereqs])

    def _format_tool_requirements(self, tools: List[Dict[str, str]]) -> str:
        """Format tool requirements"""
        if not tools:
            return "Standard system tools"

        formatted = []
        for tool in tools:
            if isinstance(tool, dict):
                name = tool.get("name", "Unknown tool")
                purpose = tool.get("purpose", "")
                optional = tool.get("optional", False)
                prefix = "Optional: " if optional else "Required: "
                formatted.append(f"• {prefix}{name}")
                if purpose:
                    formatted.append(f"  Purpose: {purpose}")
            else:
                formatted.append(f"• {tool}")

        return "\n".join(formatted)

    def _format_workflow_steps(self, steps: List[Dict[str, Any]]) -> str:
        """Format detailed workflow steps"""
        if not steps:
            return "No steps documented"

        formatted = []
        for i, step in enumerate(steps, 1):
            if isinstance(step, dict):
                action = step.get("action", f"Step {i}")
                details = step.get("details", "")
                commands = step.get("commands", [])
                expected_output = step.get("expected_output", "")

                formatted.append(f"{i}. {action}")
                if details:
                    formatted.append(f"   Details: {details}")
                if commands:
                    formatted.append("   Commands:")
                    for cmd in commands:
                        formatted.append(f"     {cmd}")
                if expected_output:
                    formatted.append(f"   Expected Output: {expected_output}")
                formatted.append("")
            else:
                formatted.append(f"{i}. {step}")

        return "\n".join(formatted)

    def _format_decision_points(self, decisions: List[Dict[str, str]]) -> str:
        """Format decision points in workflow"""
        if not decisions:
            return "No decision points documented"

        formatted = []
        for decision in decisions:
            if isinstance(decision, dict):
                condition = decision.get("condition", "Unknown condition")
                if_true = decision.get("if_true", "Continue")
                if_false = decision.get("if_false", "Stop")
                formatted.append(f"• If {condition}:")
                formatted.append(f"  - True: {if_true}")
                formatted.append(f"  - False: {if_false}")
                formatted.append("")

        return "\n".join(formatted)

    def _format_quality_checks(self, checks: List[str]) -> str:
        """Format quality check steps"""
        if not checks:
            return "No quality checks documented"

        return "\n".join([f"✓ {check}" for check in checks])

    def _format_pitfalls(self, pitfalls: List[Dict[str, str]]) -> str:
        """Format common pitfalls and how to avoid them"""
        if not pitfalls:
            return "No common pitfalls documented"

        formatted = []
        for pitfall in pitfalls:
            if isinstance(pitfall, dict):
                issue = pitfall.get("issue", "Unknown issue")
                prevention = pitfall.get("prevention", "No prevention method")
                formatted.append(f"⚠️ {issue}")
                formatted.append(f"   Prevention: {prevention}")
                formatted.append("")

        return "\n".join(formatted)

    def _format_alternatives(self, alternatives: List[Dict[str, str]]) -> str:
        """Format alternative approaches"""
        if not alternatives:
            return "No alternatives documented"

        formatted = []
        for alt in alternatives:
            if isinstance(alt, dict):
                approach = alt.get("approach", "Alternative approach")
                when_to_use = alt.get("when_to_use", "When standard method fails")
                formatted.append(f"• {approach}")
                formatted.append(f"  When to use: {when_to_use}")
                formatted.append("")

        return "\n".join(formatted)
