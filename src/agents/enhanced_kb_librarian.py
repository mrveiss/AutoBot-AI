# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Enhanced KB Librarian Agent for AutoBot
Manages tool knowledge, coordinates with other agents, and handles dynamic tool
discovery

Refactored to fix Feature Envy code smells by adding data classes with methods.
"""

import asyncio
import logging
import re
from datetime import datetime
from typing import Any, Dict, List, Optional

from src.agents.web_research_assistant import WebResearchAssistant
from src.event_manager import event_manager
from src.knowledge_base import KnowledgeBase

logger = logging.getLogger(__name__)

# Performance optimization: O(1) lookup for keyword checks (Issue #326)
REQUIREMENT_KEYWORDS = {"require", "depend", "need", "prerequisite"}
SYNTAX_PATTERNS = {"Usage:", "Syntax:", "SYNOPSIS", "usage:"}
OUTPUT_FORMAT_KEYWORDS = {"output", "format", "result", "report"}
ADVANCED_FEATURE_KEYWORDS = {"feature", "capability", "support", "advanced"}
ERROR_CODE_PATTERNS = {"error", "exit code", "return code"}
PROBLEM_KEYWORDS = {"problem", "issue", "error", "fail"}
SOLUTION_KEYWORDS = {"solution", "fix", "resolve"}
COMMON_CLI_TOOLS = {"grep", "awk", "sed", "find", "xargs"}
SECURITY_KEYWORDS = {"secure", "safe", "recommend", "best practice"}
OFFICIAL_DOC_DOMAINS = {"github.com", "docs.", "man7.org", ".org"}
LIMITATION_KEYWORDS = {"limit", "cannot", "not support", "restriction"}
PERFORMANCE_KEYWORDS = {"performance", "speed", "memory", "cpu", "slow", "fast"}
INSTALLATION_COMMANDS = {
    "apt install",
    "apt-get install",
    "yum install",
    "dnf install",
    "pacman -S",
    "brew install",
    "pip install",
    "npm install",
}
COMMAND_OPERATORS = {"-", "--", "|", ">", "<"}
FEATURE_INDICATORS = {"feature", "support", "can", "allow", "enable"}
TOOL_NAME_CHARS = {"-", "_"}  # Characters that often appear in tool names


class TextExtractor:
    """Helper class for extracting information from text content"""

    @classmethod
    def extract_requirements(cls, text: str) -> str:
        """Extract system requirements from installation text"""
        lines = text.split("\n")
        requirements = []

        for line in lines:
            line_lower = line.lower()
            if any(
                word in line_lower for word in REQUIREMENT_KEYWORDS  # O(1) lookup (Issue #326)
            ):
                requirements.append(line.strip())

        return "\n".join(requirements) if requirements else "Standard Linux system"

    @classmethod
    def extract_command_syntax(cls, text: str) -> str:
        """Extract command syntax patterns"""
        lines = text.split("\n")
        syntax_lines = []

        for line in lines:
            if any(pattern in line for pattern in SYNTAX_PATTERNS):  # O(1) lookup (Issue #326)
                syntax_lines.append(line.strip())

        return "\n".join(syntax_lines) if syntax_lines else "See man page for syntax"

    @classmethod
    def is_command_line(cls, line: str) -> bool:
        """Check if line is a command (Issue #334 - extracted helper)."""
        return line.startswith("$") or line.startswith("#")

    @classmethod
    def update_example_metadata(
        cls, example: Dict[str, str], line: str
    ) -> None:
        """Update example with description or output (Issue #334 - extracted helper)."""
        if not example["description"]:
            example["description"] = line
        elif line.startswith("Output:") or "output" in line.lower():
            example["expected_output"] = line

    @classmethod
    def extract_detailed_examples(cls, text: str) -> List[Dict[str, str]]:
        """Extract detailed command examples with descriptions"""
        examples = []
        lines = text.split("\n")

        current_example = None
        for line in lines:
            line = line.strip()
            if cls.is_command_line(line):
                if current_example:
                    examples.append(current_example)
                current_example = {
                    "command": line[1:].strip(),
                    "description": "",
                    "expected_output": "",
                }
            elif current_example and line and not cls.is_command_line(line):
                cls.update_example_metadata(current_example, line)

        if current_example:
            examples.append(current_example)

        return examples

    @classmethod
    def extract_output_formats(cls, text: str) -> str:
        """Extract information about output formats"""
        formats = []
        lines = text.split("\n")

        for line in lines:
            line_lower = line.lower()
            if any(word in line_lower for word in OUTPUT_FORMAT_KEYWORDS):  # O(1) lookup (Issue #326)
                formats.append(line.strip())

        return "\n".join(formats[:3]) if formats else "Standard text output"

    @classmethod
    def extract_advanced_features(cls, text: str) -> str:
        """Extract advanced features and capabilities"""
        features = []
        lines = text.split("\n")

        for line in lines:
            line_lower = line.lower()
            if any(word in line_lower for word in ADVANCED_FEATURE_KEYWORDS):  # O(1) lookup (Issue #326)
                features.append(line.strip())

        return (
            "\n".join(features[:5])
            if features
            else "See documentation for advanced features"
        )

    @classmethod
    def extract_error_codes(cls, text: str) -> str:
        """Extract error codes and their meanings"""
        error_info = []
        lines = text.split("\n")

        for line in lines:
            if any(pattern in line.lower() for pattern in ERROR_CODE_PATTERNS):  # O(1) lookup (Issue #326)
                error_info.append(line.strip())

        return "\n".join(error_info[:5]) if error_info else "Standard Unix exit codes"

    @classmethod
    def _is_problem_line(cls, line: str) -> bool:
        """Check if line contains problem keywords (Issue #315 - extracted helper)."""
        line_lower = line.lower()
        return any(word in line_lower for word in PROBLEM_KEYWORDS)

    @classmethod
    def _is_solution_line(cls, line: str) -> bool:
        """Check if line contains solution keywords (Issue #315 - extracted helper)."""
        line_lower = line.lower()
        return any(word in line_lower for word in SOLUTION_KEYWORDS)

    @classmethod
    def extract_common_issues(cls, text: str) -> List[Dict[str, str]]:
        """Extract common issues and solutions"""
        issues = []
        current_issue = None

        for line in text.split("\n"):
            line = line.strip()
            if cls._is_problem_line(line):
                if current_issue:
                    issues.append(current_issue)
                current_issue = {"problem": line, "solution": ""}
            elif current_issue and cls._is_solution_line(line):
                current_issue["solution"] = line

        if current_issue:
            issues.append(current_issue)

        return issues

    @classmethod
    def _is_potential_tool_name(cls, word: str) -> bool:
        """Check if word looks like a tool name (Issue #315 - extracted helper)."""
        if word in COMMON_CLI_TOOLS:
            return True
        if len(word) <= 2 or not word.islower() or word.isdigit():
            return False
        return any(char in word for char in TOOL_NAME_CHARS)

    @classmethod
    def extract_related_tools(cls, text: str) -> List[str]:
        """Extract names of related tools"""
        tools = []

        for line in text.split("\n"):
            for word in line.split():
                cleaned = word.strip(".,()[]{}")
                if cls._is_potential_tool_name(cleaned):
                    tools.append(cleaned)

        return list(set(tools))[:10]

    @classmethod
    def extract_security_practices(cls, text: str) -> List[str]:
        """Extract security best practices"""
        practices = []
        lines = text.split("\n")

        for line in lines:
            line_lower = line.lower()
            if any(word in line_lower for word in SECURITY_KEYWORDS):  # O(1) lookup (Issue #326)
                practices.append(line.strip())

        return practices[:5]

    @classmethod
    def extract_installation_commands(cls, text: str) -> str:
        """Extract installation commands from text"""
        lines = text.split("\n")
        install_commands = []

        for line in lines:
            line = line.strip()
            # Look for common installation patterns
            if any(cmd in line for cmd in INSTALLATION_COMMANDS):  # O(1) lookup (Issue #326)
                install_commands.append(line)

        if install_commands:
            return "\n".join(install_commands)
        else:
            # Look for generic installation instructions
            for line in lines:
                if "install" in line.lower():
                    return line

        return "Installation method not found"

    @classmethod
    def _extract_prompt_command(cls, line: str) -> Optional[str]:
        """Extract command from $ or # prompt line (Issue #315 - extracted helper)."""
        if not (line.startswith("$") or line.startswith("#")):
            return None
        command = line[1:].strip()
        if command and len(command) < 200:
            return command
        return None

    @classmethod
    def _is_heuristic_command(cls, line: str) -> bool:
        """Check if line looks like a command by heuristics (Issue #315 - extracted helper)."""
        if not line or line[0].isupper() or " " not in line or len(line) >= 100:
            return False
        return any(cmd in line for cmd in COMMAND_OPERATORS)

    @classmethod
    def extract_command_examples(cls, text: str) -> List[str]:
        """Extract command examples from text"""
        commands = []

        for line in text.split("\n"):
            line = line.strip()
            prompt_cmd = cls._extract_prompt_command(line)
            if prompt_cmd:
                commands.append(prompt_cmd)
            elif cls._is_heuristic_command(line):
                commands.append(line)

        return commands[:10]

    @classmethod
    def extract_purpose(cls, text: str, tool_name: str) -> str:
        """Extract tool purpose from text"""
        sentences = text.split(".")
        for sentence in sentences:
            if tool_name.lower() in sentence.lower() and "is" in sentence:
                return sentence.strip()
        return "Tool for various system operations"

    @classmethod
    def extract_features(cls, text: str) -> str:
        """Extract tool features from text"""
        # Look for feature indicators
        features = []
        lines = text.split("\n")

        for line in lines:
            if any(indicator in line.lower() for indicator in FEATURE_INDICATORS):  # O(1) lookup (Issue #326)
                features.append(line.strip())

        return (
            "\n".join(features[:5])
            if features
            else "Various features for system administration"
        )


class ToolInfoFormatter:
    """Helper class for formatting tool information and documentation"""

    @classmethod
    def format_command_examples(cls, examples: List[Dict[str, str]]) -> str:
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

    @classmethod
    def _format_procedure_dict(cls, proc: Dict[str, str]) -> List[str]:
        """Format a single procedure dict to lines (Issue #315 - extracted helper)."""
        lines = []
        name = proc.get("name", "Unnamed Procedure")
        desc = proc.get("description", "")
        steps = proc.get("steps", [])

        lines.append(f"• {name}")
        if desc:
            lines.append(f"  Description: {desc}")
        for i, step in enumerate(steps, 1):
            lines.append(f"  {i}. {step}")
        lines.append("")
        return lines

    @classmethod
    def format_procedures(cls, procedures: List[Dict[str, str]]) -> str:
        """Format procedure documentation"""
        if not procedures:
            return "No procedures documented"

        formatted = []
        for proc in procedures:
            if isinstance(proc, dict):
                formatted.extend(cls._format_procedure_dict(proc))
            else:
                formatted.append(f"• {proc}")

        return "\n".join(formatted)

    @classmethod
    def format_steps(cls, steps: List[str]) -> str:
        """Format step-by-step instructions"""
        if not steps:
            return "No steps documented"

        return "\n".join([f"{i}. {step}" for i, step in enumerate(steps, 1)])

    @classmethod
    def format_troubleshooting(cls, issues: List[Dict[str, str]]) -> str:
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

    @classmethod
    def format_best_practices(cls, practices: List[str]) -> str:
        """Format best practices"""
        if not practices:
            return "No best practices documented"

        return "\n".join([f"• {practice}" for practice in practices])

    @classmethod
    def _format_example_dict(cls, example: Dict[str, str], index: int) -> List[str]:
        """Format a single example dict to lines (Issue #315 - extracted helper)."""
        lines = []
        title = example.get("title", f"Example {index}")
        scenario = example.get("scenario", "")
        commands = example.get("commands", [])

        lines.append(f"{index}. {title}")
        if scenario:
            lines.append(f"   Scenario: {scenario}")
        if commands:
            lines.append("   Commands:")
            for cmd in commands:
                lines.append(f"     {cmd}")
        lines.append("")
        return lines

    @classmethod
    def format_documentation_examples(cls, examples: List[Dict[str, str]]) -> str:
        """Format documentation examples"""
        if not examples:
            return "No examples available"

        formatted = []
        for i, example in enumerate(examples, 1):
            if isinstance(example, dict):
                formatted.extend(cls._format_example_dict(example, i))

        return "\n".join(formatted)

    @classmethod
    def format_verification_steps(cls, steps: List[str]) -> str:
        """Format verification steps"""
        if not steps:
            return "No verification steps provided"

        return "\n".join([f"{i}. {step}" for i, step in enumerate(steps, 1)])

    @classmethod
    def format_prerequisites(cls, prereqs: List[str]) -> str:
        """Format prerequisites"""
        if not prereqs:
            return "None specified"
        return "\n".join([f"• {prereq}" for prereq in prereqs])

    @classmethod
    def format_tool_requirements(cls, tools: List[Dict[str, str]]) -> str:
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

    @classmethod
    def _format_workflow_step_dict(cls, step: Dict[str, Any], index: int) -> List[str]:
        """Format a single workflow step dict to lines (Issue #315 - extracted helper)."""
        lines = []
        action = step.get("action", f"Step {index}")
        details = step.get("details", "")
        commands = step.get("commands", [])
        expected_output = step.get("expected_output", "")

        lines.append(f"{index}. {action}")
        if details:
            lines.append(f"   Details: {details}")
        if commands:
            lines.append("   Commands:")
            for cmd in commands:
                lines.append(f"     {cmd}")
        if expected_output:
            lines.append(f"   Expected Output: {expected_output}")
        lines.append("")
        return lines

    @classmethod
    def format_workflow_steps(cls, steps: List[Dict[str, Any]]) -> str:
        """Format detailed workflow steps"""
        if not steps:
            return "No steps documented"

        formatted = []
        for i, step in enumerate(steps, 1):
            if isinstance(step, dict):
                formatted.extend(cls._format_workflow_step_dict(step, i))
            else:
                formatted.append(f"{i}. {step}")

        return "\n".join(formatted)

    @classmethod
    def format_decision_points(cls, decisions: List[Dict[str, str]]) -> str:
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

    @classmethod
    def format_quality_checks(cls, checks: List[str]) -> str:
        """Format quality check steps"""
        if not checks:
            return "No quality checks documented"

        return "\n".join([f"✓ {check}" for check in checks])

    @classmethod
    def format_pitfalls(cls, pitfalls: List[Dict[str, str]]) -> str:
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

    @classmethod
    def format_alternatives(cls, alternatives: List[Dict[str, str]]) -> str:
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


class ResultProcessor:
    """Helper class for processing search results and extracting data"""

    @classmethod
    def find_official_docs(cls, results: Dict[str, Any]) -> str:
        """Find official documentation URLs from research results"""
        for result in results.values():
            sources = result.get("sources", [])
            for source in sources:
                url = source.get("url", "")
                if any(domain in url for domain in OFFICIAL_DOC_DOMAINS):  # O(1) lookup (Issue #326)
                    return url
        return "N/A"

    @classmethod
    def extract_limitations(cls, results: Dict[str, Any]) -> str:
        """Extract tool limitations from research"""
        limitations = []
        for result in results.values():
            summary = result.get("summary", "")
            lines = summary.split("\n")
            for line in lines:
                if any(word in line.lower() for word in LIMITATION_KEYWORDS):  # O(1) lookup (Issue #326)
                    limitations.append(line.strip())

        return (
            "\n".join(limitations[:3])
            if limitations
            else "See documentation for limitations"
        )

    @classmethod
    def extract_performance_notes(cls, results: Dict[str, Any]) -> str:
        """Extract performance-related information"""
        perf_notes = []
        for result in results.values():
            summary = result.get("summary", "")
            lines = summary.split("\n")
            for line in lines:
                if any(word in line.lower() for word in PERFORMANCE_KEYWORDS):  # O(1) lookup (Issue #326)
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

    @classmethod
    def extract_tools_from_content(
        cls, content: str, title: str, tool_type: str
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

    @classmethod
    def deduplicate_results(cls, results: List[Dict]) -> List[Dict]:
        """Deduplicate search results based on content similarity"""
        unique = []
        seen_content = set()

        for result in results:
            content_hash = hash(result.get("content", "")[:100])  # Hash first 100 chars
            if content_hash not in seen_content:
                seen_content.add(content_hash)
                unique.append(result)

        return unique

    @classmethod
    def deduplicate_tools(cls, tools: List[Dict]) -> List[Dict]:
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


class InstructionParser:
    """Helper class for parsing and extracting instructions from content"""

    @classmethod
    def extract_instructions(
        cls, results: List[Dict], tool_name: str
    ) -> Optional[Dict[str, Any]]:
        """Extract installation and usage instructions from KB results"""
        for result in results:
            content = result.get("content", "")
            if cls.content_contains_tool(content, tool_name):
                instructions = cls.initialize_instructions(tool_name)
                lines = content.split("\n")
                cls.parse_content_sections(lines, instructions)

                if cls.has_valid_instructions(instructions):
                    return instructions

        return None

    @classmethod
    def content_contains_tool(cls, content: str, tool_name: str) -> bool:
        """Check if content contains the specified tool name"""
        return tool_name.lower() in content.lower()

    @classmethod
    def initialize_instructions(cls, tool_name: str) -> Dict[str, Any]:
        """Initialize empty instructions structure"""
        return {
            "name": tool_name,
            "installation": "",
            "usage": "",
            "commands": [],
        }

    @classmethod
    def parse_content_sections(
        cls, lines: List[str], instructions: Dict[str, Any]
    ) -> None:
        """Parse content lines into instruction sections"""
        current_section = None

        for line in lines:
            line = line.strip()
            section = cls.identify_section(line)

            if section:
                current_section = section
            elif current_section and line:
                cls.add_content_to_section(current_section, line, instructions)

    @classmethod
    def identify_section(cls, line: str) -> Optional[str]:
        """Identify which section a line belongs to"""
        if line.startswith("Installation:"):
            return "installation"
        elif line.startswith("Basic Usage:") or line.startswith("Usage:"):
            return "usage"
        elif line.startswith("Common Commands:"):
            return "commands"
        return None

    @classmethod
    def _is_command_list_item(cls, line: str) -> bool:
        """Check if line is a command list item (Issue #315 - extracted helper)."""
        return line.startswith("-") or line.startswith("•")

    @classmethod
    def add_content_to_section(
        cls, section: str, line: str, instructions: Dict[str, Any]
    ) -> None:
        """Add content line to the appropriate instruction section"""
        # Handle text sections with simple append
        if section in ("installation", "usage"):
            instructions[section] += line + "\n"
            return

        # Handle commands section with list item detection
        if section == "commands" and cls._is_command_list_item(line):
            instructions["commands"].append(line[1:].strip())

    @classmethod
    def has_valid_instructions(cls, instructions: Dict[str, Any]) -> bool:
        """Check if instructions contain valid content"""
        return bool(instructions["installation"] or instructions["usage"])





# NEW DATA CLASSES TO FIX FEATURE ENVY

class ToolInfoData:
    """Data class for tool information - encapsulates tool data with methods"""
    
    def __init__(self, name: str, tool_type: str = "command-line tool"):
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
        """Convert to dictionary"""
        result = {"name": self.name, "type": self.type, "category": self.category, "platform": self.platform}
        # Add non-None fields
        for key in ["purpose", "installation", "requirements", "package_name", "usage", "syntax", 
                    "output_formats", "advanced_usage", "features", "troubleshooting", "error_codes",
                    "integrations", "security_notes", "documentation_url", "verified", "limitations", "performance"]:
            val = getattr(self, key, None)
            if val is not None:
                result[key] = val
        # Add lists
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
    def from_dict(cls, data: Dict[str, Any]) -> 'ToolInfoData':
        """Create from dictionary"""
        tool = cls(data.get("name", "unknown"), data.get("type", "command-line tool"))
        for key, value in data.items():
            if hasattr(tool, key):
                setattr(tool, key, value)
        return tool


class ResearchResultsProcessor:
    """Processes web research results into structured tool information"""
    
    def __init__(self, tool_name: str, results: Dict[str, Any]):
        self.tool_name = tool_name
        self.results = results
    
    def build_tool_info(self, tool_type: str, category: str) -> ToolInfoData:
        """Build comprehensive tool info from research results"""
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
        """Determine package name from tool name and installation text"""
        package_mappings = {
            "nmap": "nmap", "netcat": "netcat", "nc": "netcat",
            "wireshark": "wireshark", "tcpdump": "tcpdump",
            "curl": "curl", "wget": "wget", "git": "git",
            "docker": "docker.io", "python": "python3",
            "pip": "python3-pip", "node": "nodejs", "npm": "npm",
        }
        
        if self.tool_name.lower() in package_mappings:
            return package_mappings[self.tool_name.lower()]
        
        # Try to extract from installation commands
        install_pattern = r"(?:apt|apt-get|yum|dnf|pacman|brew|pip|npm)\s+install\s+(?:-[yS]\s+)?(\S+)"
        match = re.search(install_pattern, installation_text)
        if match:
            return match.group(1)
        
        return self.tool_name.lower()




class EnhancedKBLibrarian:
    """
    Librarian that can search KB and coordinate with other agents for tool
    discovery
    
    Refactored to use ToolInfoData and ResearchResultsProcessor to fix Feature Envy.
    """

    def __init__(self, knowledge_base: KnowledgeBase):
        self.knowledge_base = knowledge_base
        self.web_assistant = WebResearchAssistant()
        self.tool_cache = {}  # Cache for frequently requested tools
        self._cache_lock = asyncio.Lock()  # Lock for tool_cache access

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
        unique_results = ResultProcessor.deduplicate_results(all_results)

        # Extract tool information from results
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
        """Collect valid results from gather, skipping exceptions (Issue #315 - extracted helper)."""
        tools = []
        for result in extraction_results:
            if isinstance(result, Exception):
                continue
            tools.extend(result)
        return tools

    async def _get_detailed_tools(
        self, top_tools: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Get detailed info for top tools in parallel (Issue #315 - extracted helper)."""
        if not top_tools:
            return []

        tool_infos = await asyncio.gather(
            *[self._get_detailed_tool_info(tool["name"]) for tool in top_tools],
            return_exceptions=True
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
        """Process successful web research results (Issue #315 - extracted helper)."""
        sources = web_results.get("sources", [])

        async def extract_from_source(source: Dict[str, Any]) -> List[Dict[str, Any]]:
            content = source.get("content", "")
            title = source.get("title", "")
            return ResultProcessor.extract_tools_from_content(content, title, tool_type)

        extraction_results = await asyncio.gather(
            *[extract_from_source(source) for source in sources[:5]],
            return_exceptions=True
        )

        tools = self._collect_valid_results(extraction_results)
        unique_tools = ResultProcessor.deduplicate_tools(tools)
        return await self._get_detailed_tools(unique_tools[:3])

    async def request_tool_research(self, tool_type: str) -> List[Dict[str, Any]]:
        """Ask WebAssistant to research tools when KB doesn't have info (thread-safe)"""
        logger.info(f"Requesting web research for tool type: {tool_type}")

        async with self._cache_lock:
            if tool_type in self.tool_cache:
                logger.info(f"Returning cached results for {tool_type}")
                return list(self.tool_cache[tool_type])

        research_query = f"best {tool_type} tools linux command line"
        web_results = await self.web_assistant.research_query(research_query)

        if web_results.get("status") != "success":
            logger.error(f"Web research failed for {tool_type}")
            return []

        detailed_tools = await self._process_web_research_results(tool_type, web_results)

        async with self._cache_lock:
            self.tool_cache[tool_type] = detailed_tools

        await self._store_tool_research_results(tool_type, detailed_tools)
        return detailed_tools

    async def store_tool_knowledge(self, tool_info: Dict[str, Any]):
        """Store comprehensive tool information and documentation in KB"""
        tool_name = tool_info.get("name", "unknown")

        # Create comprehensive structured document for the tool
        document_content = f"""
TOOL DOCUMENTATION: {tool_name}
==================================================

BASIC INFORMATION:
- Name: {tool_name}
- Type: {tool_info.get('type', 'command-line tool')}
- Category: {tool_info.get('category', 'general')}
- Platform: {tool_info.get('platform', 'linux')}
- Purpose: {tool_info.get('purpose', 'N/A')}

INSTALLATION:
{tool_info.get('installation', 'No installation information available')}

SYSTEM REQUIREMENTS:
{tool_info.get('requirements', 'Standard Linux system')}

BASIC USAGE:
{tool_info.get('usage', 'No usage information available')}

COMMAND SYNTAX:
{tool_info.get('syntax', 'See man page for syntax')}

COMMON COMMANDS & EXAMPLES:
{ToolInfoFormatter.format_command_examples(tool_info.get('command_examples', []))}

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
{tool_info.get('related_tools', [])}

EXTERNAL RESOURCES:
- Official Documentation: {tool_info.get('documentation_url', 'N/A')}
- Source Code: {tool_info.get('source_url', 'N/A')}
- Tutorial Links: {tool_info.get('tutorials', [])}
- Community Forums: {tool_info.get('forums', [])}

METADATA:
- Added: {datetime.now().isoformat()}
- Last Updated: {datetime.now().isoformat()}
- Verification Status: {tool_info.get('verified', 'unverified')}
- Usage Count: 0
- Success Rate: N/A
"""

        # Store in knowledge base
        metadata = {
            "tool_name": tool_name,
            "category": "tools",
            "type": "tool_documentation",
            "source": "web_research",
            "timestamp": datetime.now().isoformat(),
        }

        await self.knowledge_base.store_fact(document_content, metadata=metadata)

        logger.info(f"Stored knowledge for tool: {tool_name}")

        # Notify that new tool knowledge is available
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
            instructions = InstructionParser.extract_instructions(search_results, tool_name)
            if instructions:
                return instructions

        # If not in KB, research the specific tool
        logger.info(f"Tool {tool_name} not found in KB, researching...")
        tool_info = await self._research_specific_tool(tool_name)

        if tool_info:
            # Store for future use (convert to dict if ToolInfoData)
            tool_dict = tool_info.to_dict() if hasattr(tool_info, 'to_dict') else tool_info
            await self.store_tool_knowledge(tool_dict)
            return tool_dict

        return {"name": tool_name, "error": "Could not find instructions for this tool"}

    async def _research_specific_tool(self, tool_name: str) -> Optional[ToolInfoData]:
        """Research a specific tool comprehensively - REFACTORED to use ResearchResultsProcessor"""
        # Multiple research queries for comprehensive documentation
        research_queries = {
            "installation": f"how to install {tool_name} linux ubuntu debian",
            "usage": f"{tool_name} tutorial examples command line",
            "advanced": f"{tool_name} advanced usage options flags",
            "troubleshooting": f"{tool_name} common errors problems solutions",
            "integration": f"{tool_name} integration with other tools pipes",
            "security": f"{tool_name} security considerations best practices",
        }

        # Execute all research queries in parallel for better performance
        async def execute_query(query_type: str, query: str) -> tuple:
            try:
                result = await self.web_assistant.research_query(query)
                if result.get("status") == "success":
                    return (query_type, result)
                return (query_type, None)
            except Exception as e:
                logger.debug(f"Research query failed for {query_type}: {e}")
                return (query_type, None)

        # Run all queries in parallel
        query_results = await asyncio.gather(
            *[execute_query(qt, q) for qt, q in research_queries.items()],
            return_exceptions=True
        )

        # Collect successful results
        results = {}
        for item in query_results:
            if isinstance(item, Exception):
                continue
            query_type, result = item
            if result is not None:
                results[query_type] = result

        if not results:
            return None

        # REFACTORED: Use ResearchResultsProcessor instead of direct dict manipulation
        processor = ResearchResultsProcessor(tool_name, results)
        tool_type = self._determine_tool_type(tool_name)
        category = self._categorize_tool(tool_name, "")
        tool_info = processor.build_tool_info(tool_type, category)

        return tool_info

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

    async def _store_tool_research_results(
        self, tool_type: str, tools: List[Dict[str, Any]]
    ):
        """Store research results in KB for future use"""
        if not tools:
            return

        # Create a summary document
        summary_content = f"""
Tool Research Results: {tool_type}
Date: {datetime.now().isoformat()}

Found {len(tools)} tools for {tool_type}:

"""
        # Build tool summaries using list + join (O(n)) instead of += (O(n²))
        tool_summaries = [
            f"""
{i}. {tool['name']}
   Purpose: {tool.get('purpose', 'N/A')}
   Installation: {tool.get('installation', 'N/A')[:200]}...
"""
            for i, tool in enumerate(tools, 1)
        ]
        summary_content += "".join(tool_summaries)

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
                "purpose": TextExtractor.extract_purpose(summary, tool_name),
                "features": TextExtractor.extract_features(summary),
                "platform": "linux",  # Default assumption
                "category": self._categorize_tool(tool_name, summary),
            }

            return info

        return None

    async def store_system_documentation(self, doc_info: Dict[str, Any]):
        """Store general system documentation and procedures"""
        doc_type = doc_info.get("type", "general")
        doc_title = doc_info.get("title", "System Documentation")

        document_content = f"""
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

    async def store_workflow_knowledge(self, workflow_info: Dict[str, Any]):
        """Store complete workflow documentation for complex procedures"""
        workflow_name = workflow_info.get("name", "Unknown Workflow")

        document_content = f"""
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
