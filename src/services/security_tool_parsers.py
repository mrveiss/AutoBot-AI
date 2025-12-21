# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Security Tool Output Parsers

Parses output from security tools into structured data for storage in Memory MCP.
Supports: nmap, masscan, nuclei, nikto (extensible)

Issue: #260
"""

import logging
import re
import xml.etree.ElementTree as ET
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

logger = logging.getLogger(__name__)

# Issue #380: Pre-compiled regex patterns for security tool parsing
_NUCLEI_FORMAT_RE = re.compile(r"\[\w+\]\s+\[[^\]]+\]\s+\[")
_URL_HOST_RE = re.compile(r"(?:https?://)?([^:/]+)")
_URL_PORT_RE = re.compile(r":(\d+)")


@dataclass
class ParsedHost:
    """Parsed host information from tool output."""

    ip: str
    hostname: Optional[str] = None
    status: str = "up"
    mac_address: Optional[str] = None
    vendor: Optional[str] = None
    os_guess: Optional[str] = None
    ports: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ParsedPort:
    """Parsed port information."""

    port: int
    protocol: str = "tcp"
    state: str = "open"
    service: Optional[str] = None
    version: Optional[str] = None
    product: Optional[str] = None
    extra_info: Optional[str] = None
    scripts: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class ParsedVulnerability:
    """Parsed vulnerability information."""

    host: str
    port: Optional[int] = None
    cve_id: Optional[str] = None
    title: str = ""
    severity: str = "unknown"
    description: str = ""
    references: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ParsedToolOutput:
    """Unified output from any security tool parser."""

    tool: str
    scan_type: str
    timestamp: str
    hosts: list[ParsedHost] = field(default_factory=list)
    vulnerabilities: list[ParsedVulnerability] = field(default_factory=list)
    raw_output: str = ""
    command: Optional[str] = None
    scan_stats: dict[str, Any] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "tool": self.tool,
            "scan_type": self.scan_type,
            "timestamp": self.timestamp,
            "hosts": [
                {
                    "ip": h.ip,
                    "hostname": h.hostname,
                    "status": h.status,
                    "mac_address": h.mac_address,
                    "vendor": h.vendor,
                    "os_guess": h.os_guess,
                    "ports": h.ports,
                    "metadata": h.metadata,
                }
                for h in self.hosts
            ],
            "vulnerabilities": [
                {
                    "host": v.host,
                    "port": v.port,
                    "cve_id": v.cve_id,
                    "title": v.title,
                    "severity": v.severity,
                    "description": v.description,
                    "references": v.references,
                    "metadata": v.metadata,
                }
                for v in self.vulnerabilities
            ],
            "command": self.command,
            "scan_stats": self.scan_stats,
            "errors": self.errors,
        }


class BaseToolParser(ABC):
    """Abstract base class for security tool parsers."""

    TOOL_NAME: str = "unknown"

    @abstractmethod
    def parse(self, output: str) -> ParsedToolOutput:
        """
        Parse tool output into structured data.

        Args:
            output: Raw tool output (text, XML, JSON, etc.)

        Returns:
            ParsedToolOutput with structured data
        """

    @abstractmethod
    def can_parse(self, output: str) -> bool:
        """
        Check if this parser can handle the given output.

        Args:
            output: Raw output to check

        Returns:
            True if this parser can handle the output
        """

    def _create_output(
        self,
        scan_type: str = "unknown",
        command: Optional[str] = None,
    ) -> ParsedToolOutput:
        """Create a new ParsedToolOutput with defaults."""
        return ParsedToolOutput(
            tool=self.TOOL_NAME,
            scan_type=scan_type,
            timestamp=datetime.now(timezone.utc).isoformat(),
            command=command,
        )


class NmapParser(BaseToolParser):
    """Parser for nmap output (XML, grepable, and text formats)."""

    TOOL_NAME = "nmap"

    # Patterns for text output parsing
    HOST_PATTERN = re.compile(r"Nmap scan report for (?:(\S+) \()?(\d+\.\d+\.\d+\.\d+)")
    PORT_PATTERN = re.compile(
        r"(\d+)/(tcp|udp)\s+(\w+)\s+(\S+)(?:\s+(.+))?"
    )
    OS_PATTERN = re.compile(r"OS details?: (.+)")
    MAC_PATTERN = re.compile(r"MAC Address: ([0-9A-F:]+)(?: \((.+)\))?", re.IGNORECASE)

    # Grepable format patterns
    GREP_HOST_PATTERN = re.compile(r"Host: (\d+\.\d+\.\d+\.\d+) \(([^)]*)\)")
    GREP_PORT_PATTERN = re.compile(r"(\d+)/(open|closed|filtered)/(tcp|udp)//([^/]*)/")

    def can_parse(self, output: str) -> bool:
        """Check if output is from nmap."""
        output_lower = output.lower()
        return (
            "nmap" in output_lower
            or "<?xml" in output and "nmaprun" in output
            or "Nmap scan report" in output
            or output.startswith("Host:")
        )

    def parse(self, output: str) -> ParsedToolOutput:
        """Parse nmap output in any format."""
        output = output.strip()

        # Detect format and parse accordingly
        if output.startswith("<?xml") or "<nmaprun" in output:
            return self._parse_xml(output)
        elif output.startswith("Host:") or "# Nmap" in output:
            return self._parse_grepable(output)
        else:
            return self._parse_text(output)

    def _parse_xml(self, xml_output: str) -> ParsedToolOutput:
        """Parse nmap XML output."""
        result = self._create_output(scan_type="xml")

        try:
            root = ET.fromstring(xml_output)

            # Get scan info
            if root.get("args"):
                result.command = root.get("args")

            # Parse hosts
            for host_elem in root.findall(".//host"):
                host = self._parse_xml_host(host_elem)
                if host:
                    result.hosts.append(host)

            # Get scan stats
            runstats = root.find(".//runstats/finished")
            if runstats is not None:
                result.scan_stats = {
                    "elapsed": runstats.get("elapsed"),
                    "exit": runstats.get("exit"),
                    "time": runstats.get("timestr"),
                }

            hosts_elem = root.find(".//runstats/hosts")
            if hosts_elem is not None:
                result.scan_stats.update({
                    "hosts_up": int(hosts_elem.get("up", 0)),
                    "hosts_down": int(hosts_elem.get("down", 0)),
                    "hosts_total": int(hosts_elem.get("total", 0)),
                })

        except ET.ParseError as e:
            result.errors.append(f"XML parse error: {e}")
            logger.error("Failed to parse nmap XML: %s", e)

        return result

    def _parse_xml_host(self, host_elem: ET.Element) -> Optional[ParsedHost]:
        """Parse a single host from XML."""
        # Get IP address
        addr_elem = host_elem.find("address[@addrtype='ipv4']")
        if addr_elem is None:
            return None

        ip = addr_elem.get("addr", "")
        if not ip:
            return None

        host = ParsedHost(ip=ip)

        # Get hostname
        hostname_elem = host_elem.find(".//hostname")
        if hostname_elem is not None:
            host.hostname = hostname_elem.get("name")

        # Get MAC address
        mac_elem = host_elem.find("address[@addrtype='mac']")
        if mac_elem is not None:
            host.mac_address = mac_elem.get("addr")
            host.vendor = mac_elem.get("vendor")

        # Get host status
        status_elem = host_elem.find("status")
        if status_elem is not None:
            host.status = status_elem.get("state", "unknown")

        # Get OS guess
        osmatch = host_elem.find(".//osmatch")
        if osmatch is not None:
            host.os_guess = osmatch.get("name")

        # Parse ports
        for port_elem in host_elem.findall(".//port"):
            port_data = self._parse_xml_port(port_elem)
            if port_data:
                host.ports.append(port_data)

        return host

    def _parse_xml_port(self, port_elem: ET.Element) -> Optional[dict[str, Any]]:
        """Parse a single port from XML."""
        port_num = port_elem.get("portid")
        protocol = port_elem.get("protocol", "tcp")

        if not port_num:
            return None

        state_elem = port_elem.find("state")
        state = state_elem.get("state", "unknown") if state_elem is not None else "unknown"

        service_elem = port_elem.find("service")
        service = None
        version = None
        product = None
        extra_info = None

        if service_elem is not None:
            service = service_elem.get("name")
            product = service_elem.get("product")
            version = service_elem.get("version")
            extra_info = service_elem.get("extrainfo")

        # Parse scripts
        scripts = []
        for script_elem in port_elem.findall("script"):
            scripts.append({
                "id": script_elem.get("id"),
                "output": script_elem.get("output"),
            })

        return {
            "port": int(port_num),
            "protocol": protocol,
            "state": state,
            "service": service,
            "product": product,
            "version": version,
            "extra_info": extra_info,
            "scripts": scripts,
        }

    def _parse_grepable(self, output: str) -> ParsedToolOutput:
        """Parse nmap grepable output."""
        result = self._create_output(scan_type="grepable")

        for line in output.split("\n"):
            line = line.strip()
            if not line or line.startswith("#"):
                continue

            # Parse host line
            host_match = self.GREP_HOST_PATTERN.search(line)
            if host_match:
                ip = host_match.group(1)
                hostname = host_match.group(2) or None

                host = ParsedHost(ip=ip, hostname=hostname, status="up")

                # Parse ports from same line
                for port_match in self.GREP_PORT_PATTERN.finditer(line):
                    port_data = {
                        "port": int(port_match.group(1)),
                        "state": port_match.group(2),
                        "protocol": port_match.group(3),
                        "service": port_match.group(4) or None,
                    }
                    host.ports.append(port_data)

                result.hosts.append(host)

        return result

    def _parse_text(self, output: str) -> ParsedToolOutput:
        """Parse nmap normal text output."""
        result = self._create_output(scan_type="text")

        current_host: Optional[ParsedHost] = None
        lines = output.split("\n")

        for line in lines:
            line = line.strip()

            # Check for host line
            host_match = self.HOST_PATTERN.search(line)
            if host_match:
                # Save previous host
                if current_host:
                    result.hosts.append(current_host)

                hostname = host_match.group(1)
                ip = host_match.group(2)
                current_host = ParsedHost(ip=ip, hostname=hostname, status="up")
                continue

            if current_host:
                # Check for port line
                port_match = self.PORT_PATTERN.match(line)
                if port_match:
                    port_data = {
                        "port": int(port_match.group(1)),
                        "protocol": port_match.group(2),
                        "state": port_match.group(3),
                        "service": port_match.group(4),
                        "version": port_match.group(5),
                    }
                    current_host.ports.append(port_data)
                    continue

                # Check for OS
                os_match = self.OS_PATTERN.search(line)
                if os_match:
                    current_host.os_guess = os_match.group(1)
                    continue

                # Check for MAC
                mac_match = self.MAC_PATTERN.search(line)
                if mac_match:
                    current_host.mac_address = mac_match.group(1)
                    current_host.vendor = mac_match.group(2)
                    continue

        # Don't forget the last host
        if current_host:
            result.hosts.append(current_host)

        return result


class MasscanParser(BaseToolParser):
    """Parser for masscan output."""

    TOOL_NAME = "masscan"

    # Pattern for masscan output lines
    LINE_PATTERN = re.compile(
        r"Discovered open port (\d+)/(tcp|udp) on (\d+\.\d+\.\d+\.\d+)"
    )
    JSON_PORT_PATTERN = re.compile(r'"port":\s*(\d+)')

    def can_parse(self, output: str) -> bool:
        """Check if output is from masscan."""
        return (
            "masscan" in output.lower()
            or "Discovered open port" in output
            or ('"ports"' in output and '"ip"' in output)
        )

    def parse(self, output: str) -> ParsedToolOutput:
        """Parse masscan output."""
        result = self._create_output(scan_type="masscan")

        # Track hosts by IP
        hosts_map: dict[str, ParsedHost] = {}

        for line in output.split("\n"):
            line = line.strip()

            match = self.LINE_PATTERN.search(line)
            if match:
                port = int(match.group(1))
                protocol = match.group(2)
                ip = match.group(3)

                if ip not in hosts_map:
                    hosts_map[ip] = ParsedHost(ip=ip, status="up")

                hosts_map[ip].ports.append({
                    "port": port,
                    "protocol": protocol,
                    "state": "open",
                })

        result.hosts = list(hosts_map.values())
        return result


class NucleiParser(BaseToolParser):
    """Parser for nuclei vulnerability scanner output."""

    TOOL_NAME = "nuclei"

    # Pattern for nuclei output
    # [severity] [template-id] [protocol] url [matcher]
    LINE_PATTERN = re.compile(
        r"\[(\w+)\]\s+\[([^\]]+)\]\s+\[([^\]]+)\]\s+(\S+)"
    )

    def can_parse(self, output: str) -> bool:
        """Check if output is from nuclei."""
        # Issue #380: use pre-compiled pattern
        return "nuclei" in output.lower() or _NUCLEI_FORMAT_RE.search(output) is not None

    def parse(self, output: str) -> ParsedToolOutput:
        """Parse nuclei output."""
        result = self._create_output(scan_type="nuclei")

        for line in output.split("\n"):
            line = line.strip()

            match = self.LINE_PATTERN.search(line)
            if match:
                severity = match.group(1).lower()
                template_id = match.group(2)
                protocol = match.group(3)
                url = match.group(4)

                # Extract host from URL (Issue #380: use pre-compiled pattern)
                host_match = _URL_HOST_RE.search(url)
                host = host_match.group(1) if host_match else url

                # Extract port from URL (Issue #380: use pre-compiled pattern)
                port_match = _URL_PORT_RE.search(url)
                port = int(port_match.group(1)) if port_match else None

                vuln = ParsedVulnerability(
                    host=host,
                    port=port,
                    title=template_id,
                    severity=severity,
                    description=f"Nuclei finding: {template_id}",
                    metadata={
                        "template_id": template_id,
                        "protocol": protocol,
                        "url": url,
                    },
                )
                result.vulnerabilities.append(vuln)

        return result


class ToolParserRegistry:
    """Registry of available tool parsers with auto-detection."""

    def __init__(self) -> None:
        """Initialize tool parser registry with default security tool parsers."""
        self._parsers: list[BaseToolParser] = [
            NmapParser(),
            MasscanParser(),
            NucleiParser(),
        ]

    def register(self, parser: BaseToolParser) -> None:
        """Register a new parser."""
        self._parsers.append(parser)

    def detect_and_parse(self, output: str) -> Optional[ParsedToolOutput]:
        """
        Auto-detect tool and parse output.

        Args:
            output: Raw tool output

        Returns:
            ParsedToolOutput or None if no parser matches
        """
        for parser in self._parsers:
            if parser.can_parse(output):
                logger.info("Detected tool: %s", parser.TOOL_NAME)
                try:
                    return parser.parse(output)
                except Exception as e:
                    logger.error("Parser %s failed: %s", parser.TOOL_NAME, e)
                    continue

        logger.warning("No parser matched the output")
        return None

    def parse_with_tool(self, output: str, tool: str) -> Optional[ParsedToolOutput]:
        """
        Parse output with a specific tool parser.

        Args:
            output: Raw tool output
            tool: Tool name (nmap, masscan, nuclei)

        Returns:
            ParsedToolOutput or None if parser not found
        """
        for parser in self._parsers:
            if parser.TOOL_NAME.lower() == tool.lower():
                return parser.parse(output)

        logger.warning("No parser found for tool: %s", tool)
        return None


# Singleton registry (thread-safe)
import threading

_parser_registry: Optional[ToolParserRegistry] = None
_parser_registry_lock = threading.Lock()


def get_parser_registry() -> ToolParserRegistry:
    """Get or create the parser registry singleton (thread-safe)."""
    global _parser_registry
    if _parser_registry is None:
        with _parser_registry_lock:
            # Double-check after acquiring lock
            if _parser_registry is None:
                _parser_registry = ToolParserRegistry()
    return _parser_registry


def parse_tool_output(
    output: str,
    tool: Optional[str] = None,
) -> Optional[ParsedToolOutput]:
    """
    Convenience function to parse tool output.

    Args:
        output: Raw tool output
        tool: Optional tool name (auto-detects if not provided)

    Returns:
        ParsedToolOutput or None
    """
    registry = get_parser_registry()

    if tool:
        return registry.parse_with_tool(output, tool)
    else:
        return registry.detect_and_parse(output)
