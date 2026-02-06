# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Man Page Knowledge Integrator for AutoBot
Scrapes, parses, and integrates Linux man pages into machine-aware knowledge system
"""

import asyncio
import json
import logging
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, FrozenSet, List, Optional, Set, Tuple

import aiofiles
import yaml

from intelligence.os_detector import get_os_detector
from utils.command_utils import execute_command

logger = logging.getLogger(__name__)

# Issue #380: Module-level frozenset for common command line starters
_COMMON_COMMAND_STARTERS: FrozenSet[str] = frozenset(
    {"ls", "cat", "grep", "find", "awk", "sed"}
)


@dataclass
class ManPageInfo:
    """Structured information from a man page"""

    command: str
    section: int
    title: str
    description: str
    synopsis: str
    options: List[Dict[str, str]]
    examples: List[Dict[str, str]]
    see_also: List[str]
    file_path: Optional[str] = None
    last_updated: Optional[str] = None
    machine_id: Optional[str] = None


class ManPageParser:
    """Parser for extracting structured data from man page content"""

    def __init__(self):
        """Initialize man page parser with section regex patterns."""
        self.section_patterns = {
            "name": re.compile(r"^NAME\s*$", re.IGNORECASE | re.MULTILINE),
            "synopsis": re.compile(r"^SYNOPSIS\s*$", re.IGNORECASE | re.MULTILINE),
            "description": re.compile(
                r"^DESCRIPTION\s*$", re.IGNORECASE | re.MULTILINE
            ),
            "options": re.compile(r"^OPTIONS\s*$", re.IGNORECASE | re.MULTILINE),
            "examples": re.compile(r"^EXAMPLES?\s*$", re.IGNORECASE | re.MULTILINE),
            "see_also": re.compile(r"^SEE ALSO\s*$", re.IGNORECASE | re.MULTILINE),
        }

    def parse_man_page(
        self, content: str, command: str, section: int = 1
    ) -> ManPageInfo:
        """Parse man page content into structured data"""
        sections = self._split_into_sections(content)

        # Extract basic info
        name_section = sections.get("name", "")
        title, description = self._parse_name_section(name_section)

        # Extract synopsis
        synopsis = sections.get("synopsis", "").strip()

        # Extract options
        options = self._parse_options_section(sections.get("options", ""))

        # Extract examples
        examples = self._parse_examples_section(sections.get("examples", ""))

        # Extract see also
        see_also = self._parse_see_also_section(sections.get("see_also", ""))

        return ManPageInfo(
            command=command,
            section=section,
            title=title or f"{command} manual page",
            description=description or f"Manual page for {command}",
            synopsis=synopsis,
            options=options,
            examples=examples,
            see_also=see_also,
            last_updated=time.strftime("%Y-%m-%dT%H:%M:%S"),
        )

    def _split_into_sections(self, content: str) -> Dict[str, str]:
        """Split man page content into sections"""
        sections = {}
        current_section = None
        current_content = []

        lines = content.split("\n")

        for line in lines:
            # Check if this line is a section header
            section_found = None
            for section_name, pattern in self.section_patterns.items():
                if pattern.match(line.strip()):
                    section_found = section_name
                    break

            if section_found:
                # Save previous section
                if current_section:
                    sections[current_section] = "\n".join(current_content).strip()

                # Start new section
                current_section = section_found
                current_content = []
            else:
                # Add line to current section
                if current_section:
                    current_content.append(line)

        # Save final section
        if current_section:
            sections[current_section] = "\n".join(current_content).strip()

        return sections

    def _parse_name_section(self, content: str) -> Tuple[str, str]:
        """Parse NAME section to extract title and description"""
        if not content:
            return "", ""

        # Look for pattern: command - description
        match = re.search(
            r"^(\w+(?:\s*,\s*\w+)*)\s*[-–]\s*(.+)$", content.strip(), re.MULTILINE
        )
        if match:
            title = match.group(1).strip()
            description = match.group(2).strip()
            return title, description

        return "", content.strip()

    def _parse_options_section(self, content: str) -> List[Dict[str, str]]:
        """Parse OPTIONS section to extract command options"""
        if not content:
            return []

        options = []

        # Look for option patterns like: -f, --flag
        option_pattern = re.compile(
            r"^\s*(-\w+(?:,\s*--\w+[-\w]*)*|\s*--\w+[-\w]*)\s+(.*?)(?=^\s*-|\Z)",
            re.MULTILINE | re.DOTALL,
        )

        matches = option_pattern.findall(content)

        for option_text, description in matches:
            options.append(
                {
                    "flag": option_text.strip(),
                    "description": " ".join(
                        description.split()
                    ),  # Normalize whitespace
                }
            )

        return options

    def _parse_examples_section(self, content: str) -> List[Dict[str, str]]:
        """Parse EXAMPLES section to extract usage examples"""
        if not content:
            return []

        examples = []

        # Split by common example indicators
        example_blocks = re.split(
            r"\n\s*\n|\n\s*Example\s*\d*[:.]\s*|\n\s*•\s*", content
        )

        for block in example_blocks:
            block = block.strip()
            if not block:
                continue

            # Look for command lines (starting with $ or command name)
            lines = block.split("\n")
            command_line = None
            description_lines = []

            for line in lines:
                line = line.strip()
                if line.startswith("$") or line.startswith("# "):
                    command_line = line.lstrip("$# ").strip()
                elif command_line is None and any(
                    line.startswith(cmd) for cmd in _COMMON_COMMAND_STARTERS
                ):
                    command_line = line
                else:
                    description_lines.append(line)

            if command_line:
                examples.append(
                    {
                        "command": command_line,
                        "description": (
                            " ".join(description_lines).strip() or "Example usage"
                        ),
                    }
                )

        return examples

    def _parse_see_also_section(self, content: str) -> List[str]:
        """Parse SEE ALSO section to extract related commands"""
        if not content:
            return []

        # Extract command references like: command(1), another(8)
        pattern = re.compile(r"\b(\w+)\(\d+\)")
        matches = pattern.findall(content)

        return list(set(matches))  # Remove duplicates


class ManPageKnowledgeIntegrator:
    """Main service for integrating man pages into machine-aware knowledge"""

    def _get_network_commands(self) -> list:
        """Get network-related priority commands. Issue #620."""
        return [
            "ping",
            "curl",
            "wget",
            "netstat",
            "ss",
            "nmap",
            "arp",
            "dig",
            "nslookup",
            "traceroute",
            "ifconfig",
            "ip",
            "iptables",
            "ufw",
        ]

    def _get_file_operation_commands(self) -> list:
        """Get file operation priority commands. Issue #620."""
        return [
            "ls",
            "find",
            "grep",
            "cat",
            "head",
            "tail",
            "less",
            "more",
            "wc",
            "sort",
            "uniq",
            "cut",
            "awk",
            "sed",
            "tar",
            "zip",
            "unzip",
            "gzip",
        ]

    def _get_system_monitoring_commands(self) -> list:
        """Get system monitoring priority commands. Issue #620."""
        return [
            "ps",
            "top",
            "htop",
            "df",
            "du",
            "free",
            "uname",
            "whoami",
            "id",
            "groups",
            "sudo",
            "su",
            "systemctl",
            "service",
            "crontab",
        ]

    def _get_development_commands(self) -> list:
        """Get development tool priority commands. Issue #620."""
        return [
            "git",
            "python",
            "python3",
            "node",
            "npm",
            "docker",
            "docker-compose",
            "vim",
            "nano",
            "emacs",
            "make",
            "gcc",
            "g++",
        ]

    def _get_security_commands(self) -> list:
        """Get security tool priority commands. Issue #620."""
        return [
            "ssh",
            "scp",
            "rsync",
            "gpg",
            "openssl",
            "chmod",
            "chown",
            "chgrp",
            "passwd",
            "useradd",
            "usermod",
            "userdel",
            "groupadd",
        ]

    def _get_priority_commands(self) -> list:
        """Get combined priority commands list. Issue #620."""
        commands = []
        commands.extend(self._get_network_commands())
        commands.extend(self._get_file_operation_commands())
        commands.extend(self._get_system_monitoring_commands())
        commands.extend(self._get_development_commands())
        commands.extend(self._get_security_commands())
        return commands

    def __init__(self):
        """Initialize knowledge integrator (Issue #398: refactored)."""
        self.parser = ManPageParser()
        self.knowledge_base_dir = Path("data/system_knowledge")
        self.man_cache_dir = self.knowledge_base_dir / "man_pages"
        self.man_cache_dir.mkdir(parents=True, exist_ok=True)
        self.priority_commands = self._get_priority_commands()

    async def get_available_commands(self) -> Set[str]:
        """Get list of commands available on current machine"""
        detector = await get_os_detector()
        os_info = await detector.detect_system()

        return os_info.capabilities

    async def check_man_page_exists(self, command: str) -> bool:
        """Check if man page exists for command.

        Issue #751: Uses centralized execute_command from command_utils.
        """
        result = await execute_command(["man", "-w", command], timeout=5.0)
        return result.return_code == 0

    async def extract_man_page(
        self, command: str, section: int = 1
    ) -> Optional[ManPageInfo]:
        """Extract and parse man page for a command.

        Issue #751: Uses centralized execute_command from command_utils.
        """
        try:
            result = await execute_command(["man", str(section), command], timeout=10.0)

            if result.status == "timeout":
                logger.warning("Timeout extracting man page for %s", command)
                return None

            if result.return_code != 0:
                logger.debug("Man page not found for %s(%s)", command, section)
                return None

            # Parse the content
            man_info = self.parser.parse_man_page(result.stdout, command, section)

            # Add machine context
            detector = await get_os_detector()
            os_info = await detector.detect_system()

            if hasattr(os_info, "machine_id"):
                man_info.machine_id = getattr(os_info, "machine_id", "unknown")

            logger.info("Extracted man page for %s(%s)", command, section)
            return man_info

        except Exception as e:
            logger.error("Error extracting man page for %s: %s", command, e)
            return None

    async def cache_man_page(self, man_info: ManPageInfo) -> Path:
        """Cache parsed man page data to disk"""
        cache_file = self.man_cache_dir / f"{man_info.command}_{man_info.section}.json"

        # Convert to dict for JSON serialization
        man_data = {
            "command": man_info.command,
            "section": man_info.section,
            "title": man_info.title,
            "description": man_info.description,
            "synopsis": man_info.synopsis,
            "options": man_info.options,
            "examples": man_info.examples,
            "see_also": man_info.see_also,
            "last_updated": man_info.last_updated,
            "machine_id": man_info.machine_id,
        }

        # Use aiofiles for non-blocking file I/O
        try:
            async with aiofiles.open(cache_file, "w", encoding="utf-8") as f:
                await f.write(json.dumps(man_data, indent=2))
            logger.info("Cached man page for %s to %s", man_info.command, cache_file)
        except OSError as e:
            logger.error("Failed to cache man page to %s: %s", cache_file, e)
        return cache_file

    async def load_cached_man_page(
        self, command: str, section: int = 1
    ) -> Optional[ManPageInfo]:
        """Load cached man page data from disk"""
        cache_file = self.man_cache_dir / f"{command}_{section}.json"

        # Issue #358 - avoid blocking
        if not await asyncio.to_thread(cache_file.exists):
            return None

        try:
            async with aiofiles.open(cache_file, "r", encoding="utf-8") as f:
                content = await f.read()
                data = json.loads(content)

            return ManPageInfo(
                command=data["command"],
                section=data["section"],
                title=data["title"],
                description=data["description"],
                synopsis=data["synopsis"],
                options=data["options"],
                examples=data["examples"],
                see_also=data["see_also"],
                last_updated=data.get("last_updated"),
                machine_id=data.get("machine_id"),
            )

        except OSError as e:
            logger.error("Failed to read cached man page %s: %s", cache_file, e)
            return None
        except json.JSONDecodeError as e:
            logger.error("Failed to parse cached man page JSON %s: %s", cache_file, e)
            return None
        except Exception as e:
            logger.error("Error processing cached man page %s: %s", cache_file, e)
            return None

    def convert_to_knowledge_yaml(self, man_info: ManPageInfo) -> Dict[str, Any]:
        """Convert man page info to AutoBot knowledge format"""
        # Build usage examples from man page examples
        common_examples = []
        for example in man_info.examples:
            common_examples.append(
                {
                    "description": example["description"],
                    "command": example["command"],
                    "expected_output": "See man page for detailed output format",
                }
            )

        # Build tool entry
        tool_entry = {
            "name": man_info.command,
            "type": "command_line_tool",
            "purpose": man_info.description,
            "installation": {"system": "Pre-installed on most Linux systems"},
            "usage": {
                "basic": (
                    man_info.synopsis
                    if man_info.synopsis
                    else f"{man_info.command} [options]"
                )
            },
            "common_examples": common_examples,
            "options": [
                f"{opt['flag']}: {opt['description']}" for opt in man_info.options
            ],
            "related_tools": man_info.see_also,
            "man_page_section": man_info.section,
            "last_updated": man_info.last_updated,
            "source": f"man {man_info.command}({man_info.section})",
        }

        # Create knowledge YAML structure
        knowledge_data = {
            "metadata": {
                "category": "system_commands",
                "description": f"Manual page information for {man_info.command}",
                "last_updated": man_info.last_updated,
                "version": "1.0.0",
                "source": "man_pages",
                "machine_id": man_info.machine_id,
            },
            "tools": [tool_entry],
        }

        return knowledge_data

    async def _process_single_command(
        self, command: str, results: Dict[str, Any]
    ) -> None:
        """Process single command integration (Issue #398: extracted)."""
        results["processed"] += 1
        try:
            cached_info = await self.load_cached_man_page(command)
            if cached_info:
                results["cached"] += 1
                results["commands"][command] = "cached"
                return
            if not await self.check_man_page_exists(command):
                results["failed"] += 1
                results["commands"][command] = "no_man_page"
                return
            man_info = await self.extract_man_page(command)
            if not man_info:
                results["failed"] += 1
                results["commands"][command] = "extraction_failed"
                return
            await self.cache_man_page(man_info)
            await self._save_as_knowledge_yaml(man_info)
            results["successful"] += 1
            results["commands"][command] = "success"
            logger.info("Successfully integrated man page for %s", command)
        except Exception as e:
            results["failed"] += 1
            results["commands"][command] = f"error: {str(e)}"
            logger.error("Failed to integrate man page for %s: %s", command, e)

    async def integrate_priority_commands(self) -> Dict[str, Any]:
        """Extract and integrate man pages (Issue #398: refactored)."""
        logger.info("Starting man page integration for priority commands...")
        available_commands = await self.get_available_commands()
        commands_to_process = [
            cmd for cmd in self.priority_commands if cmd in available_commands
        ]
        logger.info(
            "Processing %d priority commands available on this machine",
            len(commands_to_process),
        )
        results = {
            "processed": 0,
            "successful": 0,
            "failed": 0,
            "cached": 0,
            "commands": {},
        }
        for command in commands_to_process:
            await self._process_single_command(command, results)
        logger.info(
            "Man page integration complete: %d successful, %d failed, %d cached",
            results["successful"],
            results["failed"],
            results["cached"],
        )
        return results

    async def _save_as_knowledge_yaml(self, man_info: ManPageInfo):
        """Save man page as knowledge YAML file"""
        # Determine the appropriate knowledge directory
        machine_dir = (
            self.knowledge_base_dir / "machines" / (man_info.machine_id or "default")
        )
        man_knowledge_dir = machine_dir / "man_pages"
        # Issue #358 - avoid blocking
        await asyncio.to_thread(man_knowledge_dir.mkdir, parents=True, exist_ok=True)

        # Convert to knowledge format
        knowledge_data = self.convert_to_knowledge_yaml(man_info)

        # Save as YAML using aiofiles for non-blocking I/O
        yaml_file = man_knowledge_dir / f"{man_info.command}.yaml"
        try:
            async with aiofiles.open(yaml_file, "w", encoding="utf-8") as f:
                await f.write(
                    yaml.dump(knowledge_data, default_flow_style=False, indent=2)
                )
            logger.info(
                f"Saved man page knowledge for {man_info.command} to {yaml_file}"
            )
        except OSError as e:
            logger.error(f"Failed to save man page knowledge to {yaml_file}: {e}")

    async def search_man_pages(self, query: str) -> List[ManPageInfo]:
        """Search cached man pages by query"""
        results = []

        # Search through cached man pages
        # Issue #358 - avoid blocking with lambda for proper glob() execution in thread
        cache_files = await asyncio.to_thread(
            lambda: list(self.man_cache_dir.glob("*.json"))
        )
        for cache_file in cache_files:
            man_info = await self.load_cached_man_page(
                cache_file.stem.split("_")[0], int(cache_file.stem.split("_")[1])
            )

            if not man_info:
                continue

            # Simple text search in title, description, and options
            # Issue #383 - Build searchable text with list join instead of +=
            searchable_parts = [
                man_info.title.lower(),
                man_info.description.lower(),
            ]
            searchable_parts.extend(
                opt["description"].lower() for opt in man_info.options
            )
            searchable_text = " ".join(searchable_parts)

            if query.lower() in searchable_text:
                results.append(man_info)

        return results

    async def update_man_page_cache(self, max_age_days: int = 7):
        """Update man page cache for commands older than max_age_days"""
        logger.info("Updating man page cache (max age: %s days)", max_age_days)

        current_time = time.time()
        max_age_seconds = max_age_days * 24 * 60 * 60

        updated_count = 0

        # Issue #358 - avoid blocking with lambda for proper glob() execution in thread
        cache_files = await asyncio.to_thread(
            lambda: list(self.man_cache_dir.glob("*.json"))
        )
        for cache_file in cache_files:
            # Check file age
            # Issue #358 - avoid blocking stat()
            file_stat = await asyncio.to_thread(cache_file.stat)
            if current_time - file_stat.st_mtime > max_age_seconds:
                command = cache_file.stem.split("_")[0]
                section = int(cache_file.stem.split("_")[1])

                logger.info("Updating cached man page for %s(%s)", command, section)

                # Re-extract man page
                man_info = await self.extract_man_page(command, section)
                if man_info:
                    await self.cache_man_page(man_info)
                    await self._save_as_knowledge_yaml(man_info)
                    updated_count += 1

        logger.info("Updated %s man page cache entries", updated_count)
        return updated_count


