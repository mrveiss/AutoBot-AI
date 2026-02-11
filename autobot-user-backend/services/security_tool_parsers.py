# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Security Tool Output Parsers

Parses output from security tools into structured data for storage in Memory MCP.
Supports: nmap, masscan, nuclei, nikto, gobuster, searchsploit (extensible)

Issue: #260
"""

import logging
import re
import xml.etree.ElementTree as ET  # nosec B405 - parsing trusted nmap output
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
    PORT_PATTERN = re.compile(r"(\d+)/(tcp|udp)\s+(\w+)\s+(\S+)(?:\s+(.+))?")
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
            or "<?xml" in output
            and "nmaprun" in output
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
            root = ET.fromstring(xml_output)  # nosec B314 - parsing trusted nmap output

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
                result.scan_stats.update(
                    {
                        "hosts_up": int(hosts_elem.get("up", 0)),
                        "hosts_down": int(hosts_elem.get("down", 0)),
                        "hosts_total": int(hosts_elem.get("total", 0)),
                    }
                )

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
        state = (
            state_elem.get("state", "unknown") if state_elem is not None else "unknown"
        )

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
            scripts.append(
                {
                    "id": script_elem.get("id"),
                    "output": script_elem.get("output"),
                }
            )

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

    def _parse_text_host_line(self, line: str) -> Optional[ParsedHost]:
        """
        Parse a host line from nmap text output.

        Returns a new ParsedHost if line matches host pattern, None otherwise. Issue #620.
        """
        host_match = self.HOST_PATTERN.search(line)
        if host_match:
            hostname = host_match.group(1)
            ip = host_match.group(2)
            return ParsedHost(ip=ip, hostname=hostname, status="up")
        return None

    def _parse_text_port_line(self, line: str, host: ParsedHost) -> bool:
        """
        Parse a port line and add to host if matched.

        Returns True if line was a port line, False otherwise. Issue #620.
        """
        port_match = self.PORT_PATTERN.match(line)
        if port_match:
            port_data = {
                "port": int(port_match.group(1)),
                "protocol": port_match.group(2),
                "state": port_match.group(3),
                "service": port_match.group(4),
                "version": port_match.group(5),
            }
            host.ports.append(port_data)
            return True
        return False

    def _parse_text_extra_info(self, line: str, host: ParsedHost) -> bool:
        """
        Parse OS and MAC address info from nmap text output.

        Updates host with OS guess or MAC address if matched. Issue #620.
        """
        os_match = self.OS_PATTERN.search(line)
        if os_match:
            host.os_guess = os_match.group(1)
            return True

        mac_match = self.MAC_PATTERN.search(line)
        if mac_match:
            host.mac_address = mac_match.group(1)
            host.vendor = mac_match.group(2)
            return True

        return False

    def _parse_text(self, output: str) -> ParsedToolOutput:
        """Parse nmap normal text output."""
        result = self._create_output(scan_type="text")
        current_host: Optional[ParsedHost] = None

        for line in output.split("\n"):
            line = line.strip()

            # Check for host line
            new_host = self._parse_text_host_line(line)
            if new_host:
                if current_host:
                    result.hosts.append(current_host)
                current_host = new_host
                continue

            if current_host:
                if self._parse_text_port_line(line, current_host):
                    continue
                self._parse_text_extra_info(line, current_host)

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

                hosts_map[ip].ports.append(
                    {
                        "port": port,
                        "protocol": protocol,
                        "state": "open",
                    }
                )

        result.hosts = list(hosts_map.values())
        return result


class NucleiParser(BaseToolParser):
    """Parser for nuclei vulnerability scanner output."""

    TOOL_NAME = "nuclei"

    # Pattern for nuclei output
    # [severity] [template-id] [protocol] url [matcher]
    LINE_PATTERN = re.compile(r"\[(\w+)\]\s+\[([^\]]+)\]\s+\[([^\]]+)\]\s+(\S+)")

    def can_parse(self, output: str) -> bool:
        """Check if output is from nuclei."""
        # Issue #380: use pre-compiled pattern
        return (
            "nuclei" in output.lower() or _NUCLEI_FORMAT_RE.search(output) is not None
        )

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


class NiktoParser(BaseToolParser):
    """Parser for nikto web vulnerability scanner output."""

    TOOL_NAME = "nikto"

    # Pattern for nikto findings
    FINDING_PATTERN = re.compile(r"^\+\s+(.+)$")
    TARGET_IP_PATTERN = re.compile(r"Target IP:\s+(\S+)")
    TARGET_HOSTNAME_PATTERN = re.compile(r"Target Hostname:\s+(\S+)")
    TARGET_PORT_PATTERN = re.compile(r"Target Port:\s+(\d+)")
    SERVER_PATTERN = re.compile(r"Server:\s+(.+)")
    OSVDB_PATTERN = re.compile(r"OSVDB-(\d+)")

    def can_parse(self, output: str) -> bool:
        """Check if output is from nikto."""
        return "nikto" in output.lower() or "Target IP:" in output

    def parse(self, output: str) -> ParsedToolOutput:
        """Parse nikto output."""
        result = self._create_output(scan_type="nikto")

        host = None
        port = None
        server = None

        for line in output.split("\n"):
            line = line.strip()

            # Extract target info
            ip_match = self.TARGET_IP_PATTERN.search(line)
            if ip_match:
                host = ip_match.group(1)
                continue

            hostname_match = self.TARGET_HOSTNAME_PATTERN.search(line)
            if hostname_match and host:
                result.hosts.append(
                    ParsedHost(ip=host, hostname=hostname_match.group(1), status="up")
                )
                continue

            port_match = self.TARGET_PORT_PATTERN.search(line)
            if port_match:
                port = int(port_match.group(1))
                continue

            server_match = self.SERVER_PATTERN.search(line)
            if server_match:
                server = server_match.group(1)
                continue

            # Parse findings (lines starting with +)
            finding_match = self.FINDING_PATTERN.match(line)
            if finding_match and host:
                finding_text = finding_match.group(1)
                severity = self._determine_severity(finding_text)

                vuln = ParsedVulnerability(
                    host=host,
                    port=port,
                    title=finding_text[:100],
                    severity=severity,
                    description=finding_text,
                    metadata={"server": server} if server else {},
                )
                result.vulnerabilities.append(vuln)

        return result

    def _determine_severity(self, finding: str) -> str:
        """Determine severity based on finding content (Issue #260)."""
        finding_lower = finding.lower()

        if "OSVDB" in finding:
            return "medium"
        elif "directory listing" in finding_lower or "indexing" in finding_lower:
            return "low"
        elif "default file" in finding_lower or "readme" in finding_lower:
            return "info"
        elif "sql" in finding_lower or "injection" in finding_lower:
            return "high"
        elif "xss" in finding_lower or "script" in finding_lower:
            return "high"
        else:
            return "medium"


class GobusterParser(BaseToolParser):
    """Parser for gobuster directory enumeration output."""

    TOOL_NAME = "gobuster"

    # Pattern for gobuster findings
    URL_PATTERN = re.compile(r"\[?\+\]?\s*Url:\s+(\S+)")
    PATH_PATTERN = re.compile(r"^(/\S*)\s+\(Status:\s+(\d+)\)\s+\[Size:\s+(\d+)\]")

    def can_parse(self, output: str) -> bool:
        """Check if output is from gobuster."""
        return "gobuster" in output.lower() or "[+] Url:" in output

    def parse(self, output: str) -> ParsedToolOutput:
        """Parse gobuster output."""
        result = self._create_output(scan_type="gobuster")

        base_url = None
        host = None

        for line in output.split("\n"):
            line = line.strip()

            # Extract base URL
            url_match = self.URL_PATTERN.search(line)
            if url_match:
                base_url = url_match.group(1)
                host_match = _URL_HOST_RE.search(base_url)
                if host_match:
                    host = host_match.group(1)
                continue

            # Parse discovered paths
            path_match = self.PATH_PATTERN.match(line)
            if path_match and host:
                path = path_match.group(1)
                status = int(path_match.group(2))
                size = int(path_match.group(3))

                # Determine severity based on path and status
                severity = self._classify_finding(path, status)

                vuln = ParsedVulnerability(
                    host=host,
                    title=f"Discovered path: {path}",
                    severity=severity,
                    description=f"Status: {status}, Size: {size} bytes",
                    metadata={
                        "path": path,
                        "status_code": status,
                        "size": size,
                        "url": f"{base_url}{path}" if base_url else path,
                    },
                )
                result.vulnerabilities.append(vuln)

        if host:
            result.hosts.append(ParsedHost(ip=host, status="up"))

        return result

    def _classify_finding(self, path: str, status: int) -> str:
        """Classify finding severity (Issue #260)."""
        path_lower = path.lower()

        # Sensitive paths
        if any(
            sensitive in path_lower
            for sensitive in [".git", "backup", "admin", ".env", "config"]
        ):
            if status == 200:
                return "high"
            elif status == 403:
                return "medium"

        # Status-based classification
        if status == 200:
            return "info"
        elif status == 403:
            return "low"
        elif status == 301:
            return "info"
        else:
            return "low"


class SearchsploitParser(BaseToolParser):
    """Parser for searchsploit exploit database output."""

    TOOL_NAME = "searchsploit"

    # Pattern for searchsploit table rows
    EXPLOIT_PATTERN = re.compile(r"^(.+?)\s+\|\s+(.+)$")

    def can_parse(self, output: str) -> bool:
        """Check if output is from searchsploit."""
        return (
            "searchsploit" in output.lower()
            or "Exploit Title" in output
            and "Path" in output
        )

    def parse(self, output: str) -> ParsedToolOutput:
        """Parse searchsploit output."""
        result = self._create_output(scan_type="searchsploit")

        in_results = False
        for line in output.split("\n"):
            line = line.strip()

            # Skip header and separator lines
            if "Exploit Title" in line or line.startswith("---"):
                in_results = True
                continue

            if not in_results or not line:
                continue

            # Parse exploit entries
            match = self.EXPLOIT_PATTERN.match(line)
            if match:
                title = match.group(1).strip()
                path = match.group(2).strip()

                # Skip if it's just dashes or empty
                if not title or title.startswith("---"):
                    continue

                severity = self._determine_severity(title)

                vuln = ParsedVulnerability(
                    host="N/A",
                    title=title,
                    severity=severity,
                    description=f"Exploit available: {path}",
                    metadata={"exploit_path": path, "exploit_title": title},
                )
                result.vulnerabilities.append(vuln)

        return result

    def _determine_severity(self, title: str) -> str:
        """Determine severity based on exploit type (Issue #260)."""
        title_lower = title.lower()

        if any(
            keyword in title_lower
            for keyword in ["remote code execution", "rce", "arbitrary code"]
        ):
            return "critical"
        elif any(
            keyword in title_lower
            for keyword in ["buffer overflow", "overflow", "privilege escalation"]
        ):
            return "high"
        elif any(keyword in title_lower for keyword in ["dos", "denial of service"]):
            return "medium"
        elif any(
            keyword in title_lower for keyword in ["information disclosure", "info"]
        ):
            return "low"
        else:
            return "medium"


class ToolParserRegistry:
    """Registry of available tool parsers with auto-detection."""

    def __init__(self) -> None:
        """Initialize tool parser registry with default security tool parsers."""
        self._parsers: list[BaseToolParser] = [
            NmapParser(),
            MasscanParser(),
            NucleiParser(),
            NiktoParser(),
            GobusterParser(),
            SearchsploitParser(),
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