# Global integrator instance (thread-safe)
import asyncio as _asyncio_lock

_integrator_instance: Optional[ManPageKnowledgeIntegrator] = None
_integrator_lock = _asyncio_lock.Lock()


async def get_man_page_integrator() -> ManPageKnowledgeIntegrator:
    """Get singleton man page integrator instance (thread-safe)."""
    global _integrator_instance
    if _integrator_instance is None:
        async with _integrator_lock:
            # Double-check after acquiring lock
            if _integrator_instance is None:
                _integrator_instance = ManPageKnowledgeIntegrator()
    return _integrator_instance


if __name__ == "__main__":
    """Test the man page integration functionality"""

    async def test_integration():
        """Run integration tests for man page extraction and caching."""
        integrator = await get_man_page_integrator()

        print("=== Man Page Integration Test ===")

        # Test single command extraction
        print("\n1. Testing single command extraction (ls)...")
        man_info = await integrator.extract_man_page("ls")
        if man_info:
            print(f"✓ Extracted man page for {man_info.command}")
            print(f"  Title: {man_info.title}")
            print(f"  Description: {man_info.description[:100]}...")
            print(f"  Options: {len(man_info.options)}")
            print(f"  Examples: {len(man_info.examples)}")
        else:
            print("✗ Failed to extract man page for ls")

        # Test caching
        print("\n2. Testing caching...")
        if man_info:
            cache_file = await integrator.cache_man_page(man_info)
            print(f"✓ Cached to {cache_file}")

            # Test loading from cache
            loaded_info = await integrator.load_cached_man_page("ls")
            if loaded_info:
                print("✓ Successfully loaded from cache")
            else:
                print("✗ Failed to load from cache")

        # Test priority commands integration
        print("\n3. Testing priority commands integration...")
        results = await integrator.integrate_priority_commands()
        print("✓ Integration results:")
        print(f"  Processed: {results['processed']}")
        print(f"  Successful: {results['successful']}")
        print(f"  Failed: {results['failed']}")
        print(f"  Cached: {results['cached']}")

        # Show some successful commands
        successful_commands = [
            cmd for cmd, status in results["commands"].items() if status == "success"
        ][:5]
        if successful_commands:
            print(f"  Sample successful commands: {', '.join(successful_commands)}")

    asyncio.run(test_integration())
